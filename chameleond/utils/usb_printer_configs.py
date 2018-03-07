# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the configuration needed for USB printer driver"""

class USBPrinterDriverConfigs(object):
  """The class that encapsulates the parameters of USB printer driver."""

  # Default manufacturer is set to Chameleon so it is easy to be identified.
  # On DUT printer menu, this printer will be identified as
  # "Chameleon <product> (USB)"
  # where product can be set in driver config.
  _DEFAULT_MANUFACTURER = 'Chameleon'

  def __init__(self):
    """Initializes a config object with default values.

    Default values are specified in the class variables above.
    """
    self._device_info = {
        'vendor_id': None,
        'product_id': None,
        'bcd_device': None,
        'serial_number': None,
        'manufacturer': self._DEFAULT_MANUFACTURER,
        'product': None,
    }

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
