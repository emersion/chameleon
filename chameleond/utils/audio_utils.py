# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Audio utilities."""

import logging
import os
import struct

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import fpga
from chameleond.utils import ids
from chameleond.utils import mem
from chameleond.utils import memory_dumper


class AudioCaptureManagerError(Exception):
  """Exception raised when any error occurs in AudioCaptureManager."""
  pass


class AudioCaptureManager(object):
  """A class to manage audio data capturing.

  Properties:
    _adump: An AudioDumper object in FpgaController.
    _capture_audio_start_time: Starting time of audio data capturing.
  """
  def __init__(self, audio_dumper):
    """Inits an AudioCaptureManager.

    Args:
      audio_dumper: An AudioDumper object.
    """
    self._adump = audio_dumper
    self._mem_dumper = None
    self._file_path = None

  @property
  def is_capturing(self):
    """True if audio dumper is dumping data.

    Returns:
      True if audio dumper is dumping data.
    """
    return self._adump.is_dumping

  def StartCapturingAudio(self, file_path):
    """Starts capturing audio.

    Args:
      file_path: The target file for audio capturing. None for no target file.
    """
    self._file_path = file_path
    self._adump.StartDumpingToMemory()
    self._mem_dumper = None
    if file_path:
      self._mem_dumper = memory_dumper.MemoryDumper(file_path, self._adump)
      self._mem_dumper.start()
    logging.info('Started capturing audio.')

  def StopCapturingAudio(self):
    """Stops capturing audio.

    Returns:
      The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.

    Raises:
      AudioCaptureManagerError: If captured time or page exceeds the limit.
      AudioCaptureManagerError: If there is no captured data.
    """
    if not self.is_capturing:
      raise AudioCaptureManagerError('Stop Capturing audio before Start')

    if self._mem_dumper:
      self._mem_dumper.Stop()
      self._mem_dumper.join()
    _, page_count = self._adump.StopDumpingToMemory()
    logging.info('Stopped capturing audio.')

    if self._mem_dumper and self._mem_dumper.exitcode:
      raise AudioCaptureManagerError(
          'MemoryDumper was terminated unexpectedly.')

    if page_count == 0:
      raise AudioCaptureManagerError(
          'No audio data was captured. Perhaps this input is not plugged ?')

    # Workaround for issue crbug.com/574683 where the last two pages should
    # be neglected.
    if self._file_path:
      self._TruncateFile(2)

    return self._adump.audio_data_format_as_dict

  def _TruncateFile(self, pages):
    """Truncates some pages from the end of recorded file.

    Args:
      pages: Number of pages to be truncated from the end of file.

    Raises:
      AudioCaptureManagerError if not enough data was captured.
    """
    file_size = os.path.getsize(self._file_path)
    new_file_size = file_size - self._adump.PAGE_SIZE * pages
    if new_file_size <= 0:
      raise AudioCaptureManagerError('Not enough audio data was captured.')

    with open(self._file_path, 'r+') as f:
      f.truncate(new_file_size)


class AudioStreamManagerError(Exception):
  """Exception raised when any error occurs in AudioStreamManager."""
  pass


class AudioStreamManager(object):
  """A class to manage audio data playback.

  Properties:
    _stream: An AudioStreamController object.
  """
  def __init__(self, stream_controller):
    """Inits an AudioStreamManager.

    Args:
      stream_controller: An AudioStreamController object.
    """
    self._stream = stream_controller
    self._memory = mem.MemoryForDumper

  @property
  def is_streaming(self):
    """The manager is streaming."""
    return self._stream.is_streaming

  def StartPlayingAudioData(self, audio_data):
    """Starts playing audio_data.

    Currently AudioStreamManager only accepts data format if it is identical
    to self._stream.audio_data_format_as_dict, which is
    audio.AudioDataFormat(
      file_type='raw', sample_format='S32_LE', channel=8, rate=48000)
    Chameleon user should do the format conversion to minimize
    work load on Chameleon board.

    Args:
      audio_data: A tuple (data, format).
        data: The audio data to play.
        format: The dict representation of AudioDataFormat. Refer to docstring
          of utils.audio.AudioDataFormat for detail.
    """
    data, data_format = audio_data
    self._CheckDataFormat(data_format)
    size_to_play = self._CopyDataToMemory(data)
    self._stream.StartStreaming(size_to_play)

  def StopPlayingAudio(self):
    """Stops playing audio."""
    self._stream.StopStreaming()

  def _CheckDataFormat(self, data_format):
    """Checks if data format is valid.

    Currently AudioStreamManager only accepts data format if it is identical
    to self._stream.audio_data_format_as_dict, which is
    audio.AudioDataFormat(
      file_type='raw', sample_format='S32_LE', channel=8, rate=48000)

    Raises:
      AudioStreamManagerError: If data format is invalid.
    """
    if data_format != self._stream.audio_data_format_as_dict:
      raise AudioStreamManagerError(
          'audio data type %r is not supported' % data_format.file_type)

  def _CopyDataToMemory(self, data):
    """Copies audio data to memory.

    Appends zeros to audio data so its size becomes a multiple of page size.
    Copies audio data to memory allocated for streaming, which starts
    from _stream.mapped_start_address with size
    _stream.MAX_STREAM_BUFFER_SIZE.

    Args:
      data: Data to be copied to memory.

    Returns:
      length of copied data.

    Raises:
      AudioStreamManagerError: If size of appended data is larger than
        self._stream.MAX_STREAM_BUFFER_SIZE.
    """
    data = AppendZeroToFitPageSize(data, self._stream.PAGE_SIZE)
    if len(data) > self._stream.MAX_STREAM_BUFFER_SIZE:
      raise AudioStreamManagerError(
          'audio data is larger than %r bytes' %
          self._stream.MAX_STREAM_BUFFER_SIZE)
    logging.info('Fill 0x%x bytes data to memory 0x%x',
                 len(data), self._stream.mapped_start_address)
    self._memory.Fill(self._stream.mapped_start_address, data)
    return len(data)


def AppendZeroToFitPageSize(data, page_size):
  """Appends data such that it is a multiple of page size.

  Args:
    data: The data to be appended.
    page_size: Page size in bytes.

  Returns:
    The appended result.
  """
  offset = len(data) % page_size
  if offset == 0:
    return data
  append_size = page_size - offset
  return data + struct.pack('<b', 0) * append_size


class AudioRouteManagerError(Exception):
  """Exception raised when any error occurs in AudioRouteManager."""
  pass


class AudioRouteManager(object):
  """A class to manage audio route.

  This class provides SetupRouteFrom[]To[] for audio flows to setup
  audio route. Route reset API are also provided. Invalid route as
  described below will raise exception when requested.

  The audio codec needs us feed its I2S clock when recording/playing
  audio. There are two possible clock sources:
  1. Generator generates a fixed 48K clock once it is turned on and it
     is not controlled by divisor or volume control.
  2. The clock from RX along with the audio signal received from RX.

  Due to the fact that codec only accepts one clock,
  we can not connect two different clocks for playback and recording.

  The following combination is invalid:

  RX_I2S -> I2S
  CODEC -> DUMPER
                                                    ----------       play to
  Source: RX_I2S        --->  Destination: I2S --> |          | ---> LINEOUT
                                                   |  CODEC   |
  Destination: DUMPER   <---  Source: CODEC    <-- |          | <--- record from
                                                    ----------       LINEIN/MIC

  In the above combination, codec will only be connected to the RX clock. But
  if there is no audio signal from RX, the RX clock will be gone too. This will
  cause malfunction to the path of recording.

  Properties:
    _aroute: An AudioRouteController object in FpgaController.
  """
  def __init__(self, audio_route):
    """Inits an AudioRouteManager.

    Args:
      audio_route: An AudioRouteController object.
    """
    self._aroute = audio_route

  def SetupRouteFromInputToDumper(self, input_id):
    """Sets up audio route given an input_id for audio dumper.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    source = self._GetAudioSourceFromInputId(input_id)
    self._SetupRouteFromSourceToDestination(
        source, fpga.AudioDestination.DUMPER)

  def SetupRouteFromInputToI2S(self, input_id):
    """Sets up audio source given an input_id for I2S controller.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    source = self._GetAudioSourceFromInputId(input_id)
    self._SetupRouteFromSourceToDestination(source, fpga.AudioDestination.I2S)

  def SetupRouteFromMemoryToI2S(self):
    """Sets up memory as audio source and I2S as destination."""
    self._SetupRouteFromSourceToDestination(
        fpga.AudioSource.MEMORY, fpga.AudioDestination.I2S)

  def ResetRouteToI2S(self):
    """Resets the route to I2S by selecting generator as source."""
    self._SetupRouteFromSourceToDestination(
        fpga.AudioSource.GENERATOR, fpga.AudioDestination.I2S)

  def ResetRouteToDumper(self):
    """Resets the route to DUMPER by selecting generator as source."""
    self._SetupRouteFromSourceToDestination(
        fpga.AudioSource.GENERATOR, fpga.AudioDestination.DUMPER)

  def _SetupRouteFromSourceToDestination(self, source, destination):
    """Sets up route from source to destination.

    _CheckInvalidCombination will check if the combination is invalid.

    Args:
      source: An audio source in fpga.AudioSource.
      destination: An audio destination in fpga.AudioDestination.
    """
    # Gets the other source to check if the combination is invalid.
    if destination == fpga.AudioDestination.I2S:
      source_i2s = source
      source_dumper = self._aroute.GetCurrentSource(
          fpga.AudioDestination.DUMPER)
    else:
      source_i2s = self._aroute.GetCurrentSource(fpga.AudioDestination.I2S)
      source_dumper = source

    self._CheckInvalidCombination(source_i2s, source_dumper)

    # Turns on generator if any one of source requires generator clock.
    # Turns off generator if none of the source requires generator clock.
    self._aroute.SetGeneratorEnabled(
        self._RequiresGeneratorClock(source_i2s) or
        self._RequiresGeneratorClock(source_dumper))

    self._aroute.SetupRoute(source, destination)

  def _CheckInvalidCombination(self, source_i2s, source_dumper):
    """Checks if the route combination is invalid.

    As stated in the docstrings of AudioRouteManager, this combination
    is invalid:

    RX_I2S -> I2S
    CODEC -> DUMPER

    Args:
      source_i2s: An audio source in fpga.AudioSource.
      source_dumper: An audio source in fpga.AudioSource.

    Raises:
      AudioRouteManagerError if the route is invalid.
    """
    if (source_i2s == fpga.AudioSource.RX_I2S and
        source_dumper == fpga.AudioSource.CODEC):
      raise AudioRouteManagerError(
          '%r -> %r, %r -> %r is invalid.' % (
              source_i2s, fpga.AudioDestination.I2S,
              source_dumper, fpga.AudioDestination.DUMPER))

  def _GetAudioSourceFromInputId(self, input_id):
    """Gets audio source given an input_id.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.

    Returns:
      An audio source in fpga.AudioSource.

    Raises:
      AudioRouteManagerError if input_id is not supported.
    """
    if input_id in [ids.DP1, ids.DP2, ids.HDMI]:
      return fpga.AudioSource.RX_I2S
    if input_id in [ids.MIC, ids.LINEIN]:
      return fpga.AudioSource.CODEC
    raise AudioRouteManagerError(
        'input_id %s is not supported in AudioRouteController' % input_id)

  def _RequiresGeneratorClock(self, source):
    """Checks if a source requires generator clock.

    Args:
      source: An audio source in fpga.AudioSource.

    Returns:
      True if generator clock is required for source.
    """
    return source != fpga.AudioSource.RX_I2S
