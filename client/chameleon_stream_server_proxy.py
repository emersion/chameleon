# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides the utilities for chameleon streaming server usage.

Sample Code for dumping real-time video frames:
  stream = ChameleonStreamServer(IP)
  stream.reset_video_session()

  chameleon_proxy.StartCapturingVideo(port)
  stream.dump_realtime_video_frame(False, RealtimeMode.BestEffort)
  while True:
    video_frame = stream.receive_realtime_video_frame()
    if not video_frame:
      break
    (frame_number, width, height, channel, data) = video_frame
    image = Image.fromstring('RGB', (width, height), data)
    image.save('%d.bmp' % frame_number)

Sample Code for dumping real-time audio pages:
  stream = ChameleonStreamServer(IP)
  stream.reset_audio_session()

  chameleon_proxy.StartCapturingAudio(port)
  stream.dump_realtime_audio_page(RealtimeMode.BestEffort)
  f = open('audio.raw',  'w')
  while True:
    audio_page = stream.receive_realtime_audio_page()
    if not audio_page:
      break
    (page_count, data) = audio_page
    f.write(data)
"""

import collections
import logging
import socket
from struct import calcsize, pack, unpack


CHAMELEON_STREAM_SERVER_PORT = 9994
SUPPORT_MAJOR_VERSION = 1
SUPPORT_MINOR_VERSION = 0


class StreamServerVersionError(Exception):
  """Version is not compatible between client and server."""
  pass


class ErrorCode(object):
  """Error codes of response from the stream server."""
  OK = 0
  NON_SUPPORT_COMMAND = 1
  ARGUMENT = 2
  REAL_TIME_STREAM_EXISTS = 3
  VIDEO_MEMORY_OVERFLOW_STOP = 4
  VIDEO_MEMORY_OVERFLOW_DROP = 5
  AUDIO_MEMORY_OVERFLOW_STOP = 6
  AUDIO_MEMORY_OVERFLOW_DROP = 7
  MEMORY_ALLOC_FAIL = 8


class RealtimeMode(object):
  """Realtime mode of dumping data."""
  # Stop dump when memory overflow
  StopWhenOverflow = 1

  # Drop data when memory overflow
  BestEffort = 2

  # Strings used for logging.
  LogStrings = ['None', 'Stop when overflow', 'Best effort']


class ChameleonStreamServer(object):
  """This class provides easy-to-use APIs to access the stream server."""

  # Main message types.
  _REQUEST_TYPE = 0
  _RESPONSE_TYPE = 1
  _DATA_TYPE = 2

  # uint16 type, uint16 error_code, uint32 length.
  packet_head_struct = '!HHL'

  # Message types.
  Message = collections.namedtuple('Message', ['type',
                                               'request_struct',
                                               'response_struct',
                                               'data_struct'])
  _RESET_MSG = Message(0, None, None, None)
  # Response: uint8 major, uint8 minor.
  _GET_VERSION_MSG = Message(1, None, '!BB', None)
  # Request: unt16 screen_width, uint16 screen_height.
  _CONFIG_VIDEO_STREAM_MSG = Message(2, '!HH', None, None)
  # Request: uint8 shrink_width, uint8 shrink_height.
  _CONFIG_SHRINK_VIDEO_STREAM_MSG = Message(3, '!BB', None, None)
  # Request: uint32 memory_address1, uint32 memory_address2,
  #          uint16 number_of_frames.
  # Data: uint32 frame_number, uint16 width, uint16 height, uint8 channel,
  #       uint8 padding[3]
  _DUMP_VIDEO_FRAME_MSG = Message(4, '!LLH', None, '!LHHBBBB')
  # Request: uint8 is_dual, uint8 mode.
  # Data: uint32 frame_number, uint16 width, uint16 height, uint8 channel,
  #       uint8 padding[3]
  _DUMP_REAL_TIME_VIDEO_FRAME_MSG = Message(5, '!BB', None, '!LHHBBBB')
  _STOP_DUMP_VIDEO_FRAME_MSG = Message(6, None, None, None)
  # Request: uint8 mode.
  # Data: uint32 page_count.
  _DUMP_REAL_TIME_AUDIO_PAGE = Message(7, '!B', None, '!L')
  _STOP_DUMP_AUDIO_PAGE = Message(8, None, None, None)

  _PACKET_HEAD_SIZE = 8

  def __init__(self, hostname, port=CHAMELEON_STREAM_SERVER_PORT):
    """Constructs a ChameleonStreamServer.

    Args:
      hostname: Hostname of stream server.
      port: Port number the stream server is listening on.
    """
    self._video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._hostname = hostname
    self._port = port
    # Used for non-realtime dump video frames.
    self._remain_frame_count = 0
    self._is_realtime_video = False
    self._is_realtime_audio = False

  def _get_request_type(self, message):
    """Get the request type of the message.

    Args:
      message: Message namedtuple.

    Returns:
      Request message type.
    """
    return (self._REQUEST_TYPE << 8) | message.type

  def _get_response_type(self, message):
    """Get the response type of the message.

    Args:
      message: Message namedtuple.

    Returns:
      Response message type.
    """
    return (self._RESPONSE_TYPE << 8) | message.type

  def _is_data_type(self, message_type):
    """Check if the message type is data type.

    Args:
      message_type: Message type

    Returns:
      Non 0 if the message is data type. otherwise 0.
    """
    return (self._DATA_TYPE << 8) & message_type

  def _receive_whole_packet(self, sock):
    """Receive one whole packet, contains packet head and content.

    Args:
      sock: Which socket to be used.

    Returns:
      A tuple with 4 elements: message_type, error code, length and content.

    Raises:
      ValueError if we can't receive data from server.
    """
    # receive packet header
    data = sock.recv(self._PACKET_HEAD_SIZE)
    if not data:
      raise ValueError('Receive no data from server')

    while len(data) != self._PACKET_HEAD_SIZE:
      remain_length = self._PACKET_HEAD_SIZE - len(data)
      recv_content = sock.recv(remain_length)
      data += recv_content

    message_type, error_code, length = unpack(self.packet_head_struct, data)

    # receive content
    content = ''
    remain_length = length
    while remain_length:
      recv_content = sock.recv(remain_length)
      if not recv_content:
        raise ValueError('Receive no data from server')
      remain_length -= len(recv_content)
      content += recv_content

    if error_code != ErrorCode.OK:
      logging.warn('Receive error code %d, %r', error_code, content)

    return (message_type, error_code, length, content)

  def _send_and_receive(self, packet, sock, check_error=True):
    """Send packet to server and receive response from server.

    Args:
      packet: The packet to be sent.
      sock: Which socket to be used.
      check_error: Check the error code. If this is True, this function will
          check the error code from response and raise exception if the error
          code is not OK.

    Returns:
      The response packet from server. A tuple with 4 elements contains
      message_type, error code, length and content.

    Raises:
      ValueError if check_error and error code is not OK.
    """
    sock.send(packet)
    packet = self._receive_whole_packet(sock)
    if packet and check_error:
      (_, error_code, _, _) = packet
      if error_code != ErrorCode.OK:
        raise ValueError('Error code is not OK')

    return packet

  def _generate_request_packet(self, message, *args):
    """Generate whole request packet with parameters.

    Args:
      message: Message namedtuple.
      *args: Packet contents.

    Returns:
      The whole request packet content.
    """
    if message.request_struct:
      content = pack(message.request_struct, *args)
    else:
      content = ''

    # Create header.
    head = pack(self.packet_head_struct,
                self._get_request_type(message),
                ErrorCode.OK, len(content))

    return head + content

  def _receive_video_frame(self):
    """Receive one video frame from server.

    This function assumes it only can receive video frame data packet
    from server. Error code will indicate success or not.

    Returns:
      If error code is OK, a decoded values will be stored in a tuple
      (error_code, frame number, width, height, channel, data).
      If error code is not OK, it will return a tuple (error code, content). The
      content is the error message from server.

    Raises:
      ValueError if packet is not data packet.
    """
    (message, error_code, _, content) = self._receive_whole_packet(
        self._video_sock)
    if error_code != ErrorCode.OK:
      return (error_code, content)

    if not self._is_data_type(message):
      raise ValueError('Message is not data')

    video_frame_head_size = calcsize(self._DUMP_VIDEO_FRAME_MSG.data_struct)
    frame_number, width, height, channel, _, _, _ = unpack(
        self._DUMP_VIDEO_FRAME_MSG.data_struct, content[:video_frame_head_size])
    data = content[video_frame_head_size:]
    return (error_code, frame_number, width, height, channel, data)

  def _get_version(self):
    """Get the version of the server.

    Returns:
      A tuple with Major and Minor number of the server.
    """
    packet = self._generate_request_packet(self._GET_VERSION_MSG)
    (_, _, _, content) = self._send_and_receive(packet, self._video_sock)
    return unpack(self._GET_VERSION_MSG.response_struct, content)

  def _check_version(self):
    """Check if this client is compatible with the server.

    The major number must be the same and the minor number of the server
    must larger then the client's.

    Returns:
      Compatible or not
    """
    (major, minor) = self._get_version()
    logging.debug('Major %d, minor %d', major, minor)
    return major == SUPPORT_MAJOR_VERSION and minor >= SUPPORT_MINOR_VERSION

  def connect(self):
    """Connect to the server and check the compatibility.

    Raises:
      StreamServerVersionError if client is not compitable with server.
    """
    server_address = (self._hostname, self._port)
    logging.info('connecting to %s:%s', self._hostname, self._port)
    self._video_sock.connect(server_address)
    self._audio_sock.connect(server_address)
    if not self._check_version():
      raise StreamServerVersionError()

  def reset_video_session(self):
    """Reset the video session."""
    logging.info('Reset session')
    packet = self._generate_request_packet(self._RESET_MSG)
    self._send_and_receive(packet, self._video_sock)

  def reset_audio_session(self):
    """Reset the audio session.

    For audio, we don't need to reset any thing.
    """
    pass

  def config_video_stream(self, width, height):
    """Configure the properties of the non-realtime video stream.

    Args:
      width: The screen width of the video frame by pixel per channel.
      height: The screen height of the video frame by pixel per channel.
    """
    logging.info('Config video, width %d, height %d', width, height)
    packet = self._generate_request_packet(self._CONFIG_VIDEO_STREAM_MSG, width,
                                           height)
    self._send_and_receive(packet, self._video_sock)

  def config_shrink_video_stream(self, shrink_width, shrink_height):
    """Configure the shrink operation of the video frame dump.

    Args:
      shrink_width: Shrink (shrink_width+1) pixels to 1 pixel when do video
          dump. 0 means no shrink.
      shrink_height: Shrink (shrink_height+1) to 1 height when do video dump.
          0 means no shrink.
    """
    logging.info('Config shrink video, shirnk_width %d, shrink_height %d',
                 shrink_width, shrink_height)
    packet = self._generate_request_packet(self._CONFIG_VIDEO_STREAM_MSG,
                                           shrink_width, shrink_height)
    self._send_and_receive(packet, self._video_sock)

  def dump_video_frame(self, count, address1, address2):
    """Ask server to dump video frames.

    User must use receive_video_frame() to receive video frames after
    calling this API.

    Sample Code:
      address = chameleon_proxy.GetCapturedFrameAddresses(0)
      count = chameleon_proxy.GetCapturedFrameCount()
      server.dump_video_frame(count, int(address), 0)
      while True:
        video_frame = server.receive_video_frame()
        if not video_frame:
          break
        (frame_number, width, height, channel, data) = video_frame
        image = Image.fromstring('RGB', (width, height), data)
        image.save('%s.bmp' % frame_number)

    Args:
      count: Specify number of video frames.
      address1: Dump memory address1.
      address2: Dump memory address2. If it is 0. It means we only dump from
          address1.
    """
    logging.info('dump video frame count %d, address1 0x%x, address2 0x%x',
                 count, address1, address2)
    packet = self._generate_request_packet(self._DUMP_VIDEO_FRAME_MSG, address1,
                                           address2, count)
    self._send_and_receive(packet, self._video_sock)
    self._remain_frame_count = count

  def dump_realtime_video_frame(self, is_dual, mode):
    """Ask server to dump realtime video frames.

    User must use receive_realtime_video_frame() to receive video frames
    after calling this API.

    Sample Code:
      server.dump_realtime_video_frame(False,
                       RealtimeMode.StopWhenOverflow)
      while True:
        video_frame = server.receive_realtime_video_frame()
        if not video_frame:
          break
        (frame_number, width, height, channel, data) = video_frame
        image = Image.fromstring('RGB', (width, height), data)
        image.save('%s.bmp' % frame_number)

    Args:
      is_dual: False: means only dump from channel1, True: means dump from dual
          channels.
      mode: The values of RealtimeMode.
    """
    logging.info('dump realtime video frame is_dual %d, mode %s', is_dual,
                 RealtimeMode.LogStrings[mode])
    packet = self._generate_request_packet(self._DUMP_REAL_TIME_VIDEO_FRAME_MSG,
                                           is_dual, mode)
    self._send_and_receive(packet, self._video_sock)
    self._is_realtime_video = True

  def receive_video_frame(self):
    """Receive one video frame from server after calling dump_video_frame().

    This function assumes it only can receive video frame data packet
    from server. Error code will indicate success or not.

    Returns:
      A tuple with video frame information.
      (frame number, width, height, channel, data), None if error happens.
    """
    if not self._remain_frame_count:
      return None
    self._remain_frame_count -= 1
    frame_info = self._receive_video_frame()
    if frame_info[0] != ErrorCode.OK:
      self._remain_frame_count = 0
      return None
    return frame_info[1:]

  def receive_realtime_video_frame(self):
    """Receive one video frame from server.

    After calling dump_realtime_video_frame(). The video frame may be dropped if
    we use BestEffort mode. We can detect it by the frame number.

    This function assumes it only can receive video frame data packet
    from server. Error code will indicate success or not.

    Returns:
      A tuple with video frame information.
      (frame number, width, height, channel, data), None if error happens or
      no more frames.
    """
    if not self._is_realtime_video:
      return None

    frame_info = self._receive_video_frame()
    # We can still receive video frame for drop case.
    while frame_info[0] == ErrorCode.VIDEO_MEMORY_OVERFLOW_DROP:
      frame_info = self._receive_video_frame()

    if frame_info[0] != ErrorCode.OK:
      return None

    return frame_info[1:]

  def stop_dump_realtime_video_frame(self):
    """Ask server to stop dump realtime video frame."""
    if not self._is_realtime_video:
      return
    packet = self._generate_request_packet(self._STOP_DUMP_VIDEO_FRAME_MSG)
    self._video_sock.send(packet)
    # Drop video frames until receive _StopDumpVideoFrame response.
    while True:
      (message, _, _, _) = self._receive_whole_packet(self._video_sock)
      if message == self._get_response_type(self._STOP_DUMP_VIDEO_FRAME_MSG):
        break
    self._is_realtime_video = False

  def dump_realtime_audio_page(self, mode):
    """Ask server to dump realtime audio pages.

    User must use receive_realtime_audio_page() to receive audio pages
    after calling this API.

    Sample Code for BestEffort:
      server.dump_realtime_audio_page(RealtimeMode.kBestEffort)
      f = open('audio.raw'), 'w')
      while True:
        audio_page = server.receive_realtime_audio_page()
        if audio_page:
          break
        (page_count, data) = audio_page
        f.write(data)

    Args:
      mode: The values of RealtimeMode.

    Raises:
      ValueError if error code from response is not OK.
    """
    logging.info('dump realtime audio page mode %s',
                 RealtimeMode.LogStrings[mode])
    packet = self._generate_request_packet(self._DUMP_REAL_TIME_AUDIO_PAGE,
                                           mode)
    self._send_and_receive(packet, self._audio_sock)
    self._is_realtime_audio = True

  def receive_realtime_audio_page(self):
    """Receive one audio page from server.

    After calling dump_realtime_audio_page(). The behavior is the same as
    receive_realtime_video_frame(). The audio page may be dropped if we use
    BestEffort mode. We can detect it by the page count.

    This function assumes it can receive audio page data packet
    from server. Error code will indicate success or not.

    Returns:
      A tuple with audio page information: (page count, data) None if error
      happens or no more frames.

    Rraises:
      ValueError if packet is not data packet.
    """
    if not self._is_realtime_audio:
      return None
    (message, error_code, _, content) = self._receive_whole_packet(
        self._audio_sock)
    # We can still receive audio page for drop case.
    while error_code == ErrorCode.AUDIO_MEMORY_OVERFLOW_DROP:
      (message, error_code, _, content) = self._receive_whole_packet(
          self._audio_sock)

    if error_code != ErrorCode.OK:
      return None
    if not self._is_data_type(message):
      raise ValueError('Message is not data')

    page_count = unpack(self._DUMP_REAL_TIME_AUDIO_PAGE.data_struct,
                        content[:4])[0]
    data = content[4:]
    return (page_count, data)

  def stop_dump_realtime_audio_page(self):
    """Ask server to stop dump realtime audio page."""
    if not self._is_realtime_audio:
      return
    packet = self._generate_request_packet(self._STOP_DUMP_AUDIO_PAGE)
    self._audio_sock.send(packet)
    # Drop audio pages until receive _StopDumpAudioPage response.
    while True:
      (message, _, _, _) = self._receive_whole_packet(self._audio_sock)
      if message == self._get_response_type(self._STOP_DUMP_AUDIO_PAGE):
        break
    self._is_realtime_audio = False
