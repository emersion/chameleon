# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The control interface of USB printer exposed to chameleond user."""

import logging
import os
import tempfile

from chameleond.devices import chameleon_device
from chameleond.utils import system_tools
from chameleond.utils import usb_printer_control


class USBPrinterError(Exception):
  """Exception raised when any error occurs in USBPrinter."""
  pass


class USBPrinter(object):
  """The control interface of USB printer module driver."""

  def __init__(self, usb_ctrl):
    """Initializes a USBPrinter object.

    Args:
      usb_ctrl: A USBPrinterController object that USBPrinter keep
                reference to.
    """
    self._usb_ctrl = usb_ctrl
    self._subprocess = None

  def IsDetected(self):
    """Returns if the device can be detected."""
    return self._usb_ctrl.DetectDriver()

  def InitDevice(self):
    """Enables USB port controller.

    Enables USB port device mode controller so USB host on the other side will
    not get confused when trying to enumerate this USB device.
    """
    self._usb_ctrl.EnableUSBOTGDriver()
    logging.info('Initialized USB device mode for printer')

  @property
  def _subprocess_is_running(self):
    """The subprocess spawned for running a command is running.

    Returns:
      True if subprocess has yet to return a result.
      False if there is no subprocess spawned yet, or if the subprocess has
        returned a value.
    """
    if self._subprocess is None:
      return False

    elif self._subprocess.poll() is None:
      return True

    else:
      return False

  @property
  def is_capturing_printer_data(self):
    """USBPrinter is capturing printer data from USB Host.

    Returns:
      True if USBPrinter is capturing printer data.
    """
    return self._subprocess_is_running

  def StartCapturingPrinterData(self):
    """Starts capturing printer data.

    Raises:
      USBPrinterError: If printer is not plugged.
    """
    if not self.IsPlugged():
      raise USBPrinterError('Should start capturing printer data after plug.')

    recorded_file = tempfile.NamedTemporaryFile(prefix='printer_',
                                                suffix='.raw',
                                                delete=False)
    self._file_path = recorded_file.name
    self._file_handle = open(self._file_path, 'w')
    self._subprocess = system_tools.SystemTools.RunInSubprocessOutputToFile(
        'printer', self._file_handle, '-read_data')
    logging.info('Started capturing printer data to %s', self._file_path)

  def StopCapturingPrinterData(self):
    """Stops capturing printer data.

    Returns:
      The path to the captured printer data.

    Raises:
      USBPrinterError if this is called before StartCapturingPrinterData()
      is called.
    """
    if self._subprocess is None:
      raise USBPrinterError('Stop capturing printer data before start.')

    elif self._subprocess.poll() is None:
      self._subprocess.terminate()
      logging.info('Stopped capturing printer data.')

    else:
      raise USBPrinterError('Printer capturing process stopped unexpectedly')

    self._subprocess = None
    self._file_handle.close()
    return self._file_path

  def Reset(self):
    """Resets USBPrinter.

    Stops capturing. Set printer model to the default model.
    """
    if self.is_capturing_printer_data:
      self.StopCapturingPrinterData()
    self._usb_ctrl.ResetPrinterModel()

  def IsPlugged(self):
    """Returns a Boolean value reflecting the status of USB printer driver.

    Returns:
      True if USB printer gadget driver is enabled. False otherwise.
    """
    return self._usb_ctrl.DriverIsEnabled()

  def Plug(self):
    """Emulates plug for USB printer by enabling printer gadget driver."""
    self._usb_ctrl.EnableDriver()

  def Unplug(self):
    """Emulates unplug for USB printer by disabling printer gadget driver."""
    self._usb_ctrl.DisableDriver()

  def SetPrinterModel(self, vendor_id, product_id, name):
    """Sets printer model with vendor_id, product_id, and name.

    Args:
      vendor_id: A number for vendor_id.
      product_id: A number for product_id.
      name: A name for printer product name.

    Raises:
      USBPrinterError if it is capturing printer data.
    """
    if self.is_capturing_printer_data:
      raise USBPrinterError('Can not set printer model while capturing')

    printer_model = usb_printer_control.PrinterModel(vendor_id, product_id, name)
    self._usb_ctrl.SetPrinterModel(printer_model)
