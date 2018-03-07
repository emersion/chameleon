# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control USB driver module."""

import copy
import logging
import re

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import usb
from chameleond.utils import usb_printer_configs


class USBPrinterControllerError(usb.USBControllerError):
  """Exception raised when any error occurs in USBPrinterController."""
  pass


class USBPrinterController(usb.USBController):
  """Provides interface to control USB printer driver.

  Properties:
    _driver_configs_to_set: A USBPrinterDriverConfigs object used to store user-
                            set changes.
    _driver_configs_in_use: A USBPrinterDriverConfigs object representing the
                            the configurations currently in use by the driver,
                            if it is successfully modprobed.
  """
  def __init__(self):
    """Initializes a USBPrinterController object.

    _driver_configs_to_set is set to the config from a default printer model.
    """
    self._driver_configs_to_set = usb_printer_configs.USBPrinterDriverConfigs()
    self._driver_configs_to_set.SetDeviceInfo(
        DEFAULT_PRINTER_MODEL.GetDeviceInfoDict())
    self._driver_configs_in_use = None
    super(USBPrinterController, self).__init__('g_printer')

  def EnableDriver(self):
    """Modprobes g_printer module with params from _driver_configs_to_set.

    Returns:
      The status code of modprobe result.

    Raises:
      USBPrinterControllerError if the driver was not successfully enabled.
    """
    try:
      status = super(USBPrinterController, self).EnableDriver()
    except usb.USBControllerError as e:
      self._driver_configs_in_use = None
      raise USBPrinterControllerError(e.message)
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

    Args:
      driver_configs: A USBPrinterDriverConfigs object storing configurations to
                      be applied to the driver when enabled.

    Returns:
      A dictionary containing modprobe-appropriate parameters and their
      corresponding argument values derived from driver_configs.
    """
    device_info = driver_configs.GetDeviceInfoDict()

    params_dict = {
        'idVendor': device_info['vendor_id'],
        'idProduct': device_info['product_id'],
        'bcdDevice': device_info['bcd_device'],
        'iSerialNumber': device_info['serial_number'],
        'iManufacturer': device_info['manufacturer'],
        'iProduct': device_info['product'],
    }
    return params_dict

  def DisableDriver(self):
    """Removes the g_printer module from kernel and updates configs.

    Returns:
      The status code of modprobe result.
    """
    status = super(USBPrinterController, self).DisableDriver()
    if status in [self.MODPROBE_SUCCESS, self.MODPROBE_DUPLICATED]:
      self._driver_configs_in_use = None
    return status

  def SetPrinterModel(self, printer_model):
    """Sets configs in _driver_configs_to_set to emulate a printer model.

    The driver should be disabled before the driver configurations are set. If the
    driver was initially enabled/modprobed, then the driver will be enabled
    again after configurations are set.

    Args:
      printer_model: A PrinterModel object.
    """
    was_modprobed = self._is_modprobed
    self.DisableDriver()
    logging.info('Set printer model to %s', printer_model.name)
    self._driver_configs_to_set.SetDeviceInfo(printer_model.GetDeviceInfoDict())
    if was_modprobed:
      self.EnableDriver()

  def ResetPrinterModel(self):
    """Resets printer model to default one."""
    self.SetPrinterModel(DEFAULT_PRINTER_MODEL)


class PrinterModel(object):
  """The class that encapsulates the printer models."""
  def __init__(self, vendor_id=None, product_id=None, name=None):
    """Initializes a PrinterModel.

    Args:
      vendor_id: A number for vendor_id.
      product_id: A number for product_id.
      name: A string for name. This is only for debug purpose.
    """
    self.vendor_id = vendor_id
    self.product_id = product_id
    self.name = name

  def GetDeviceInfoDict(self):
    """Gets a dict containing device info.

    Returns:
      A dict containing 'vendor_id' and 'product_id'.
    """
    ret = {
        'vendor_id': self.vendor_id,
        'product_id': self.product_id,
        'product': self.name,
    }

    return ret


# Default values for printer model.
# Default vendor is HP.
# Default model is HP deskjet 895c.
DEFAULT_PRINTER_MODEL = PrinterModel(
    vendor_id=0x03f0,
    product_id=0x0004,
    name='HP deskjet 895c')
