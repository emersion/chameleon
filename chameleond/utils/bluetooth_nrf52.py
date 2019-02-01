# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This module provides an abstraction of the Nordic nRF52 bluetooth low energy
kit.
"""

from __future__ import print_function

import logging
import time

import common
import serial_utils
from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_peripheral_kit import PeripheralKitException


class nRF52Exception(PeripheralKitException):
  """A dummy exception class for nRF52 class."""
  pass


class nRF52(PeripheralKit):
  """This is an abstraction of Nordic's nRF52 Dongle and the C application
     that implements BLE mouse and keyboard functionality.

     SDK: https://www.nordicsemi.com/Software-and-Tools/Software/nRF5-SDK

     See autotest-private/nRF52/ble_app_hids/README for information about
     using the SDK to compile the application.
  """

  # Serial port settings (override)
  BAUDRATE = 115200
  DRIVER = 'cdc_acm'
  # Driver name in udev is 'cdc_acm', but builtin module is 'cdc-acm.ko'
  # So we need to look for cdc_acm when searching by driver,
  # but looking in builtins requires searching by 'cdc-acm'.
  DRIVER_MODULE = 'cdc-acm'
  BAUDRATE = 115200
  USB_VID = '1d6b'
  USB_PID = '0002'

  # A newline can just be a '\n' to denote the end of a command
  NEWLINE = '\n'
  CMD_FS = ' '                                      # Command field separator

  # Supported device types
  MOUSE = 'MOUSE'
  KEYBOARD = 'KEYBOARD'

  RESET_SLEEP_SECS = 1

  # Mouse button constants
  MOUSE_BUTTON_LEFT_BIT = 1
  MOUSE_BUTTON_RIGHT_BIT = 2

  # Specific Commands
  # Reboot the nRF52
  CMD_REBOOT = "RBT"
  # Reset the nRF52 and erase all previous bonds
  CMD_FACTORY_RESET = "FRST"
  # Return the name that is sent in advertisement packets
  CMD_GET_ADVERTISED_NAME = "GN"
  # Return the nRF52 firmware version
  CMD_GET_FIRMWARE_VERSION = "GV"
  # Return the Bluetooth address of the nRF52
  CMD_GET_NRF52_MAC = "GM"
  # Return the address of the device connected (if there exists a connection)
  CMD_GET_REMOTE_CONNECTION_MAC = "GC"
  # Return the status of the nRF52's connection with a central device
  CMD_GET_CONNECTION_STATUS = "GS"

  # Return the type of device the HID service is set
  CMD_GET_DEVICE_TYPE = "GD"
  # Set the nRF52 HID service to mouse
  CMD_SET_MOUSE = "SM"
  # Set the nRF52 HID service to keyboard
  CMD_SET_KEYBOARD = "SK"
  # Start HID service emulation
  CMD_START_HID_EM = "START"
  # Start HID service emulation
  CMD_STOP_HID_EM = "STOP"
  # Start advertising with the current settings (HID type)
  CMD_START_ADVERTISING = "ADV"

  # Press (or clear) one or more buttons (left/right)
  CMD_MOUSE_BUTTON = "B"
  # Click the left and/or right button of the mouse
  CMD_MOUSE_CLICK = "C"
  # Move the mouse along x and/or y axis
  CMD_MOUSE_MOVE = "M"
  # Scrolling the mouse wheel up/down
  CMD_MOUSE_SCROLL = "S"

  def GetCapabilities(self):
    """What can this kit do/not do that tests need to adjust for?

    Returns:
      A dictionary from PeripheralKit.CAP_* strings to an appropriate value.
      See above (CAP_*) for details.
    """
    return {PeripheralKit.CAP_TRANSPORTS: [PeripheralKit.TRANSPORT_LE],
            PeripheralKit.CAP_HAS_PIN: False,
            PeripheralKit.CAP_INIT_CONNECT: False}

  def EnterCommandMode(self):
    """Make the kit enter command mode.

    The application on the nRF52 Dongle is always in command mode, so this
    method will just create a serial connection if necessary

    Returns:
      True if the kit successfully entered command mode.

    Raises:
      nRF52Exception if there is an error in creating the serial connection
    """
    if self._serial is None:
      self.CreateSerialDevice()
    if not self._command_mode:
      self._command_mode = True
    return True

  def LeaveCommandMode(self, force=False):
    """Make the kit leave command mode.

    As above, the nRF52 application is always in command mode.

    Args:
      force: True if we want to ignore potential errors and leave command mode
            regardless of those errors

    Returns:
      True if the kit successfully left command mode.
    """
    if self._command_mode or force:
      self._command_mode = False
    return True

  def Reboot(self):
    """Reboot the nRF52 Dongle.

    Does not erase the bond information.

    Returns:
      True if the kit rebooted successfully.
    """
    self.SerialSendReceive(self.CMD_REBOOT,
                           msg='rebooting nRF52')
    time.sleep(self.RESET_SLEEP_SECS)
    return True

  def FactoryReset(self):
    """Factory reset the nRF52 Dongle.

    Erase the bond information and reboot.

    Returns:
      True if the kit is reset successfully.
    """
    self.SerialSendReceive(self.CMD_FACTORY_RESET,
                           msg='factory reset nRF52')
    time.sleep(self.RESET_SLEEP_SECS)
    return True

  def GetAdvertisedName(self):
    """Get the name advertised by the nRF52.

    Returns:
      The device name that the application uses in advertising
    """
    return self.SerialSendReceive(self.CMD_GET_ADVERTISED_NAME,
                                  msg='getting advertised name')

  def GetFirmwareVersion(self):
    """Get the firmware version of the kit.

    This is useful for checking what features are supported if we want to
    support muliple versions of some kit.

    For nRF52, returns the Link Layer Version (8 corresponds to BT 4.2),
    Nordic Company ID (89), and Firmware ID (135).

    Returns:
      The firmware version of the kit.
    """
    return self.SerialSendReceive(self.CMD_GET_FIRMWARE_VERSION,
                                  msg='getting firmware version')

  def GetOperationMode(self):
    """Get the operation mode.

    This is master/slave in Bluetooth BR/EDR; the Bluetooth LE equivalent is
    central/peripheral. For legacy reasons, we call it MASTER or SLAVE only.
    Not all kits may support all modes.

    nRF52 only supports peripheral role

    Returns:
      The operation mode of the kit.
    """
    logging.debug('GetOperationMode is a NOP on nRF52')
    return "SLAVE"

  def SetMasterMode(self):
    """Set the kit to master/central mode.

    nRF52 application only acts as a peripheral

    Returns:
      True if master/central mode was set successfully.

    Raises:
      A kit-specific exception if master/central mode is unsupported.
    """
    error_msg = 'Failed to set master/central mode'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def SetSlaveMode(self):
    """Set the kit to slave/peripheral mode.

    Silently succeeds, because the nRF52 application is always a peripheral

    Returns:
      True if slave/peripheral mode was set successfully.

    Raises:
      A kit-specific exception if slave/peripheral mode is unsupported.
    """
    logging.debug('SetSlaveMode is a NOP on nRF52')
    return True

  def GetAuthenticationMode(self):
    """Get the authentication mode.

    This specifies how the device will authenticate with the DUT, for example,
    a PIN code may be used.

    Not supported on nRF52 application.

    Returns:
      None as the nRF52 does not support an Authentication mode.
    """
    logging.debug('GetAuthenticationMode is a NOP on nRF52')
    return None

  def SetAuthenticationMode(self, mode):
    """Set the authentication mode to the specified mode.

    If mode is PIN_CODE_MODE, implementations must ensure the default PIN
    is set by calling _SetDefaultPinCode() as appropriate.

    Not supported on nRF52 application.

    Args:
      mode: the desired authentication mode (specified in PeripheralKit)

    Returns:
      True if the mode was set successfully,

    Raises:
      A kit-specific exception if given mode is not supported.
    """
    error_msg = 'nRF52 does not support authentication mode'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def GetPinCode(self):
    """Get the pin code.

    Returns:
      A string representing the pin code,
      None if there is no pin code stored.
    """
    warn_msg = 'nRF52 does not support PIN code mode, no PIN exists'
    logging.warn(warn_msg)
    return None

  def SetPinCode(self, pin):
    """Set the pin code.

    Not support on nRF52 application.

    Returns:
      True if the pin code is set successfully,

    Raises:
      A kit-specifc exception if the pin code is invalid.
    """
    error_msg = 'nRF52 does not support PIN code mode'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def GetServiceProfile(self):
    """Get the service profile.

    Unrelated to HID for the nRF52 application, so ignore for now

    Returns:
      The service profile currently in use (as per constant in PeripheralKit)
    """
    logging.debug('GetServiceProfile is a NOP on nRF52')
    return "HID"

  def SetServiceProfileSPP(self):
    """Set SPP as the service profile.

    Unrelated to HID for the nRF52 application, so ignore for now

    Returns:
      True if the service profile was set to SPP successfully.

    Raises:
      A kit-specifc exception if unsuppported.
    """
    error_msg = 'Failed to set SPP service profile'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def SetServiceProfileHID(self):
    """Set HID as the service profile.

    nRF52 application only does HID at the moment. Silently succeeds

    Returns:
      True if the service profile was set to HID successfully.
    """
    logging.debug('SetServiceProfileHID is a NOP on nRF52')
    return True

  def GetLocalBluetoothAddress(self):
    """Get the address advertised by the nRF52, which is the MAC address.

    Address is returned as XX:XX:XX:XX:XX:XX

    Returns:
      The address of the nRF52 if successful or None if it fails
    """
    address = self.SerialSendReceive(self.CMD_GET_NRF52_MAC,
                                     msg='getting local MAC address')
    return address

  def GetRemoteConnectedBluetoothAddress(self):
    """Get the address of the device that is connected to the nRF52.

    Address is returned as XX:XX:XX:XX:XX:XX
    If not connected, nRF52 will return 00:00:00:00:00:00

    Returns:
      The address of the connected device or a null address if successful.
      None if the serial receiving fails
    """
    address = self.SerialSendReceive(self.CMD_GET_REMOTE_CONNECTION_MAC,
                                     msg='getting remote MAC address')
    if len(address) == 17:
      return address
    else:
      logging.error('remote connection address is invalid: %s', raw_address)
      return None

  def GetConnectionStatus(self):
    """Get whether the nRF52 is connected to another device.

    nRF52 returns a string 'INVALID' or 'CONNECTED'

    Returns:
      True if the nRF52 is connected to another device
    """
    result = self.SerialSendReceive(self.CMD_GET_CONNECTION_STATUS,
                                    msg = 'getting connection status')
    return result == 'CONNECTED'

  def EnableConnectionStatusMessage(self):
    """Enable the connection status message.

    On some kits, this is required to use connection-related methods.

    Not supported by the nRF52 application for now. This could be
    changed so that Connection Status Messages are sent by nRF52.

    Returns:
      True if enabling the connection status message successfully.
    """
    logging.debug('EnableConnectionStatusMessage is a NOP on nRF52')
    return True

  def DisableConnectionStatusMessage(self):
    """Disable the connection status message.

    Not supported by the nRF52 application for now. This could be
    changed so that Connection Status Messages are sent by nRF52.

    Returns:
      True if disabling the connection status message successfully.
    """
    logging.debug('DisableConnectionStatusMessage is a NOP on nRF52')
    return True

  def GetHIDDeviceType(self):
    """Get the HID device type.

    Returns:
      A string representing the HID device type
    """
    return self.SerialSendReceive(self.CMD_GET_DEVICE_TYPE,
                                  msg='getting HID device type')

  def SetHIDType(self, device_type):
    """Set HID type to the specified device type.

    Args:
      device_type: the HID type to emulate, from PeripheralKit
                   (MOUSE, KEYBOARD)

    Returns:
      True if successful

    Raises:
      A kit-specific exception if that device type is not supported.
    """
    if device_type == self.MOUSE:
      result = self.SerialSendReceive(self.CMD_SET_MOUSE,
                             msg='setting mouse as HID type')
      print(result)
    elif device_type == self.KEYBOARD:
      self.SerialSendReceive(self.CMD_SET_KEYBOARD,
                             msg='setting keyboard as HID type')
    else:
      msg = "Failed to set HID type, not supported: %s" % device_type
      logging.error(msg)
      raise nRF52Exception(msg)
    return True

  def GetClassOfService(self):
    """Get the class of service, if supported.

    Not supported on nRF52

    Returns:
      None, the only reasonable value for BLE-only devices
    """
    logging.debug('GetClassOfService is a NOP on nRF52')
    return None

  def SetClassOfService(self, class_of_service):
    """Set the class of service, if supported.

    The class of service is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Not supported on nRF52, but fake it

    Args:
      class_of_service: A decimal integer representing the class of service.

    Returns:
      True as this action is not supported.
    """
    logging.debug('SetClassOfService is a NOP on nRF52')
    return True

  def GetClassOfDevice(self):
    """Get the class of device, if supported.

    The kit uses a hexadeciaml string to represent the class of device.
    It is converted to a decimal number as the return value.
    The class of device is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Not supported on nRF52, so None

    Returns:
      None, the only reasonable value for BLE-only devices.
    """
    logging.debug('GetClassOfDevice is a NOP on nRF52')
    return None

  def SetClassOfDevice(self, device_type):
    """Set the class of device, if supported.

    The class of device is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Not supported on nRF52, but fake it.

    Args:
      device_type: A decimal integer representing the class of device.

    Returns:
      True as this action is not supported.
    """
    logging.debug('SetClassOfDevice is a NOP on nRF52')
    return True

  def SetRemoteAddress(self, remote_address):
    """Set the remote Bluetooth address.

    (Usually this will be the device under test that we want to connect with,
    where the kit starts the connection.)

    Not supported on nRF52 HID application.

    Args:
      remote_address: the remote Bluetooth MAC address, which must be given as
                      12 hex digits with colons between each pair.
                      For reference: '00:29:95:1A:D4:6F'

    Returns:
      True if the remote address was set successfully.

    Raises:
      PeripheralKitException if the given address was malformed.
    """
    error_msg = 'Failed to set remote address'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def Connect(self):
    """Connect to the stored remote bluetooth address.

    In the case of a timeout (or a failure causing an exception), the caller
    is responsible for retrying when appropriate.

    Not supported on nRF52 HID application.

    Returns:
      True if connecting to the stored remote address succeeded, or
      False if a timeout occurs.
    """
    error_msg = 'Failed to connect to remote device'
    logging.error(error_msg)
    raise nRF52Exception(error_msg)

  def Disconnect(self):
    """Disconnect from the remote device.

    Specifically, this causes the peripheral emulation kit to disconnect from
    the remote connected device, usually the DUT.

    Returns:
      True if disconnecting from the remote device succeeded.
    """
    self.SerialSendReceive(self.CMD_DISCONNECT,
                           msg='disconnect')
    return True

  def StartAdvertising(self):
    """Command the nRF52 to begin advertising with its current settings.

    Returns:
      True if successful.
    """
    self.SerialSendReceive(self.CMD_START_ADVERTISING,
                           msg='start advertising')
    return True

  def MouseMove(self, delta_x, delta_y):
    """Move the mouse (delta_x, delta_y) steps.

    Buttons currently pressed will stay pressed during this operation.
    This move is relative to the current position by the HID standard.
    Valid step values must be in the range [-127,127].

    Args:
      delta_x: The number of steps to move horizontally.
               Negative values move left, positive values move right.
      delta_y: The number of steps to move vertically.
               Negative values move up, positive values move down.

    Returns:
      True if successful.
    """
    command = self.CMD_MOUSE_MOVE + self.CMD_FS
    command += str(delta_x) + self.CMD_FS + str(delta_y)
    message = 'moving BLE mouse ' + str(delta_x) + " " + str(delta_y)
    result = self.SerialSendReceive(command, msg=message)
    return True

  def MouseScroll(self, steps):
    """Scroll the mouse wheel steps number of steps.

    Buttons currently pressed will stay pressed during this operation.
    Valid step values must be in the range [-127,127].

    Args:
      steps: The number of steps to scroll the wheel.
             With traditional scrolling:
               Negative values scroll down, positive values scroll up.
             With reversed (formerly "Australian") scrolling this is reversed.

    Returns:
      True if successful.
    """
    command = self.CMD_MOUSE_SCROLL + self.CMD_FS
    command += self.CMD_FS
    command += str(steps) + self.CMD_FS
    message = 'scrolling BLE mouse'
    result = self.SerialSendReceive(command, msg=message)
    return True

  def MouseHorizontalScroll(self, steps):
    """Horizontally scroll the mouse wheel steps number of steps.

    Buttons currently pressed will stay pressed during this operation.
    Valid step values must be in the range [-127,127].

    There is no nRF52 limitation for implementation. If we can program
    the correct HID event report to emulate horizontal scrolling, this
    can be supported.
    **** Not implemented ****
    Args:
      steps: The number of steps to scroll the wheel.
             With traditional scrolling:
               Negative values scroll left, positive values scroll right.
             With reversed (formerly "Australian") scrolling this is reversed.

    Returns:
      True if successful.
    """
    return True

  def _MouseButtonCodes(self):
    """Gives the letter codes for whatever buttons are pressed.

    Returns:
      A int w/ bits representing pressed buttons.
    """
    currently_pressed = 0
    for button in self._buttons_pressed:
      if button == PeripheralKit.MOUSE_BUTTON_LEFT:
        currently_pressed += self.MOUSE_BUTTON_LEFT_BIT
      elif button == PeripheralKit.MOUSE_BUTTON_RIGHT:
        currently_pressed += self.MOUSE_BUTTON_RIGHT_BIT
      else:
        error = "Unknown mouse button in state: %s" % button
        logging.error(error)
        raise nRF52Exception(error)
    return currently_pressed

  def MousePressButtons(self, buttons):
    """Press the specified mouse buttons.

    The kit will continue to press these buttons until otherwise instructed, or
    until its state has been reset.

    Args:
      buttons: A set of buttons, as PeripheralKit MOUSE_BUTTON_* values, that
               will be pressed (and held down).

    Returns:
      True if successful.
    """
    self._MouseButtonStateUnion(buttons)
    button_codes = self._MouseButtonCodes()
    command = self.CMD_MOUSE_BUTTON + self.CMD_FS
    command += str(button_codes)
    message = 'pressing BLE mouse buttons'
    result = self.SerialSendReceive(command, msg=message)
    return True

  def MouseReleaseAllButtons(self):
    """Release all mouse buttons.

    Returns:
      True if successful.
    """
    self._MouseButtonStateClear()
    command = self.CMD_MOUSE_BUTTON + self.CMD_FS
    command += '0'
    message = 'releasing all BLE HOG mouse buttons'
    result = self.SerialSendReceive(command, msg=message)
    return True

  def Reset(self):
    result = self.SerialSendReceive(nRF52.CMD_REBOOT, msg='reset nRF52')
    return True

  def SetModeMouse(self):
    self.EnterCommandMode()
    result = self.SerialSendReceive(nRF52.CMD_SET_MOUSE, msg='set nRF52 mouse')
    return True

  def GetKitInfo(self, connect_separately=False, test_reset=False):
    """A simple demo of getting kit information."""
    if connect_separately:
      print('create serial device: %s' % self.CreateSerialDevice())
    if test_reset:
      print('factory reset: %s' % self.FactoryReset())
    self.EnterCommandMode()
    print('advertised name: %s' % self.GetAdvertisedName())
    print('firmware version: %s' % self.GetFirmwareVersion())
    print('local bluetooth address: %s' % self.GetLocalBluetoothAddress())
    print('connection status: %s' % self.GetConnectionStatus())
    # The class of service/device is None for LE kits (it is BR/EDR-only)


if __name__ == '__main__':
  kit_instance = nRF52()
  kit_instance.GetKitInfo()
