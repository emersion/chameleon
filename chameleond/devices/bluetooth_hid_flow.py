# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The control interface of Bluetooth HID flow module driver."""

import logging

from chameleond.devices import chameleon_device
from chameleond.utils import serial_utils
from chameleond.utils.bluetooth_hid import BluetoothHID
from chameleond.utils.bluetooth_hid import BluetoothHIDMouse


class BluetoothHIDFlowError(Exception):
  """Exception raised when any error occurs in BluetoothHIDFlow."""
  pass


class BluetoothHIDFlow(chameleon_device.Flow):
  """The control interface of bluetooth HID flow module driver."""

  # the serial driver for chameleon to access the bluetooth emulation kit
  SERIAL_DRIVER = 'ftdi_sio'

  def __init__(self, port_id, connector_type, usb_ctrl):
    """Initializes a BluetoothHIDFlow object.

    Args:
      port_id: the port id that represents the type of port used.
      connector_type: the string obtained by GetConnectorType().
      usb_ctrl: a USBController object that BluetoothHIDFlow references to.
    """
    self._port_id = port_id
    self._connector_type = connector_type
    self._usb_ctrl = usb_ctrl
    self._tty = None
    super(BluetoothHIDFlow, self).__init__()

  # TODO(mojahsu): implement
  def IsDetected(self):
    """Returns if the device can be detected."""
    raise NotImplementedError('IsDetected')

  # TODO(mojahsu): implement
  def InitDevice(self):
    """Init the real device of chameleon board."""
    raise NotImplementedError('InitDevice')

  # TODO(mojahsu): implement
  def Reset(self):
    """Reset chameleon device."""
    raise NotImplementedError('Reset')

  def Initialize(self):
    """Enables Bluetooth HID port controller.

    Enables USB port device mode controller so USB host on the other side will
    not get confused when trying to enumerate this USB device.
    """
    self._usb_ctrl.EnableDriver()
    self._usb_ctrl.EnableUSBOTGDriver()
    logging.debug('Initialized Bluetooth HID flow #%d.', self._port_id)

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
    self._tty = serial_utils.FindTtyByDriver(self.SERIAL_DRIVER)
    return self._usb_ctrl.DriverIsEnabled() and bool(self._tty)

  def Plug(self):
    """Emulates plug by enabling the bluetooth hid serial driver."""
    logging.debug('Bluetooth HID flow #%d: Plug() called.', self._port_id)

  def Unplug(self):
    """Emulates unplug by disabling bluetooth hid serial driver.

    Do nothing for BlueoothHIDFlow.
    """
    logging.debug('Bluetooth HID flow #%d: Unplug() called.', self._port_id)

  def Disconnect(self):
    """Disconnect to the device by removing the serial driver."""
    self._usb_ctrl.DisableDriver()

  def DoFSM(self):
    """fpga_tio calls DoFSM after a flow is selected.

    Do nothing for BlueoothHIDFlow.
    """
    logging.debug('Bluetooth HID flow #%d: DoFSM() called.', self._port_id)


class BluetoothHIDMouseFlow(BluetoothHIDMouse, BluetoothHIDFlow):
  """A flow object that emulates a classic bluetooth mouse device."""

  def __init__(self, port_id, usb_ctrl):
    """Initializes a BluetoothHIDMouseFlow object.

    Args:
      port_id: the port id that represents the type of port used.
      usb_ctrl: a USBController object that BluetoothHIDFlow references to.
    """
    BluetoothHIDFlow.__init__(self, port_id, 'ClassicBluetoothMouse', usb_ctrl)
    BluetoothHIDMouse.__init__(self, BluetoothHID.PIN_CODE_MODE)

  # TODO(mojahsu): implement
  def IsDetected(self):
    """Returns if the device can be detected."""
    raise NotImplementedError('IsDetected')

  # TODO(mojahsu): implement
  def InitDevice(self):
    """Init the real device of chameleon board."""
    raise NotImplementedError('InitDevice')

  # TODO(mojahsu): implement
  def Reset(self):
    """Reset chameleon device."""
    raise NotImplementedError('Reset')
