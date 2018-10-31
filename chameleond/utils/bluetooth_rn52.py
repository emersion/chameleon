# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides an abstraction of the RN-52 bluetooth chip."""

from __future__ import print_function

import logging
import time

import common
from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_peripheral_kit import PeripheralKitException

class RN52Exception(PeripheralKitException):
  """A dummpy exception class for RN52 class."""
  pass


class RN52(PeripheralKit):
  """This is an abstraction of Roving Network's RN-52 bluetooth evaluation kit.

  RN-52 supports SPP and HID protocols. The primary use case is to
  configure it to use the HID protocol to emulate a keyboard, a mouse,
  or a combo of both.

  For the RN-52 Evaluation Kit User's Guide, refer to
  http://ww1.microchip.com/downloads/en/DeviceDoc/50002153A.pdf

  For more information about the RN-52 Bluetooth Module, refer to the
  Command Reference and User's Guide at
  http://ww1.microchip.com/downloads/en/DeviceDoc/50002154A.pdf
  """

  # Serial port settings (override)
  DRIVER = 'ftdi_sio'
  BAUDRATE = 115200
  USB_VID = '0403'
  USB_PID = '6001'

  CHIP_NAME = 'RNBT'
  MAX_PIN_LEN = 20
  DEFAULT_PIN_CODE = '1234'     # The default factory pin code.
  # TODO(josephsih): Improve timing values, find/describe source thereof
  CONNECTION_TIMEOUT_SECS = 10  # the connection timeout in seconds
  POST_CONNECTION_WAIT_SECS = 1 # waiting time for a connection to become stable
  REBOOT_SLEEP_SECS = 3         # the time to sleep after reboot.
  RESET_SLEEP_SECS = 1          # the time to sleep after factory reset.
  SET_PIN_CODE_SLEEP_SECS = 0.5 # the time to sleep after setting pin code.

  # Response status
  AOK = 'AOK'                 # Acknowledge OK
  INVALID = 'ERR'             # Invalid command
  UNKNOWN = '?'               # Unrecognized command

  # basic chip operations
  CMD_REBOOT = 'R,1'
  CMD_FACTORY_RESET = 'SF,1'
  CMD_GET_BASIC_SETTINGS = 'D'

  # chip basic information
  CMD_GET_ADVERTISED_NAME = 'GN'
  CMD_GET_FIRMWARE_VERSION = 'V'

  # authentication mode
  CMD_GET_AUTHENTICATION_MODE = 'GA'
  CMD_SET_AUTHENTICATION_MODE = 'SA,'

  # pin code
  CMD_GET_PIN_CODE = 'GP'
  CMD_SET_PIN_CODE = 'SP,'

  # bluetooth mac address and connection
  CMD_GET_RN52_BLUETOOTH_MAC = 'GB'
  CMD_GET_CONNECTION_STATUS = 'Q'

  # Class of Service/Device
  # RN52 sets/gets class-of-service + class-of-device in single COD field
  CMD_GET_CLASS_OF_SERVICE = 'GC'
  CMD_SET_CLASS_OF_SERVICE = 'SC,'

  # Disconnect A2DP.
  CMD_DISCONNECT_A2DP = 'K,04'

  """ Other constants """
  CONNECTION_STRING = {
      '0000': 'not connected',
      '0001': 'iAP active connection',
      '0002': 'SPP active connection',
      '0004': 'A2DP active connection',
      '0008': 'HFP/HSP active connection'
  }
  AUTHENTICATION_MODE = {
      PeripheralKit.OPEN_MODE: '0',
      PeripheralKit.SSP_KEYBOARD_MODE: '1',
      PeripheralKit.SSP_JUST_WORK_MODE: '2',
      PeripheralKit.PIN_CODE_MODE: '4'
  }

  # Map abstract authentication mode to decimal number
  REV_AUTHENTICATION_MODE = {v: k for k, v in AUTHENTICATION_MODE.iteritems()}


  def __init__(self):
    super(RN52, self).__init__()
    self._settings = {}

  def __del__(self):
    super(RN52, self).__del__()

  def GetCapabilities(self):
    """What can this kit do/not do that tests need to adjust for?

    Returns:
      A dictionary from PeripheralKit.CAP_* strings to an appropriate value.
      See PeripheralKit for details.
    """
    return {PeripheralKit.CAP_TRANSPORTS: [PeripheralKit.TRANSPORT_BREDR],
            PeripheralKit.CAP_HAS_PIN: True,
            PeripheralKit.CAP_INIT_CONNECT: True}

  def GetBasicSettings(self):
    """Get basic information about the RN52 configuration

    Returns:
      True if successfully connected to serial device and _settings{} populated
    """
    if self._serial is None:
        self.CreateSerialDevice()
        if not self._serial._serial.isOpen():
          self._serial._
    if not self._settings:
      self._settings = (dict(setting.split('=') for setting in
                             self.SerialSendReceive(
                                 self.CMD_GET_BASIC_SETTINGS,
                                 msg='getting basic RN-52 settings').
                             splitlines()[1:]))
    return True

  def Reboot(self):
    """Reboot (or partially reset) the chip.

    On the RN52 kit, this does not reset the pairing info.

    Returns:
      True if the kit rebooted successfully.
    """
    self.SerialSendReceive(self.CMD_REBOOT,
                           expect_in='Reboot',
                           msg='rebooting RN-52')
    time.sleep(self.REBOOT_SLEEP_SECS)
    return True

  def FactoryReset(self):
    """Factory reset the chip.

    Reset the chip to the factory defaults.

    Returns:
      True if the kit is reset successfully.
    """
    self.SerialSendReceive(self.CMD_FACTORY_RESET,
                           msg='factory reset RN-52')
    time.sleep(self.RESET_SLEEP_SECS)
    return True

  def GetAdvertisedName(self):
    """Get the name advertised by the kit.

    The chip returns something like 'RNBT-A955\\r\\n'
    where 'RN' means Roving Network, 'BT' bluetooth, and
    'A955' the last four digits of its MAC address.

    Returns:
      The name that the kit advertises to other Bluetooth devices.
    """
    self.GetBasicSettings()
    return self._settings['BTName']

  def GetFirmwareVersion(self):
    """Get the firmware version of the kit.

    The chip returns something like
    'Ver 6.15 04/26/2013\\r\\n(c) Roving Networks\\r\\n'

    Returns:
      The firmware version of the kit.
    """
    return self.SerialSendReceive(self.CMD_GET_FIRMWARE_VERSION,
                                  expect_in='Ver',
                                  msg='getting firmware version')

  def GetAuthenticationMode(self):
    """Get the authentication mode.

    This specifies how the device will authenticate with the DUT, for example,
    a PIN code may be used.

    Returns:
      The authentication mode of the kit (from the choices in PeripheralKit).
    """
    self.GetBasicSettings()
    result = self._settings['Authen']
    return self.REV_AUTHENTICATION_MODE.get(result)

  def SetAuthenticationMode(self, mode):
    """Set the authentication mode to the specified mode.

    If mode is PIN_CODE_MODE, implementations must ensure the default PIN
    is set by calling _SetDefaultPinCode() as appropriate.

    Args:
      mode: the desired authentication mode (specified in PeripheralKit)

    Returns:
      True if the mode was set successfully,

    Raises:
      A kit-specific Exception if something goes wrong.
    """
    if mode not in self.AUTHENTICATION_MODE:
      error_msg = 'Unsupported Authentication mode: %s' % mode
      logging.error(error_msg)
      raise RN52Exception(error_msg)

    digit_mode = self.AUTHENTICATION_MODE.get(mode)

    self.SerialSendReceive(self.CMD_SET_AUTHENTICATION_MODE + digit_mode,
                           expect=self.AOK,
                           msg='setting authentication mode "%s"' % mode)
    if mode == PeripheralKit.PIN_CODE_MODE:
      return self.SetPinCode(self.DEFAULT_PIN_CODE)
    return True

  def GetPinCode(self):
    """Get the pin code.

    Returns:
      A string representing the pin code.
    """
    self.GetBasicSettings()
    result = self._settings['PinCode']
    return result

  def SetPinCode(self, pin):
    """Set the pin code.

    Args:
      pin: String representing value of new pin code.

    Returns:
      True if the pin code is set successfully,

    Raises:
      A kit-specifc exception if the pin code is invalid.
    """
    if len(pin) > self.MAX_PIN_LEN:
      vals = (pin, self.MAX_PIN_LEN)
      msg = 'The pin code "%s" is longer than max length (%d).' % vals
      logging.warn(msg)
      raise RN52Exception(msg)

    result = self.SerialSendReceive(self.CMD_SET_PIN_CODE + pin,
                                    msg='setting pin code')
    time.sleep(self.SET_PIN_CODE_SLEEP_SECS)
    return result

  def GetLocalBluetoothAddress(self):
    """Get the local (kit's) Bluetooth MAC address.

    The kit should always return a valid MAC address in the proper format:
    12 digits with colons between each pair, like so: '00:06:66:75:A9:6F'

    The RN-52 kit returns a raw address like '00066675A96F'.
    It is converted to something like '00:06:66:75:A9:6F'.

    Returns:
      The Bluetooth MAC address of the kit, None if the kit has no MAC address
      The RN-52 should always return a MAC address, though.
    """
    self.GetBasicSettings()
    raw_address = self._settings['BTA']
    if len(raw_address) == 12:
      return ':'.join([raw_address[i:i+2]
                       for i in range(0, len(raw_address), 2)])
    else:
      logging.error('RN52 bluetooth address is invalid: %s', raw_address)
      return None

  def GetConnectionStatus(self):
    """Get the connection status.

    This indicates that the kit is connected to a remote device, usually the
    DUT.

    the connection status returned from the kit could be
    '0,0,0': not connected
    '1,0,0': connected

    Returns:
      True if the kit is connected to a remote device.
    """
    result = self.SerialSendReceive(self.CMD_GET_CONNECTION_STATUS,
                                    msg='getting connection status')
    connection = self.CONNECTION_STRING[result]
    return connection

  def GetClassOfService(self):
    """Get the class of service.

    The Bluetooth Class of Device/Service field is described here:
    https://www.bluetooth.com/specifications/assigned-numbers/baseband

    COD[1:0]   = Format Type
    COD[7:2]   = Minor Device Class
    COD[12:8]  = Major Device Class
    COD[23:13] = Major Service Class

    e.g. COD = 0x240704 =>
    Service Class = 0x120 (Rendering, Audio)
    Major Device Class = 0x7 (Wearable)
    Minor Device Class = 0x1 (Wristwatch)

    Returns:
      A decimal integer representing the class of service.
    """
    self.GetBasicSettings()
    result = self._settings['COD']
    return int(result, 16) >> 12

  def SetClassOfService(self, cos_str):
    """Set the class of service.

    The Bluetooth Class of Device/Service field is described here:
    https://www.bluetooth.com/specifications/assigned-numbers/baseband

    See example in docstring for GetClassOfService()

    Args:
      cos_str: Class of Service portion of COD field

    Returns:
      True if the class of device/service was set successfully, or if this action is
      not supported.
    """
    self.GetBasicSettings()
    orig_cod =  self._settings['COD']
    new_cod = (int(orig_cod, 16) & 0x1fff) | (int(cos_str, 16) << 12)
    result = self.SerialSendReceive(
        self.CMD_SET_CLASS_OF_SERVICE + ("%06x" % new_cod),
        msg='setting class of service')
    return result

  def GetClassOfDevice(self):
    """Get the class of device.

    The chip uses a hexadeciaml string to represent the class of device.
    It is converted to a decimal number as the return value.
    The class of device is a number usually assigned by the Bluetooth SIG.
    Supported on RN-52 with BR/EDR.

    Returns:
      A decimal integer representing the class of device.
    """
    self.GetBasicSettings()
    result = self._settings['COD']
    return int(result, 16) & 0x1fff

  def SetClassOfDevice(self, cod_str):
    """Set the class of device.

    The Bluetooth Class of Device/Service field is described here:
    https://www.bluetooth.com/specifications/assigned-numbers/baseband

    See example in docstring for GetClassOfService()

    Args:
      cod_str: Class of Device portion of COD field

    Returns:
      True if the class of device/service was set successfully, or if this action is
      not supported.
    """
    self.GetBasicSettings()
    orig_cod =  self._settings['COD']
    # Clear 13 LSBits and populate with device class from input
    new_cod = (int(orig_cod, 16) & (~0x1ffff)) | int(cod_str, 16)
    result = self.SerialSendReceive(
        self.CMD_SET_CLASS_OF_SERVICE + ("%06x" % new_cod),
        msg='setting class of service')
    self._settings.clear() # Force a re-read of settings on next query

  def Disconnect(self):
    """Disconnect the A2DP profile. There doesn't seem to be a way to say
    'disconnect all'. This will disconnect the A2DP connection to the DUT,
    but an SPP connection seems to persist.

    Returns:
      True if disconnecting from the remote device succeeded.
    """
    # This is done by sending a 0x0.
    # A '%DISCONNECT' string would be received as a response.
    self.SerialSendReceive(self.CMD_DISCONNECT_A2DP,
                           msg='disconnecting from the remote device')
    return True

  def EnterCommandMode(self):
    """RN52 doesn't have a UART cmd to enter CMD mode (unlike RN42).
    Using this call to read basic settings.
    """
    self.GetBasicSettings()
    return True

  def LeaveCommandMode(self, force):
    """RN52 doesn't have a UART cmd to exit CMD mode (unlike RN42).
    Using this call to clear cached settings.
    """
    if self._settings:
      self._settings.clear()
    return True

  def GetKitInfo(self, connect_separately=False, test_reset=False):
    """A simple demo of getting kit information."""
    if connect_separately:
      print('create serial device: %s' % self.CreateSerialDevice())
    if test_reset:
      print('factory reset: %s' % self.FactoryReset())
    print('advertised name: %s' % self.GetAdvertisedName())
    print('firmware version: %s' % self.GetFirmwareVersion())
    print('authentication mode: %s' % self.GetAuthenticationMode())
    print('local bluetooth address: %s' % self.GetLocalBluetoothAddress())
    print('connection status: %s' % self.GetConnectionStatus())
    # The class of service/device is None for LE kits (it is BR/EDR-only)
    class_of_service = self.GetClassOfService()
    try:
      class_of_service = hex(class_of_service)
    except TypeError:
      pass
    print('Class of service: %s' % class_of_service)
    class_of_device = self.GetClassOfDevice()
    try:
      class_of_device = hex(class_of_device)
    except TypeError:
      pass
    print ('Class of device: %s' % class_of_device)

if __name__ == '__main__':
  kit_instance = RN52()
  kit_instance.GetKitInfo()
