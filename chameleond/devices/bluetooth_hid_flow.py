# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The control interface of Bluetooth HID flow module driver."""

import logging
import subprocess

from chameleond.devices import chameleon_device
from chameleond.utils import common
from chameleond.utils import serial_utils
from chameleond.utils import system_tools
from chameleond.utils.bluetooth_bluefruitle import BluefruitLE
from chameleond.utils.bluetooth_hid import BluetoothHIDMouse
from chameleond.utils.bluetooth_peripheral_kit import PeripheralKit
from chameleond.utils.bluetooth_rn42 import RN42


class BluetoothHIDFlow(chameleon_device.Flow):
  """The control interface of bluetooth HID flow module driver."""

  # Subclasses must override this DRIVER attribute
  DRIVER = None

  # TODO(crbug.com/763504): Can we lower detection time? Or maybe wait longer
  # only when enabling the driver the first time, since the first detect was
  # timing out.
  # NOTE: This timeout was increased because the first detection after
  # enabling the driver was taking too long. This may increase startup times
  # by ~10+ seconds on Chameleons without a Bluetooth kit.
  DETECT_TIMEOUT_SECS = 5  # the timeout in detection
  DETECT_INTERVAL_SECS = 1  # the time to wait before retrying in detection

  def __init__(self, port_id, connector_type, usb_ctrl, kit_vid_hex,
               kit_pid_hex):
    """Initializes a BluetoothHIDFlow object.

    Args:
      port_id: the port id that represents the type of port used.
      connector_type: the string obtained by GetConnectorType().
      usb_ctrl: a USBController object that BluetoothHIDFlow references to.
      serial_driver: the serial driver name for the kit
      kit_vid_hex: The USB VID (Vendor ID) of the kit, as a hexadecimal string
      kit_pid_hex: The USB PID (Product ID) of the kit, as a hexadecimal string
    """
    self._port_id = port_id
    self._connector_type = connector_type
    self._usb_ctrl = usb_ctrl
    self._tty = None
    self._kit_vid_hex = kit_vid_hex
    self._kit_pid_hex = kit_pid_hex
    super(BluetoothHIDFlow, self).__init__()

  def _FindAndSetTty(self):
    self._tty = serial_utils.FindTtyByUsbVidPid(self._kit_vid_hex,
                                                self._kit_pid_hex,
                                                driver_name=self.DRIVER)
    return self._tty

  def IsUSBHostMode(self):
    """Check if the platform is in USB host mode.

    Returns:
      True if the platform is in USB host mode; otherwise, False.
    """
    try:
      pci_info = system_tools.SystemTools.Output('lspci', '-v')
    except subprocess.CalledProcessError:
      logging.info('Failed to use lspci')
      return False

    for line in pci_info.splitlines():
      if 'xhci_hcd' in line:
        logging.info('USB host mode: %s', line)
        return True

    logging.info('Not in USB host mode')
    return False

  def IsDetected(self):
    """Returns if the device can be detected."""

    # Enables Bluetooth HID port controller.
    # If the platform is 'chromeos' which always acts in the USB host mode,
    # there is no need to enable the USB OTG driver.
    if not self.IsUSBHostMode():
      self._usb_ctrl.EnableUSBOTGDriver()
    self._usb_ctrl.EnableDriver()
    # Our Bluetooth HID flow differs substantially from other flows.
    # Everything needed for IsDetected does the job of InitDevice:
    # Initialize a TTY, and report detecting it instead of a driver.
    # (Other USB flows simulate Plug/Unplug by Enabling/Diabling the driver.)
    # Ultimately, this is reasonable given that we expect the kit to stay
    # plugged in to chameleon, but Plug/Unplug for resetting the USB device
    # might be useful.
    # TODO(josephsih): Investigate plug/unplug for the Bluetooth HID Flow.
    try:
      common.WaitForCondition(lambda: bool(self._FindAndSetTty()), True,
                              self.DETECT_INTERVAL_SECS,
                              self.DETECT_TIMEOUT_SECS)
      return True
    except common.TimeoutError:
      logging.warn("Did not detect bluetooth kit for %s before timing out.",
                   self.__class__.__name__)
      return False

  def InitDevice(self):
    """Init the tty of the kit attached to the chameleon board."""
    logging.debug("InitDevice in Bluetooth HID Flow #%d is a no-op.",
                  self._port_id)

  def Reset(self):
    """Reset chameleon device.

    Do nothing for BlueoothHIDFlow.
    """
    logging.debug('Bluetooth HID flow #%d: Reset() called.', self._port_id)

  def Select(self):
    """Selects the USB HID flow."""
    logging.debug('Selected Bluetooth HID flow #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return self._connector_type

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged.

    Always returns True.
    """
    logging.debug('Bluetooth HID flow #%d: IsPhysicalPlugged() called.',
                  self._port_id)
    return True

  def IsPlugged(self):
    """Returns a Boolean value about the status of bluetooth hid serial driver.

    Returns:
      True if Bluetooth hid serial driver is enabled and the tty is found.
      False otherwise.
    """
    return self._usb_ctrl.DriverIsEnabled() and bool(self._tty)

  def Plug(self):
    """Emulates plug by enabling the bluetooth hid serial driver."""
    logging.debug('Bluetooth HID flow #%d: Plug() called.', self._port_id)

  def Unplug(self):
    """Emulates unplug by disabling bluetooth hid serial driver.

    Do nothing for BlueoothHIDFlow.
    """
    logging.debug('Bluetooth HID flow #%d: Unplug() called.', self._port_id)

  def DoFSM(self):
    """fpga_tio calls DoFSM after a flow is selected.

    Do nothing for BlueoothHIDFlow.
    """
    logging.debug('Bluetooth HID flow #%d: DoFSM() called.', self._port_id)


class BluetoothHIDMouseFlow(BluetoothHIDFlow, BluetoothHIDMouse):
  """A flow object that emulates a Bluetooth BR/EDR mouse device."""

  DRIVER = RN42.DRIVER

  def __init__(self, port_id, usb_ctrl):
    """Initializes a BluetoothHIDMouseFlow object.

    Args:
      port_id: the port id that represents the type of port used.
      usb_ctrl: a USBController object that BluetoothHIDFlow references to.
    """
    BluetoothHIDFlow.__init__(self, port_id, 'BluetoothBR/EDR', usb_ctrl,
                              RN42.USB_VID, RN42.USB_PID)
    # TODO(josephsih): Ideally constants at this level of Bluetooth abstraction
    # should be in BluetoothHID*, but that doesn't currently work due to cyclic
    # imports. Remove this when constants are moved to BluetoothHID.
    BluetoothHIDMouse.__init__(self, PeripheralKit.PIN_CODE_MODE, RN42)


class BluetoothHOGMouseFlow(BluetoothHIDFlow, BluetoothHIDMouse):
  """A flow object that emulates a Bluetooth Low Energy mouse device."""

  DRIVER = BluefruitLE.DRIVER

  def __init__(self, port_id, usb_ctrl):
    """Initializes a BluetoothHOGMouseFlow object.

    (HOG meaning HID over GATT)

    Args:
      port_id: the port id that represents the type of port used.
      usb_ctrl: a USBController object that BluetoothHOGFlow references to.
    """
    BluetoothHIDFlow.__init__(self, port_id, 'BluetoothLEMouse', usb_ctrl,
                              BluefruitLE.USB_VID, BluefruitLE.USB_PID)
    BluetoothHIDMouse.__init__(self, PeripheralKit.SSP_JUST_WORK_MODE,
                               BluefruitLE)
