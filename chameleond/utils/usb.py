# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control USB driver module."""

import chameleon_common
from chameleond.utils import system_tools

class USBController(object):
  """Provides interface to control USB driver.

  Properties:
    _supported_playback_data_format: Allowed data format for audio playback
                                     based on driver configs.
    _supported_capture_data_format: Allowed data format for audio capture based
                                    on driver configs.
  """

  def __init__(self, driver_configs):
    """Initializes a USBController object with given driver configurations.

    Args:
      driver_configs: a USBAudioDriverConfigs object.
    """
    self._driver_configs = driver_configs
    self._supported_playback_data_format = None
    self._supported_capture_data_format = None

  def InitializeAudioDriver(self):
    """Modprobes g_audio module with params from driver_configs."""
    driver_audio_configs = self._driver_configs.GetDriverAudioConfigsDict()
    params_list = []
    for key, value in driver_audio_configs.iteritems():
      item = key + '=' + str(value)
      params_list.append(item)

    device_info_configs = self._driver_configs.GetDeviceInfoDict()
    for key, value in device_info_configs.iteritems():
      if value is not None:
        item = key + '=' + str(value)
        params_list.append(item)

    system_tools.SystemTools.Call('modprobe', 'g_audio', *params_list)

  def DisableAudioDriver(self):
    """Removes the g_audio module from kernel."""
    system_tools.SystemTools.call('modprobe', '-r', 'g_audio')

  def _GetSampleFormat(self, sample_size):
    """Based on sample size, gets sample format as Signed bits in Little Endian.

    Sample size is converted from bytes to bits.

    Args:
      sample_size: Either playback or capture sample size in bytes

    Returns:
      A format string e.g., 'S32_LE' for 32 Signed Bits Little Endian.
    """
    sample_format = 'S' + str(sample_size * 8) + 'LE'
    return sample_format

  def _ConvertChannelMaskToChannelNumber(self, channel_mask):
    """Converts size of a binary mask to number e.g., 0b11 ---> 2

    Returns:
      An integer for channel number.
    """
    count = 0
    while channel_mask:
      count += channel_mask & 1
      channel_mask = channel_mask >> 1
    return count

  def _ConvertConfigsToDataFormat(self, configs_dict):
    """Converts a configs dictionary into a data format dictionary.

    Args:
      configs_dict: A three-item dictionary with the following keys -
        sample_size: Size of each sample in bytes
        channel_mask: Number of channels in binary mask form
        sampling_rate: Rate at which data is sampled

    Returns:
      A three-item dictionary with the following keys:
        sample_format: See _GetSampleFormat() docstring for details
        channel: Number of channels in integer form
        rate: Same as sampling_rate
    """
    sample_format = self._GetSampleFormat(configs_dict['sample_size'])
    channel_mask = configs_dict['channel_mask']
    channel = self._ConvertChannelMaskToChannelNumber(channel_mask)
    rate = configs_dict['sampling_rate']
    data_format = {
        'sample_format': sample_format,
        'channel': channel,
        'rate': rate,
    }
    return data_format

  def GetSupportedPlaybackDataFormat(self):
    """Returns the playback data format as supported by the USB driver.

    This method converts the driver's playback configurations into data format.

    Returns:
      A three-entry dictionary with keys: sample_format, channel and rate.
    """
    if self._supported_playback_data_format is None:
      playback_configs = self._driver_configs.GetPlaybackConfigsDict()
      data_format = self._ConvertConfigsToDataFormat(playback_configs)
      self._supported_playback_data_format = data_format
    return self._supported_playback_data_format

  def GetSupportedCaptureDataFormat(self):
    """Returns the capture data format as supported by the USB driver.

    This method converts the driver's capture configurations into data format.

    Returns:
      A three-entry dictionary with keys: sample_format, channel and rate.
    """
    if self._supported_capture_data_format is None:
      capture_configs = self._driver_configs.GetCaptureConfigsDict()
      data_format = self._ConvertConfigsToDataFormat(capture_configs)
      self._supported_capture_data_format = data_format
    return self._supported_capture_data_format
