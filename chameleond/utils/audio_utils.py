# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Audio utilities."""

import logging
import os
import tempfile
import time

import chameleon_common  # pylint: disable=W0611
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

    if page_count > self._adump.SIMPLE_DUMP_PAGE_LIMIT:
      raise AudioCaptureManagerError(
          'Dumped number of pages %d exceeds the limit %d',
          page_count, self._adump.SIMPLE_DUMP_PAGE_LIMIT)

    if captured_time_secs > self._adump.SIMPLE_DUMP_TIME_LIMIT_SECS:
      raise AudioCaptureManagerError(
          'Capture time %f seconds exceeds time limit %f secs' % (
              captured_time_secs, self._adump.SIMPLE_DUMP_TIME_LIMIT_SECS))

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
