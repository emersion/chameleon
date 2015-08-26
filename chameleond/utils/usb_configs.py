# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the configuration needed for USB audio driver"""

import chameleon_common #pylint: disable=W0611
from chameleond.utils import audio

class USBAudioDriverConfigs(object):
  """The class that encapsulates the parameters of USB audio driver."""

  # Default values for initializing the class object.
  _DEFAULT_FILE_TYPE = None
  _DEFAULT_SAMPLE_FORMAT = 'S16_LE'
  _DEFAULT_CHANNEL = 2
  _DEFAULT_RATE = 48000

  def __init__(self):
    """Initializes a configs object with default values.

    Default values for the audio data fields are specified in the class
    variables above. All fields for device info are set to None.
    """
    self._playback_configs = audio.AudioDataFormat(self._DEFAULT_FILE_TYPE,
                                                   self._DEFAULT_SAMPLE_FORMAT,
                                                   self._DEFAULT_CHANNEL,
                                                   self._DEFAULT_RATE)

    self._capture_configs = audio.AudioDataFormat(self._DEFAULT_FILE_TYPE,
                                                  self._DEFAULT_SAMPLE_FORMAT,
                                                  self._DEFAULT_CHANNEL,
                                                  self._DEFAULT_RATE)
    self._device_info = {
        'vendor_id': None,
        'product_id': None,
        'bcd_device': None,
        'serial_number': None,
        'manufacturer': None,
        'product': None,
    }

  def SetPlaybackConfigs(self, playback_data_format):
    """Sets different configurations for playback.

    Args:
      playback_data_format: An AudioDataFormat object with playback
        configurations.
    """
    self._playback_configs = playback_data_format

  def SetCaptureConfigs(self, capture_data_format):
    """Sets different configurations for capture.

    Args:
      capture_data_format: An AudioDataFormat object with capture
        configurations.
    """
    self._capture_configs = capture_data_format

  def SetDeviceInfo(self, device_info):
    """Allows user to configure the driver into a particular product/device.

    Args:
      device_info: A six-entry dictionary with the following keys: 'vendor_id',
        'product_id', 'bcd_device', 'serial_number', 'manufacturer' and
        'product'. Keys with None as corresponding value will be ignored, and
        its original value saved self._device_info will be unchanged.
    """
    for key, value in device_info.iteritems():
      if value is not None:
        self._device_info[key] = value

  def GetDeviceInfoDict(self):
    """Get the device information in dict form.

    Returns:
      A dict containing all six parameters of device info.
    """
    return self._device_info

  def GetPlaybackConfigs(self):
    """Returns playback-related data configurations.

    Returns:
      An AudioDataFormat object containing values of playback-related
        configurations.
    """
    return self._playback_configs

  def GetCaptureConfigs(self):
    """Returns capture-related data configurations.

    Returns:
      An AudioDataFormat object containing values of capture-related
        configurations.
    """
    return self._capture_configs
