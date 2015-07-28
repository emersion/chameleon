# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control USB driver module."""

from chameleond.utils import system_tools

class USBController(object):
  """Provides interface to control USB driver."""

  def __init__(self, driver_configs):
    """Initializes a USBController object with given driver configurations.

    Args:
      driver_configs: a USBAudioDriverConfigs object.
    """
    self._driver_configs = driver_configs

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
