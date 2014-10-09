# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Audio utilities."""

import logging
import os
import struct
import tempfile
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import mem
from chameleond.utils import system_tools


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
    self._capture_audio_start_time = None

  @property
  def is_capturing(self):
    """True if audio dumper is dumping data.

    Returns:
      True if audio dumper is dumping data.
    """
    return self._adump.is_dumping

  def StartCapturingAudio(self):
    """Starts capturing audio."""
    self._capture_audio_start_time = time.time()
    self._adump.StartDumpingToMemory()
    logging.info('Started capturing audio.')

  def StopCapturingAudio(self):
    """Stops capturing audio.

    Returns:
      A tuple (data, format).
      data: The captured audio data.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.

    Raises:
      AudioCaptureManagerError: If captured time or page exceeds the limit.
      AudioCaptureManagerError: If there is no captured data.
    """
    if not self._capture_audio_start_time:
      raise AudioCaptureManagerError('Stop Capturing audio before Start')

    captured_time_secs = time.time() - self._capture_audio_start_time
    self._capture_audio_start_time = None

    start_address, page_count = self._adump.StopDumpingToMemory()

    if page_count > self._adump.MAX_DUMP_PAGES:
      raise AudioCaptureManagerError(
          'Dumped number of pages %d exceeds the limit %d',
          page_count, self._adump.MAX_DUMP_PAGES)

    if captured_time_secs > self._adump.MAX_DUMP_TIME_SECS:
      raise AudioCaptureManagerError(
          'Capture time %f seconds exceeds time limit %f secs' % (
              captured_time_secs, self._adump.MAX_DUMP_TIME_SECS))

    logging.info(
        'Stopped capturing audio. Captured duration: %f seconds; '
        '4K page count: %d', captured_time_secs, page_count)

    # The page count should increase even if there is no audio data
    # sent to this input.
    if page_count == 0:
      raise AudioCaptureManagerError(
          'No audio data was captured. Perhaps this input is not plugged ?')

    # Use pixeldump to dump a range of memory into file.
    # Originally, the area size is
    # screen_width * screen_height * byte_per_pixel.
    # In our use case, the area size is page_size * page_count * 1.
    with tempfile.NamedTemporaryFile() as f:
      system_tools.SystemTools.Call(
          'pixeldump', '-a', start_address, f.name, self._adump.PAGE_SIZE,
          page_count, 1)
      logging.info('Captured audio data size: %f MBytes',
                   os.path.getsize(f.name) / 1024.0 / 1024.0)
      return f.read(), self._adump.audio_data_format_as_dict


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

  def StartPlayingAudio(self, audio_data):
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
