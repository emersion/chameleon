# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A class used to detect audio streamed values close to 0."""

import logging
import os
import struct
import time
import wave

from chameleon_stream_server_proxy import (ChameleonStreamServer,
                                           RealtimeMode)


class AudioValueDetector(object):
  """The class detects if Chameleon captures continuous audio data close to 0.

    Attributes:
      _host: The host address of chameleon board.
      _audio_frame_format: Audio sample format from chameleon.
      _audio_frame_bytes: Total bytes per audio sample.
      _continuous_0_per_channel: An array to record how many continuous 0s we've
          gotten per channel
      _do_detect_0_per_channel: An array to indicate the detect state per
          channel.  True for detecting continous 0s. False for detecting non 0.
      _num_print_frames: Used to print the number of values of the first audio
          frames.
          Used to fine tune the margin.
  """
  def __init__(self, host):
    """Creates an AudioValueDetector object.

    Args:
      host: The chameleon board's host address.
    """
    self._host = host
    # Audio sample from chameleon are 32 bits per channel and it has 8 channels.
    self._audio_frame_format = '<llllllll'
    self._audio_frame_bytes = struct.calcsize(self._audio_frame_format)
    self._continuous_0_per_channel = None
    self._do_detect_0_per_channel = None
    self._num_print_frames = 0

  def SaveChameleonAudioDataToWav(self, directory, data, file_name):
    """Save audio data from chameleon to a wave file.

    This function will use default parameters for the chameleon audio data.

    Args:
      directory: Save file in which directory.
      data: audio data.
      file_name: The file name of the wave file.
    """
    num_channels = 8
    sampwidth = 4
    framerate = 48000
    comptype = "NONE"
    compname = "not compressed"
    file_path = '%s/%s' % (directory, file_name)
    logging.warn('Save to %s', file_path)
    wav_file = wave.open(file_path, 'w')
    wav_file.setparams((num_channels, sampwidth, framerate, len(data), comptype,
                        compname))
    wav_file.writeframes(data)
    wav_file.close()

  def _DetectAudioDataValues(self, channels, continuous_samples, data, margin):
    """Detect if we get continuous 0s from chameleon audio data.

    Args:
      channels: Array of audio channels we want to check.
      continuous_samples: When continuous_samples samples are closed to 0,
          do detect 0 event.
      data: A page of audio data from chameleon.
      margin: Used to decide if the value is closed to 0. Maximum value is 1.

    Returns:
      Can save file or not. Save file when detecting continuous 0 or detecting
      non-zero after continuous 0.
    """
    should_save_file = False

    # Detect audio data values sample by sample.
    offset = 0
    while offset != len(data):
      audio_sample = struct.unpack_from(self._audio_frame_format, data, offset)
      offset = offset + self._audio_frame_bytes
      for index, channel in enumerate(channels):
        value = float(abs(audio_sample[channel]))/(1 << 31)
        if self._num_print_frames:
          logging.info('Value of channel %d is %f', channel, value)
        # Value is close to 0.
        if value < margin:
          self._continuous_0_per_channel[index] += 1
          # We've detected continuous 0s on this channel before. This sample is
          # in the same continous 0s state.
          if not self._do_detect_0_per_channel[index]:
            continue
          if self._continuous_0_per_channel[index] >= continuous_samples:
            logging.warn('Detected continuous %d 0s of channel %d',
                         self._continuous_0_per_channel[index], channel)
            self._do_detect_0_per_channel[index] = False
            should_save_file = True
        else:
          # Value is not close to 0.
          if not self._do_detect_0_per_channel[index]:
            # This if section means we get non-0 after continuous 0s were
            # detected.
            logging.warn('Continuous %d 0s of channel %d',
                         self._continuous_0_per_channel[index], channel)
            self._do_detect_0_per_channel[index] = True
            should_save_file = True
          # Reset number of continuous 0s when we detect a non-0 value.
          self._continuous_0_per_channel[index] = 0
      if self._num_print_frames:
        self._num_print_frames -= 1
    return should_save_file

  def Detect(self, channels, margin, continuous_samples, duration, dump_frames):
    """Detects if Chameleon captures continuous audio data close to 0.

    This function will get the audio streaming data from stream server and will
    check if the audio data is close to 0 by the margin parameter.
    -margin < value < margin will be considered to be close to 0.
    If there are continuous audio samples close to 0 in the streamed data,
    test_server will log it and save the audio data to a wav file.

    Args:
      channels: Array of audio channels we want to check.
          E.g. [0, 1] means we only care about channel 0 and channel 1.
      margin: Used to decide if the value is closed to 0. Maximum value is 1.
      continuous_samples: When continuous_samples samples are closed to 0,
          trigger event.
      duration: The duration of monitoring in seconds.
      dump_frames: When event happens, how many audio frames we want to save to
          file.
    """
    # Create a new directory for storing audio files.
    directory = 'detect0_%s' % time.strftime('%Y%m%d%H%M%S', time.localtime())
    if not os.path.exists(directory):
      os.mkdir(directory)

    dump_bytes = self._audio_frame_bytes * dump_frames

    self._num_print_frames = 10
    self._continuous_0_per_channel = [0] * len(channels)
    self._do_detect_0_per_channel = [True] * len(channels)
    audio_data = ''

    stream = ChameleonStreamServer(self._host)
    stream.connect()
    stream.reset_audio_session()
    stream.dump_realtime_audio_page(RealtimeMode.BestEffort)
    start_time = time.time()
    logging.info('Start to detect continuous 0s.')
    logging.info('Channels=%r, margin=%f, continuous_samples=%d, '
                 'duration=%d seconds, dump_frames=%d.', channels, margin,
                 continuous_samples, duration, dump_frames)
    while True:
      audio_page = stream.receive_realtime_audio_page()
      if not audio_page:
        logging.warn('No audio page, there may be a socket errror.')
        break
      # We've checked None before, so we can disable the false alarm.
      (page_count, data) = audio_page  # pylint: disable=unpacking-non-sequence
      audio_data += data

      # Only keep needed volume of data for saving memory usage.
      audio_data = audio_data[-dump_bytes:]

      should_save_file = self._DetectAudioDataValues(channels,
                                                     continuous_samples, data,
                                                     margin)
      if should_save_file:
        file_name = 'audio_%d.wav' % page_count
        self.SaveChameleonAudioDataToWav(directory, audio_data, file_name)
        audio_data = ''

      current_time = time.time()
      if current_time - start_time > duration:
        stream.stop_dump_realtime_audio_page()
        logging.warn('Timeout stop detect.')
        break
