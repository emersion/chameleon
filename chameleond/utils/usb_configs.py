# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the configuration needed for USB audio driver"""


class USBAudioDriverConfigs(object):
  """The class that encapsulates the parameters of USB audio driver."""

  # Default values for initializing the class object.
  _DEFAULT_CHANNEL_MASK = 0b11
  _DEFAULT_SAMPLING_RATE = 48000
  _DEFAULT_SAMPLE_SIZE = 2

  def __init__(self):
    """Initializes a configs object with default values.

    Default values for the audio data fields are specified in the class
    variables above. All fields for device info are set to None.
    """
    self._p_channel_mask = self._DEFAULT_CHANNEL_MASK
    self._c_channel_mask = self._DEFAULT_CHANNEL_MASK
    self._p_sampling_rate = self._DEFAULT_SAMPLING_RATE
    self._c_sampling_rate = self._DEFAULT_SAMPLING_RATE
    self._p_sample_size = self._DEFAULT_SAMPLE_SIZE
    self._c_sample_size = self._DEFAULT_SAMPLE_SIZE

    self._device_info = {
        'idVendor': None,
        'idProduct': None,
        'bcdDevice': None,
        'iSerialNumber': None,
        'iManufacturer': None,
        'iProduct': None,}

  def SetPlaybackConfigs(self, channel_mask, sampling_rate, sample_size):
    """Sets different configs for playback.

    Args:
      channel_mask: int value of binary mask specifying the number of channels,
                    e.g., 0b11 for two channels.
      sampling_rate: sampling rate, e.g., 48000Hz.
      sample_size: size of each sample in bytes.
    """
    self._p_channel_mask = channel_mask
    self._p_sampling_rate = sampling_rate
    self._p_sample_size = sample_size

  def SetCaptureConfigs(self, channel_mask, sampling_rate, sample_size):
    """Sets different configs for capture.

    Args:
      channel_mask: int value of binary mask specifying the number of channels.
                    e.g., 0b11 for two channels.
      sampling_rate: sampling rate, e.g., 48000Hz.
      sample_size: size of each sample in bytes.
    """
    self._c_channel_mask = channel_mask
    self._c_sampling_rate = sampling_rate
    self._c_sample_size = sample_size

  def SetDeviceInfo(self, vendor_id=None, product_id=None, bcd_device=None,
                    serial_number=None, manufacturer=None, product=None):
    """Allows user to configure the driver into a particular product/device.

    Fields not specified as keyword arguments will be overwritten to None.

    Args:
      vendor_id: USB vendor ID as string.
      product_id: USB product ID as string.
      bcd_device: USB device release number as string with format "0xABCD".
      serial_number: serial number string.
      manufacturer: USB manufacturer string.
      product: USB product string.
    """
    self._device_info = {
        'idVendor': vendor_id,
        'idProduct': product_id,
        'bcdDevice': bcd_device,
        'iSerialNumber': serial_number,
        'iManufacturer': manufacturer,
        'iProduct': product,}

  def GetDriverAudioConfigsDict(self):
    """Get the audio data parameters in dict form.

    Returns:
      A dict containing all six parameters of driver configs.
    """
    return {
        'p_chmask': self._p_channel_mask,
        'p_srate': self._p_sampling_rate,
        'p_ssize': self._p_sample_size,
        'c_chmask': self._c_channel_mask,
        'c_srate': self._c_sampling_rate,
        'c_ssize': self._c_sample_size,}

  def GetDeviceInfoDict(self):
    """Get the device information in dict form.

    Returns:
      A dict containing all six parameters of device info.
    """
    return self._device_info

  def GetPlaybackConfigsDict(self):
    """Returns playback-related data configurations in dict form.

    Returns:
      A 3-item dictionary with keys: sample_size, channel_mask and
      sampling_rate.
    """
    playback_configs = {
        'sample_size': self._p_sample_size,
        'channel_mask': self._p_channel_mask,
        'sampling_rate': self._p_sampling_rate,
    }
    return playback_configs

  def GetCaptureConfigsDict(self):
    """Returns capture-related data configurations in dict form.

    Returns:
      A 3-item dictionary with keys: sample_size, channel_mask and
      sampling_rate.
    """
    capture_configs = {
        'sample_size': self._c_sample_size,
        'channel_mask': self._c_channel_mask,
        'sampling_rate': self._c_sampling_rate,
    }
    return capture_configs
