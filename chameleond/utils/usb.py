# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control USB driver module."""

import re

import chameleon_common #pylint: disable=W0611
from chameleond.utils import system_tools
from chameleond.utils import usb_configs

class USBControllerError(Exception):
  """Exception raised when any error occurs in USBController."""
  pass


class USBController(object):
  """Provides interface to control USB driver.

  Properties:
    _driver_configs_to_set: A USBAudioDriverConfigs object used to store user-
                            set changes.
    _driver_configs_in_use: A USBAudioDriverConfigs object representing the
                            the configurations currently in use by the driver,
                            if it is successfully modprobed.
  """
  _MODPROBE_GAUDIO_ARGS_VERBOSE = ['g_audio', '-v', '--first-time']

  def __init__(self):
    """Initializes a USBController object.

    _driver_configs_to_set is initially set to a USBAudioDriverConfigs object
    with default configurations.
    """
    self._driver_configs_to_set = usb_configs.USBAudioDriverConfigs()
    self._driver_configs_in_use = None

  def EnableAudioDriver(self):
    """Modprobes g_audio module with params from driver_configs_to_set."""
    params_dict = self.\
                  _FormatDriverConfigsForModprobe(self._driver_configs_to_set)
    args_list = list(self._MODPROBE_GAUDIO_ARGS_VERBOSE)
    for key, value in params_dict.iteritems():
      if value is not None:
        item = key + '=' + str(value)
        args_list.append(item)
    system_tools.SystemTools.Call('modprobe', *args_list)
    #TODO(hsuying): Need to add logic to check modprobe result before setting
    # driver_configs_in_use to driver_configs_to_set. Right now we assume that
    # modprobe has installed the driver with driver_configs_to_set successfully,
    # which is not always the case.
    self._driver_configs_in_use = self._driver_configs_to_set

  def _FormatDriverConfigsForModprobe(self, driver_configs):
    """Converts configurations stored in driver_configs into modprobe arguments.

    Args:
      driver_configs: A USBAudioDriverConfigs object storing configurations to
        be applied to the driver when enabled.

    Returns:
      A dictionary containing modprobe-appropriate parameters and their
        corresponding argument values derived from driver_configs.
    """
    p_configs = driver_configs.GetPlaybackConfigs()
    p_chmask = self._TransformChannelNumberToChannelMask(p_configs.channel)
    p_srate = p_configs.rate
    p_ssize_in_bits = self._ExtractBitsFromSampleFormat(p_configs.sample_format)
    p_ssize_in_bytes = p_ssize_in_bits / 8

    c_configs = driver_configs.GetCaptureConfigs()
    c_chmask = self._TransformChannelNumberToChannelMask(c_configs.channel)
    c_srate = c_configs.rate
    c_ssize_in_bits = self._ExtractBitsFromSampleFormat(c_configs.sample_format)
    c_ssize_in_bytes = c_ssize_in_bits / 8

    device_info = driver_configs.GetDeviceInfoDict()

    params_dict = {
        'p_chmask': p_chmask,
        'p_srate': p_srate,
        'p_ssize': p_ssize_in_bytes,
        'c_chmask': c_chmask,
        'c_srate': c_srate,
        'c_ssize': c_ssize_in_bytes,
        'idVendor': device_info['vendor_id'],
        'idProduct': device_info['product_id'],
        'bcdDevice': device_info['bcd_device'],
        'iSerialNumber': device_info['serial_number'],
        'iManufacturer': device_info['manufacturer'],
        'iProduct': device_info['product'],
    }
    return params_dict

  def _TransformChannelNumberToChannelMask(self, channel_number):
    """Transforms channel number to integer equivalent of a binary mask.

    For example, channel_number = 2 will be transformed to 3, which is the
    integer value for binary number 0b11.

    Args:
      channel_number: The number of channels used.

    Returns:
      An integer representing the binary channel mask.
    """
    channel_mask = pow(2, channel_number) - 1
    return channel_mask

  def _ExtractBitsFromSampleFormat(self, sample_format):
    """Checks whether sample_format is valid and extracts sample size in bits.

    In this test suite, only sample formats with signed bits Little Endian are
    allowed.

    Args:
      sample_format: A string representing format of audio samples, e.g.,
        'S16_LE' means Signed 16 bits Little Endian.

    Returns:
      sample_size: An integer representing sample size in bits.
    """
    try:
      sample_format_lower = sample_format.lower()
      pattern = re.compile(r's(\d+)_le')
      match_result = pattern.match(sample_format_lower)
      if match_result is not None:
        sample_size = int(match_result.group(1))
        return sample_size
      else:
        raise USBControllerError('Sample format %s in driver configs is'
                                 ' invalid.' % sample_format)
    except ValueError:
      raise USBControllerError('Sample format %s in driver configs is'
                               ' invalid.' % sample_format)

  def DisableAudioDriver(self):
    """Removes the g_audio module from kernel."""
    args_list = list(self._MODPROBE_GAUDIO_ARGS_VERBOSE)
    args_list.append('-r')
    system_tools.SystemTools.call('modprobe', *args_list)

  def GetSupportedPlaybackDataFormat(self):
    """Returns the playback data format as supported by the USB driver.

    Returns:
      An AudioDataFormat object that stores the playback data format supported
        by the USB driver.
    """
    #TODO(hsuying): Need to check that there is a valid copy of configurations
    # stored by _driver_configs_in_use before trying to get configurations from
    # it. Now we assume that this method is only called when driver has been
    # successfully enabled with valid configurations.
    return self._driver_configs_in_use.GetPlaybackConfigs()

  def GetSupportedCaptureDataFormat(self):
    """Returns the capture data format as supported by the USB driver.

    Returns:
      An AudioDataFormat object that stores the capture data format supported by
        the USB driver.
    """
    #TODO(hsuying): Need to check that there is a valid copy of configurations
    # stored by _driver_configs_in_use before trying to get configurations from
    # it. Now we assume that this method is only called when driver has been
    # successfully enabled with valid configurations.
    return self._driver_configs_in_use.GetCaptureConfigs()

  def CheckPlaybackFormat(self, data_format):
    """Check whether format of playback data match that of audio driver.

    Args:
      data_format: An AudioDataFormat object in dict form

    Returns:
      True if the relevant key-value pairs in data_format match those of
        supported_format. False otherwise.
    """
    supported_format = self.GetSupportedPlaybackDataFormat().AsDict()
    for key in supported_format.keys():
      if data_format[key] != supported_format[key]:
        return False
    return True
