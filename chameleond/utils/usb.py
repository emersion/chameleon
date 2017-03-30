# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control USB driver module."""

import copy
import logging
import re

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import system_tools
from chameleond.utils import usb_audio_configs


class USBControllerError(Exception):
  """Exception raised when any error occurs in USBController."""
  pass


class USBController(object):
  """Provides interface to control USB driver.

  Properties:
    _module: Module name of USB driver.
  """
  # Enumeration of modprobe status.
  MODPROBE_SUCCESS = 0  # successfully modprobe inserted/removed
  MODPROBE_NO_ACTION = 1  # command is redundant and no error occurred
  MODPROBE_DUPLICATED = 2  # module is already inserted/removed from the kernel

  def __init__(self, module):
    """Initializes a USBAudioController object.

    Modprobe command to remove driver module from kernel is called to make sure
    the module is not in kernel at initialization.
    """
    self._module = module
    system_tools.SystemTools.Call('modprobe', '-r', self._module)

  @property
  def _is_modprobed(self):
    """A property that is True when the driver module is enabled.

    Returns:
      True when the module name is got from lsmod command. False otherwise.
    """
    output = system_tools.SystemTools.Output('lsmod').splitlines()
    return any(line.startswith(self._module) for line in output)

  @property
  def _modprobe_verbose_args(self):
    """A property of modprobe command arguments.

    Returns:
      A list of modprobe command arguments with verbosity.
    """
    return [self._module, '-v', '--first-time']

  def DriverIsEnabled(self):
    """Returns a Boolean indicating whether driver is modprobed.

    Returns:
      True if driver is enabled. False otherwise.
    """
    return self._is_modprobed

  def EnableDriver(self):
    """Modprobes USB driver module.

    Returns:
      The status code of modprobe result.
    """
    args_list = self._MakeArgsForInsertModule()
    process = system_tools.SystemTools.RunInSubprocess('modprobe', *args_list)
    logging.info('Modprobe command is run with arguments: %s', str(args_list))
    process_output = system_tools.SystemTools.GetSubprocessOutput(process)
    return self._CheckModprobeResult(process_output)

  def _MakeArgsForInsertModule(self):
    """Puts flags and arguments needed for inserting module into a list.

    The list includes -v (--verbose) flag and --first-time flag, which makes the
    modprobe command fail if it does not in fact do anything.

    Returns:
      A list of arguments formatted for calling modprobe command to insert
        module.
    """
    return self._modprobe_verbose_args

  def _CheckModprobeResult(self, process_output):
    """Checks result of insert module command.

    Args:
      process_output: A tuple (return_code, out, err) containing the return
        code, standard output and error message (if applicable) of the
        the subprocess spawned by the modprobe command to insert the driver
        module into kernel.

    Returns:
      The status code of modprobe result.

    Raises:
      USBControllerError if _is_modprobed returns False, meaning the driver
        was not successfully enabled by modprobe.
    """
    return_code, out, err = process_output
    error_message = ('ERROR: could not insert \'%s\': Module already in '
                     'kernel\n' % self._module)
    if return_code == 0:
      if 'insmod' in out and err == '':
        return self.MODPROBE_SUCCESS
      return self.MODPROBE_NO_ACTION
    if error_message in err and self._is_modprobed:
      logging.warning('%s module is already in the kernel.', self._module)
      return self.MODPROBE_DUPLICATED
    logging.error('Modprobe return code: %d', return_code)
    logging.error('Modprobe stdout: %s', out)
    logging.error('Modprobe error (if any): %s', err)
    logging.exception('Modprobe failed to insert %s module into kernel.',
                      self._module)
    raise USBControllerError('Driver failed to be enabled.')

  def DisableDriver(self):
    """Removes USB driver module from kernel.

    Returns:
      The status code of modprobe result.
    """
    args_list = self._MakeArgsForRemoveModule()
    process = system_tools.SystemTools.RunInSubprocess('modprobe', *args_list)
    process_output = system_tools.SystemTools.GetSubprocessOutput(process)
    return self._CheckRemoveModuleResult(process_output)

  def _MakeArgsForRemoveModule(self):
    """Puts flags and arguments needed for removing module into a list.

    The list includes -v (--verbose) flag and --first-time flag, which makes the
    modprobe command fail if it does not in fact do anything.

    Returns:
      A list of arguments formatted for calling modprobe command to remove
        module.
    """
    args = self._modprobe_verbose_args
    args.append('-r')
    return args

  def _CheckRemoveModuleResult(self, process_output):
    """Checks result of remove module command.

    Args:
      process_output: A tuple (return_code, out, err) containing the return
        code, standard output and error message (if applicable) of the
        the subprocess spawned by the modprobe command to remove the driver
        module.

    Returns:
      The status code of modprobe result.

    Raises:
      USBControllerError if _is_modprobed returns True, meaning the driver was
        not successfully disabled by the remove module command.
    """
    return_code, out, err = process_output
    error_message = 'FATAL: Module %s is not in kernel.' % self._module
    if return_code == 0:
      if 'rmmod' in out and err == '':
        return self.MODPROBE_SUCCESS
      return self.MODPROBE_NO_ACTION
    if error_message in err:
      logging.warning('%s module is already removed from the kernel.',
                      self._module)
      return self.MODPROBE_DUPLICATED
    logging.error('Modprobe (rmmod) return code: %d', return_code)
    logging.error('Modprobe (rmmod) stdout: %s', out)
    logging.error('Modprobe (rmmod) error (if any): %s', err)
    logging.exception('Modprobe failed to remove %s module from kernel.',
                      self._module)
    raise USBControllerError('Driver failed to be disabled.')

  def EnableUSBOTGDriver(self):
    """Enables dwc2 driver so USB port can be controlled by Chameleon."""
    output = system_tools.SystemTools.Output('lsmod').splitlines()
    if any(line.startswith('dwc2') for line in output):
      logging.warning('Skip modprobe dwc2 because it has already enabled.')
    else:
      system_tools.SystemTools.Call('modprobe', 'dwc2')

  def DisableUSBOTGDriver(self):
    """Disables dwc2 driver so USB port does not get controlled by Chameleon."""
    system_tools.SystemTools.Call('modprobe', '-r', 'dwc2')

  def DetectDriver(self):
    """Detect if we have the USB module driver.

    We detect it by checking the module driver information.

    Returns:
      True for detecting success, False otherwise
    """
    # If the module is already loaded, just return True
    if self._is_modprobed:
      return True
    # Check if we have the module driver in system.
    # Use modinfo to check. If there is no such module in system, we will have
    # exception.
    try:
      system_tools.SystemTools.Call('modinfo', self._module)
      return True
    except Exception:
      logging.info('Try to modinfo %s fail', self._module)
      return False


class USBAudioController(USBController):
  """Provides interface to control USB audio driver.

  Properties:
    _driver_configs_to_set: A USBAudioDriverConfigs object used to store user-
                            set changes.
    _driver_configs_in_use: A USBAudioDriverConfigs object representing the
                            the configurations currently in use by the driver,
                            if it is successfully modprobed.
  """
  def __init__(self):
    """Initializes a USBAudioController object.

    _driver_configs_to_set is initially set to a USBAudioDriverConfigs object
    with default configurations.
    """
    self._driver_configs_to_set = usb_audio_configs.USBAudioDriverConfigs()
    self._driver_configs_in_use = None
    super(USBAudioController, self).__init__('g_audio')

  def EnableDriver(self):
    """Modprobes g_audio module with params from _driver_configs_to_set.

    If the user wishes to change the current configurations into
    _driver_configs_to_set, the user should disable the driver with
    DisableDriver() before changing the configurations via
    SetDriverPlaybackConfigs() or SetDriverCaptureConfigs(), and calling
    EnableDriver() again.

    Returns:
      The status code of modprobe result.

    Raises:
      USBControllerError if the driver was not successfully enabled.
    """
    try:
      status = super(USBAudioController, self).EnableDriver()
    except USBControllerError as e:
      self._driver_configs_in_use = None
      raise USBControllerError(e.message)
    if status == self.MODPROBE_SUCCESS:
      self._driver_configs_in_use = copy.deepcopy(self._driver_configs_to_set)
    return status

  def _MakeArgsForInsertModule(self):
    """Puts all relevant driver configs from _driver_configs_to_set into a list.

    Returns:
      A list of arguments formatted for calling modprobe command to insert
        module.
    """
    params_dict = self.\
                  _FormatDriverConfigsForModprobe(self._driver_configs_to_set)
    args_list = self._modprobe_verbose_args
    for key, value in params_dict.iteritems():
      if value is not None:
        item = key + '=' + str(value)
        args_list.append(item)
    return args_list

  def _FormatDriverConfigsForModprobe(self, driver_configs):
    """Converts configurations stored in driver_configs into modprobe arguments.

    Note that 'file_type' attribute in driver_configs is left out because it is
    not a relevant parameter for modprobing the driver module.

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

  def DisableDriver(self):
    """Removes the g_audio module from kernel and update configs.

    Returns:
      The status code of modprobe result.
    """
    status = super(USBAudioController, self).DisableDriver()
    if status in [self.MODPROBE_SUCCESS, self.MODPROBE_DUPLICATED]:
      self._driver_configs_in_use = None
    return status

  def GetSupportedPlaybackDataFormat(self):
    """Returns the playback data format as supported by the USB driver.

    Note that the 'file_type' attribute of the returned AudioDataFormat object
    is ignored and not actively managed by USBController.

    Returns:
      An AudioDataFormat object that stores the playback data format supported
        by the USB driver.
    """
    if not self._is_modprobed:
      error_message = ('Invalid Call: Supported format not applicable '
                       'since driver is not enabled.')
      raise USBControllerError(error_message)
    return self._driver_configs_in_use.GetPlaybackConfigs()

  def GetSupportedCaptureDataFormat(self):
    """Returns the capture data format as supported by the USB driver.

    Note that the 'file_type' attribute of the returned AudioDataFormat object
    is ignored and not actively managed by USBController.

    Returns:
      An AudioDataFormat object that stores the capture data format supported by
        the USB driver.
    """
    if not self._is_modprobed:
      error_message = ('Invalid Call: Supported format not applicable '
                       'since driver is not enabled.')
      raise USBControllerError(error_message)
    return self._driver_configs_in_use.GetCaptureConfigs()

  def SetDriverPlaybackConfigs(self, playback_configs):
    """Sets playback-related configs in _driver_configs_to_set.

    The driver will be disabled before the driver configurations are set. If the
    driver was initially enabled/modprobed, then the driver will be enabled
    again after configurations are set.

    The 'file_type' attribute of playback_configs is ignored by this class.

    Args:
      playback_configs: An AudioDataFormat object with playback configurations.
    """
    was_modprobed = self._is_modprobed
    self.DisableDriver()
    self._driver_configs_to_set.SetPlaybackConfigs(playback_configs)
    if was_modprobed:
      self.EnableDriver()

  def SetDriverCaptureConfigs(self, capture_configs):
    """Sets capture-related configs in _driver_configs_to_set.

    The driver will be disabled before the driver configurations are set. If the
    driver was initially enabled/modprobed, then the driver will be enabled
    again after configurations are set.

    The 'file_type' attribute of capture_configs is ignored by this class.

    Args:
      capture_configs: An AudioDataFormat object with capture configurations.
    """
    was_modprobed = self._is_modprobed
    self.DisableDriver()
    self._driver_configs_to_set.SetCaptureConfigs(capture_configs)
    if was_modprobed:
      self.EnableDriver()
