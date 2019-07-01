# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module implements the PeripheralKit instance for a bluez peripheral
   on Raspberry Pi.
"""

from __future__ import print_function

import dbus
import dbus.mainloop.glib
import dbus.service
import logging
import os
import threading

# Libraries needed on raspberry pi. ImportError on
# Fizz can be ignored.
try:
  from gi.repository import GLib
except ImportError:
  pass

from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_peripheral_kit import PeripheralKitException

DBUS_BLUEZ_SERVICE_IFACE = 'org.bluez'
DBUS_BLUEZ_ADAPTER_IFACE = DBUS_BLUEZ_SERVICE_IFACE + '.Adapter1'
DBUS_BLUEZ_DEVICE_IFACE = DBUS_BLUEZ_SERVICE_IFACE + '.Device1'
BLUEZ_KEYBOARD_DEVICE_NAME = "KEYBD_REF"


class BluezPeripheralException(PeripheralKitException):
  """A dummpy exception class for Bluez class."""
  pass


class BluezPeripheral(PeripheralKit):
  """This is an abstraction of a Bluez peripheral."""

  def __init__(self):
    super(BluezPeripheral, self).__init__()
    self._settings = {}
    self._setup_dbus_loop()

    # Bluez DBus constants - npnext
    self._dbus_system_bus = dbus.SystemBus()
    self._dbus_hci_adapter_path = '/org/bluez/hci0'
    self._dbus_hci_props = dbus.Interface(self._dbus_system_bus.get_object(\
                                                            'org.bluez',\
                                                            '/org/bluez/hci0'),\
                                          'org.freedesktop.DBus.Properties')
    # Make sure device is powered up and discoverable
    self._dbus_hci_props.Set('org.bluez.Adapter1',
                             'Powered',
                             dbus.Boolean(1))
    self._dbus_hci_props.Set('org.bluez.Adapter1',
                             'Discoverable',
                             dbus.Boolean(1))
    logging.debug("Bluetooth adapter powered-up and discoverable")
    # Set device class and name. These are read-only DBus properties,
    # so need to be set using system calls.
    os.system("sudo hciconfig hci0 class 0x002540")
    os.system("bluetoothctl > /dev/null << EOF \n system-alias " +
              BLUEZ_KEYBOARD_DEVICE_NAME +
              "\n quit \n EOF")
    logging.debug("Bluetooth adapter name %s" % BLUEZ_KEYBOARD_DEVICE_NAME)


  def _setup_dbus_loop(self):
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    self._loop = GLib.MainLoop()
    self._thread = threading.Thread(target=self._loop.run)
    self._thread.start()


  def GetCapabilities(self):
    """What can this kit do/not do that tests need to adjust for?

    Returns:
      A dictionary from PeripheralKit.CAP_* strings to an appropriate value.
      See PeripheralKit for details.
    """
    return {PeripheralKit.CAP_TRANSPORTS: [PeripheralKit.TRANSPORT_BREDR],
            PeripheralKit.CAP_HAS_PIN: True,
            PeripheralKit.CAP_INIT_CONNECT: True}


  def EnterCommandMode(self):
    raise NotImplementedError("Not Implemented")


  def LeaveCommandMode(self, force=False):
    raise NotImplementedError("Not Implemented")


  def Reboot(self):
    raise NotImplementedError("Not Implemented")


  def FactoryReset(self):
    raise NotImplementedError("Not Implemented")


  def GetAdvertisedName(self):
    """Get the name advertised by the kit.

    Returns:
      The name that the kit advertises to other Bluetooth devices.
    """
    return self._dbus_hci_props.Get('org.bluez.Adapter1', 'Alias')


  def GetFirmwareVersion(self):
    raise NotImplementedError("Not Implemented")


  def GetOperationMode(self):
    raise NotImplementedError("Not Implemented")


  def SetMasterMode(self):
    raise NotImplementedError("Not Implemented")


  def SetSlaveMode(self):
    raise NotImplementedError("Not Implemented")


  def GetAuthenticationMode(self):
    raise NotImplementedError("Not Implemented")


  def SetAuthenticationMode(self, mode):
    raise NotImplementedError("Not Implemented")


  def GetPinCode(self):
    raise NotImplementedError("Not Implemented")


  def SetPinCode(self, pin):
    raise NotImplementedError("Not Implemented")


  def GetServiceProfile(self):
    raise NotImplementedError("Not Implemented")


  def SetServiceProfileSPP(self):
    raise NotImplementedError("Not Implemented")


  def SetServiceProfileHID(self):
    raise NotImplementedError("Not Implemented")


  def GetLocalBluetoothAddress(self):
    """Get the builtin Bluetooth MAC address.

    If the HCI device doesn't exist, Get() will throw an exception
    (dbus.exceptions.DBus.Error.UnknownObject)
    """
    try:
      addr = self._dbus_hci_props.Get('org.bluez.Adapter1', 'Address')
    except:
      addr = None
    return addr


  def GetConnectionStatus(self):
    raise NotImplementedError("Not Implemented")


  def EnableConnectionStatusMessage(self):
    raise NotImplementedError("Not Implemented")


  def DisableConnectionStatusMessage(self):
    raise NotImplementedError("Not Implemented")


  def GetRemoteConnectedBluetoothAddress(self):
    raise NotImplementedError("Not Implemented")


  def GetHIDDeviceType(self):
    raise NotImplementedError("Not Implemented")


  def SetHIDType(self, device_type):
    raise NotImplementedError("Not Implemented")


  def GetClassOfService(self):
    return self._dbus_hci_props.Get('org.bluez.Adapter1', 'Class')


  def SetClassOfService(self, class_of_service):
    raise NotImplementedError("Not Implemented")


  def GetClassOfDevice(self):
    return self.GetClassOfService()


  def _SetClassOfDevice(self, class_of_device):
    raise NotImplementedError("Not Implemented")


  def SetClassOfDevice(self, device_type):
    raise NotImplementedError("Not Implemented")


  def SetRemoteAddress(self, remote_address):
    raise NotImplementedError("Not Implemented")


  def Connect(self):
    raise NotImplementedError("Not Implemented")


  def Disconnect(self):
    raise NotImplementedError("Not Implemented")


# (TODO) - revisit these functions upto _MouseButtonsRawHidValues
  def _CheckValidModifiers(self, modifiers):
    invalid_modifiers = [m for m in modifiers if m not in self.MODIFIERS]
    if invalid_modifiers:
      logging.error('Modifiers not valid: "%s".', str(invalid_modifiers))
      return False
    return True


  def _IsValidScanCode(self, code):
    """Check if the code is a valid scan code.

    Args:
      code: the code to check

    Returns:
      True: if the code is a valid scan code.
    """
    return (self.SCAN_NO_EVENT <= code <= self.SCAN_PAUSE or
            self.SCAN_SYSTEM_POWER <= code <= self.SCAN_SYSTEM_WAKE)


  def _CheckValidScanCodes(self, keys):
    invalid_keys = [k for k in keys if not self._IsValidScanCode(k)]
    if invalid_keys:
      logging.error('Keys not valid: "%s".', str(invalid_keys))
      return False
    return True


  def RawKeyCodes(self, modifiers=None, keys=None):
    """Generate the codes in raw keyboard report format.

    This method sends data in the raw report mode. The first start
    byte chr(UART_INPUT_RAW_MODE) is stripped and the following bytes
    are sent without interpretation.

    For example, generate the codes of 'shift-alt-i' by
      codes = RawKeyCodes(modifiers=[RasPi.LEFT_SHIFT, RasPi.LEFT_ALT],
                          keys=[RasPi.SCAN_I])

    Args:
      modifiers: a list of modifiers
      keys: a list of scan codes of keys

    Returns:
      a raw code string if both modifiers and keys are valid, or
      None otherwise.
    """
    modifiers = modifiers or []
    keys = keys or []

    if not (self._CheckValidModifiers(modifiers) and
            self._CheckValidScanCodes(keys)):
      return None

    real_scan_codes = map(chr, keys)
    padding_0s = (chr(0) * (self.RAW_REPORT_FORMAT_KEYBOARD_LEN_SCAN_CODES -
                            len(real_scan_codes)))

    return (chr(self.UART_INPUT_RAW_MODE) +
            chr(self.RAW_REPORT_FORMAT_KEYBOARD_LENGTH) +
            chr(self.RAW_REPORT_FORMAT_KEYBOARD_DESCRIPTOR) +
            chr(sum(modifiers)) +
            chr(0x0) +
            ''.join(real_scan_codes) +
            padding_0s)


  def _MouseButtonsRawHidValues(self):
    """Gives the raw HID values for whatever buttons are pressed."""
    currently_pressed = 0x0
    for button in self._buttons_pressed:
      if button == PeripheralKit.MOUSE_BUTTON_LEFT:
        currently_pressed |= self.RAW_HID_LEFT_BUTTON
      elif button == PeripheralKit.MOUSE_BUTTON_RIGHT:
        currently_pressed |= self.RAW_HID_RIGHT_BUTTON
      else:
        error = "Unknown mouse button in state: %s" % button
        logging.error(error)
        raise BluezPeripheralException(error)
    return currently_pressed


  def MouseMove(self, delta_x, delta_y):
    """Move the mouse (delta_x, delta_y) steps.

    If buttons are being pressed, they will stay pressed during this operation.
    This move is relative to the current position by the HID standard.
    Valid step values must be in the range [-127,127].

    Args:
      delta_x: The number of steps to move horizontally.
               Negative values move left, positive values move right.
      delta_y: The number of steps to move vertically.
               Negative values move up, positive values move down.
    """
    raw_buttons = self._MouseButtonsRawHidValues()
    if delta_x or delta_y:
      mouse_codes = self._RawMouseCodes(buttons=raw_buttons, x_stop=delta_x,
                                        y_stop=delta_y)
      self.SerialSendReceive(mouse_codes, msg='BluezPeripheral: MouseMove')


  def MouseScroll(self, steps):
    """Scroll the mouse wheel steps number of steps.

    Buttons currently pressed will stay pressed during this operation.
    Valid step values must be in the range [-127,127].

    Args:
      steps: The number of steps to scroll the wheel.
             With traditional scrolling:
               Negative values scroll down, positive values scroll up.
             With reversed (formerly "Australian") scrolling this is reversed.
    """
    raw_buttons = self._MouseButtonsRawHidValues()
    if steps:
      mouse_codes = self._RawMouseCodes(buttons=raw_buttons, wheel=steps)
      self.SerialSendReceive(mouse_codes, msg='BluezPeripheral: MouseScroll')


  def MousePressButtons(self, buttons):
    """Press the specified mouse buttons.

    The kit will continue to press these buttons until otherwise instructed, or
    until its state has been reset.

    Args:
      buttons: A set of buttons, as PeripheralKit MOUSE_BUTTON_* values, that
               will be pressed (and held down).
    """
    self._MouseButtonStateUnion(buttons)
    raw_buttons = self._MouseButtonsRawHidValues()
    if raw_buttons:
      mouse_codes = self._RawMouseCodes(buttons=raw_buttons)
      self.SerialSendReceive(mouse_codes, msg='BluezPeripheral: MousePressButtons')


  def MouseReleaseAllButtons(self):
    """Release all mouse buttons."""
    self._MouseButtonStateClear()
    mouse_codes = self._RawMouseCodes(buttons=self.RAW_HID_BUTTONS_RELEASED)
    self.SerialSendReceive(mouse_codes, msg='BluezPeripheral: MouseReleaseAllButtons')


  def _RawMouseCodes(self, buttons=0, x_stop=0, y_stop=0, wheel=0):
    """Generate the codes in mouse raw report format.

    This method sends data in the raw report mode. The first start
    byte chr(UART_INPUT_RAW_MODE) is stripped and the following bytes
    are sent without interpretation.

    For example, generate the codes of moving cursor 100 pixels left
    and 50 pixels down:
      codes = _RawMouseCodes(x_stop=-100, y_stop=50)

    Args:
      buttons: the buttons to press and release
      x_stop: the pixels to move horizontally
      y_stop: the pixels to move vertically
      wheel: the steps to scroll

    Returns:
      a raw code string.
    """
    def SignedChar(value):
      """Converted the value to a legitimate signed character value.

      Given value must be in [-127,127], or odd things will happen.

      Args:
        value: a signed integer

      Returns:
        a signed character value
      """
      if value < 0:
        # Perform two's complement.
        return value + 256
      return value

    return (chr(self.UART_INPUT_RAW_MODE) +
            chr(self.RAW_REPORT_FORMAT_MOUSE_LENGTH) +
            chr(self.RAW_REPORT_FORMAT_MOUSE_DESCRIPTOR) +
            chr(SignedChar(buttons)) +
            chr(SignedChar(x_stop)) +
            chr(SignedChar(y_stop)) +
            chr(SignedChar(wheel)))


  def PressShorthandCodes(self, modifiers=None, keys=None):
    """Generate key press codes in shorthand report format.

    Only key press is sent. The shorthand mode is useful in separating the
    key press and key release events.

    For example, generate the codes of 'shift-alt-i' by
      codes = PressShorthandCodes(modifiers=[RasPi.LEFT_SHIFT, RasPi.LEFT_ALT],
                                  keys=[RasPi_I])

    Args:
      modifiers: a list of modifiers
      keys: a list of scan codes of keys

    Returns:
      a shorthand code string if both modifiers and keys are valid, or
      None otherwise.
    """
    modifiers = modifiers or []
    keys = keys or []

    if not (self._CheckValidModifiers(modifiers) and
            self._CheckValidScanCodes(keys)):
      return None

    if len(keys) > self.SHORTHAND_REPORT_FORMAT_KEYBOARD_MAX_LEN_SCAN_CODES:
      return None

    return (chr(self.UART_INPUT_SHORTHAND_MODE) +
            chr(len(keys) + 1) +
            chr(sum(modifiers)) +
            ''.join(map(chr, keys)))


  def ReleaseShorthandCodes(self):
    """Generate the shorthand report format code for key release.

    Key release is sent.

    Returns:
      a special shorthand code string to release any pressed keys.
    """
    return chr(self.UART_INPUT_SHORTHAND_MODE) + chr(0x0)


  def GetKitInfo(self):
    """A simple demo of getting kit information."""
    print ('advertised name: %s' % self.GetAdvertisedName())
    print ('local bluetooth address: %s' % self.GetLocalBluetoothAddress())
    class_of_service = self.GetClassOfService()
    try:
      class_of_service = hex(class_of_service)
    except TypeError:
      pass
    print ('Class of service: %s' % class_of_service)
    class_of_device = self.GetClassOfDevice()
    try:
      class_of_device = hex(class_of_device)
    except TypeError:
      pass
    print ('Class of device: %s' % class_of_device)


if __name__ == '__main__':
  kit_instance = BluezPeripheral()
  kit_instance.GetKitInfo()
