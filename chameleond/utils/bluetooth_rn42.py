# -*- coding: utf-8 -*-
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides an abstraction of the RN-42 bluetooth chip."""

import logging
import time

import common
import sys
from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_peripheral_kit import PeripheralKitException
from ids import RN42_SET

class RN42Exception(PeripheralKitException):
  """A dummpy exception class for RN42 class."""
  pass


class RN42(PeripheralKit):
  """This is an abstraction of Roving Network's RN-42 bluetooth evaluation kit.

  RN-42 supports SPP and HID protocols. The primary use case is to
  configure it to use the HID protocol to emulate a keyboard, a mouse,
  or a combo of both.

  For user guide about serial control of the kit, refer to
  http://ww1.microchip.com/downloads/en/DeviceDoc/50002325A.pdf

  For advanced information about configuring HID profile, refer to
  http://ww1.microchip.com/downloads/en/DeviceDoc/bluetooth_cr_UG-v1.0r.pdf
  """

  # Serial port settings (override)
  DRIVER = 'ftdi_sio'
  BAUDRATE = 115200
  USB_VID = '0403'
  USB_PID = '6001'

  KNOWN_DEVICE_SET = RN42_SET   # Set of known RN42 serial numbers
  CHIP_NAME = 'RNBT'
  MAX_PIN_LEN = 16
  DEFAULT_PIN_CODE = '1234'     # The default factory pin code.
  # TODO(josephsih): Improve timing values, find/describe source thereof
  CONNECTION_TIMEOUT_SECS = 10  # the connection timeout in seconds
  POST_CONNECTION_WAIT_SECS = 1 # waiting time for a connection to become stable
  REBOOT_SLEEP_SECS = 3         # the time to sleep after reboot.
  RESET_SLEEP_SECS = 1          # the time to sleep after reboot.
  SET_PIN_CODE_SLEEP_SECS = 0.5 # the time to sleep after setting pin code.

  # Response status
  AOK = 'AOK'                 # Acknowledge OK
  UNKNOWN = '?'               # Unknown command

  # basic chip operations
  CMD_ENTER_COMMAND_MODE = '$$$'
  CMD_LEAVE_COMMAND_MODE = '---'
  CMD_REBOOT = 'R,1'
  CMD_FACTORY_RESET = 'SF,1'

  # chip basic information
  CMD_GET_ADVERTISED_NAME = 'GN'
  CMD_GET_FIRMWARE_VERSION = 'V'

  # operation modes: master or slave
  CMD_GET_OPERATION_MODE = 'GM'
  CMD_SET_MASTER_MODE = 'SM,1'
  CMD_SET_SLAVE_MODE = 'SM,0'

  # authentication mode
  CMD_GET_AUTHENTICATION_MODE = 'GA'
  CMD_SET_AUTHENTICATION_MODE = 'SA,'

  # pin code
  CMD_GET_PIN_CODE = 'GP'
  CMD_SET_PIN_CODE = 'SP,'

  # bluetooth service profiles
  PROFILE_SPP = '0'
  PROFILE_HID = '6'
  CMD_GET_SERVICE_PROFILE = 'G~'
  CMD_SET_SERVICE_PROFILE_SPP = 'S~,' + PROFILE_SPP
  CMD_SET_SERVICE_PROFILE_HID = 'S~,' + PROFILE_HID

  # bluetooth mac address and connection
  CMD_GET_RN42_BLUETOOTH_MAC = 'GB'
  CMD_GET_CONNECTION_STATUS = 'GK'
  CMD_GET_REMOTE_CONNECTED_BLUETOOTH_MAC = 'GF'
  CMD_ENABLE_CONNECTION_STATUS_MESSAGE = 'SO,1'
  CMD_DISABLE_CONNECTION_STATUS_MESSAGE = 'SO,0'

  # HID device classes
  CMD_GET_HID = 'GH'
  CMD_SET_HID_KEYBOARD = 'SH,0000'
  CMD_SET_HID_GAMEPAD = 'SH,0010'
  CMD_SET_HID_MOUSE = 'SH,0020'
  CMD_SET_HID_COMBO = 'SH,0030'
  CMD_SET_HID_JOYSTICK = 'SH,0040'

  # Class of Service/Device
  CMD_GET_CLASS_OF_SERVICE = 'GC'
  CMD_GET_CLASS_OF_DEVICE = 'GD'
  CMD_SET_CLASS_OF_SERVICE = 'SC,'
  CMD_SET_CLASS_OF_DEVICE = 'SD,'

  # Set remote bluetooth address
  CMD_SET_REMOTE_ADDRESS = 'SR,'

  # Connect to the stored remote address
  CMD_CONNECT_REMOTE_ADDRESS = 'C'
  # Disconnect from the remote device
  CMD_DISCONNECT_REMOTE_ADDRESS = chr(0)

  # UART input modes
  # raw mode
  UART_INPUT_RAW_MODE = 0xFD
  # Length of report format for keyboard
  RAW_REPORT_FORMAT_KEYBOARD_LENGTH = 9
  RAW_REPORT_FORMAT_KEYBOARD_DESCRIPTOR = 1
  RAW_REPORT_FORMAT_KEYBOARD_LEN_SCAN_CODES = 6
  LEN_SCAN_CODES = 6
  # shorthand mode
  UART_INPUT_SHORTHAND_MODE = 0xFE
  SHORTHAND_REPORT_FORMAT_KEYBOARD_MAX_LEN_SCAN_CODES = 6
  # Length of report format for mouse
  RAW_REPORT_FORMAT_MOUSE_LENGTH = 5
  RAW_REPORT_FORMAT_MOUSE_DESCRIPTOR = 2

  # Definitions of mouse button HID encodings
  RAW_HID_BUTTONS_RELEASED = 0x0
  RAW_HID_LEFT_BUTTON = 0x01
  RAW_HID_RIGHT_BUTTON = 0x02

  # TODO(alent): Move std scan codes to PeripheralKit when Keyboard implemented
  # modifiers
  LEFT_CTRL = 0x01
  LEFT_SHIFT = 0x02
  LEFT_ALT = 0x04
  LEFT_GUI = 0x08
  RIGHT_CTRL = 0x10
  RIGHT_SHIFT = 0x20
  RIGHT_ALT = 0x40
  RIGHT_GUI = 0x80
  MODIFIERS = [LEFT_CTRL, LEFT_SHIFT, LEFT_ALT, LEFT_GUI,
               RIGHT_CTRL, RIGHT_SHIFT, RIGHT_ALT, RIGHT_GUI]

  # ASCII to HID report scan codes
  SCAN_SYSTEM_POWER = 0x81
  SCAN_SYSTEM_SLEEP = 0x82
  SCAN_SYSTEM_WAKE = 0x83
  SCAN_NO_EVENT = 0x0
  SCAN_OVERRUN_ERROR = 0x01
  SCAN_POST_FAIL = 0x02
  SCAN_ERROR_UNDEFINED = 0x03
  SCAN_A = 0x04
  SCAN_B = 0x05
  SCAN_C = 0x06
  SCAN_D = 0x07
  SCAN_E = 0x08
  SCAN_F = 0x09
  SCAN_G = 0x0A
  SCAN_H = 0x0B
  SCAN_I = 0x0C
  SCAN_J = 0x0D
  SCAN_K = 0x0E
  SCAN_L = 0x0F
  SCAN_M = 0x10
  SCAN_N = 0x11
  SCAN_O = 0x12
  SCAN_P = 0x13
  SCAN_Q = 0x14
  SCAN_R = 0x15
  SCAN_S = 0x16
  SCAN_T = 0x17
  SCAN_U = 0x18
  SCAN_V = 0x19
  SCAN_W = 0x1A
  SCAN_X = 0x1B
  SCAN_Y = 0x1C
  SCAN_Z = 0x1D
  SCAN_1 = 0x1E                     # 1
  SCAN_EXCLAMATION = 0x1E           # !
  SCAN_2 = 0x1F                     # 2
  SCAN_AMPERSAT = 0x1F              # @
  SCAN_3 = 0x20                     # 3
  SCAN_POUND = 0x20                 # #
  SCAN_4 = 0x21                     # 4
  SCAN_DOLLAR = 0x21                # $
  SCAN_5 = 0x22                     # 5
  SCAN_PERCENT = 0x22               # %
  SCAN_6 = 0x23                     # 6
  SCAN_CARET = 0x23                 # ^
  SCAN_7 = 0x24                     # 7
  SCAN_AMPERSAND = 0x24             # &
  SCAN_8 = 0x25                     # 8
  SCAN_ASTERISK = 0x25              # *
  SCAN_9 = 0x26                     # 9
  SCAN_OPEN_PARENTHESIS = 0x26      # (
  SCAN_0 = 0x27                     # 0
  SCAN_CLOSE_PARENTHESIS = 0x27     # )
  SCAN_RETURN = 0x28
  SCAN_ESCAPE = 0x29
  SCAN_BACKSPACE = 0x2A
  SCAN_TAB = 0x2B
  SCAN_SPACE = 0x2C
  SCAN_MINUS = 0x2D                 # -
  SCAN_UNDERSCORE = 0x2D            # _
  SCAN_EQUAL = 0x2E                 # =
  SCAN_PLUS = 0x2E                  # +
  SCAN_OPEN_BRACKET = 0x2F          # [
  SCAN_OPEN_BRACE = 0x2F            # {
  SCAN_CLOSE_BRACKET = 0x30         # ]
  SCAN_CLOSE_BRACE = 0x30           # }
  SCAN_BACK_SLASH = 0x31            # \
  SCAN_PIPE = 0x31                  # |
  SCAN_EUROPE1 = 0x32
  SCAN_SEMICOLON = 0x33             # ;
  SCAN_COLON = 0x33                 # :
  SCAN_APOSTROPHE = 0x34            # '
  SCAN_QUOTE = 0x34                 # "
  SCAN_ACUTE = 0x35                 # `
  SCAN_TILDE = 0x35                 # ~
  SCAN_COMMA = 0x36                 # ,
  SCAN_OPEN_ANGLE_BRACKET = 0x36    # <
  SCAN_PERIOD = 0x37                # .
  SCAN_CLOSE_ANGLE_BRACKET = 0x37   # >
  SCAN_SLASH = 0x38                 # /
  SCAN_QUESTION = 0x38              # ?
  SCAN_CAPS_LOCK = 0x39
  SCAN_F1 = 0x3A
  SCAN_F2 = 0x3B
  SCAN_F3 = 0x3C
  SCAN_F4 = 0x3D
  SCAN_F5 = 0x3E
  SCAN_F6 = 0x3F
  SCAN_F7 = 0x40
  SCAN_F8 = 0x41
  SCAN_F9 = 0x42
  SCAN_F10 = 0x43
  SCAN_F11 = 0x44
  SCAN_F12 = 0x45
  SCAN_PRINT_SCREEN = 0x46
  SCAN_SCROLL_LOCK = 0x47
  SCAN_BREAK = 0x48
  SCAN_PAUSE = 0x48

  # the operation mode
  OPERATION_MODE = {
      'Slav': 'SLAVE',      # slave mode
      'Mstr': 'MASTER',     # master mode
      'Trig': 'TRIGGER',    # trigger mode
      'Auto': 'AUTO',       # auto connect master mode
      'DTR': 'DTR',         # auto connect DTR mode
      'Any': 'ANY',         # auto connect any mode
      'Pair': 'PAIR'        # paring mode
  }

  # the service profile
  SERVICE_PROFILE = {
      '0': 'SPP',
      '1': 'DUN_DCE',
      '2': 'DUN_DTE',
      '3': 'MDM_SPP',
      '4': 'SPP_AND_DUN_DCE',
      '5': 'APL',
      '6': 'HID'
  }

  DEFAULT_CLASS_OF_SERVICE = 0

  # Map HID type to Class of Device
  CLASS_OF_DEVICE = {
      PeripheralKit.KEYBOARD: 0x540,
      PeripheralKit.GAMEPAD: 0x508,
      PeripheralKit.MOUSE: 0x580,
      PeripheralKit.COMBO: 0x5C0,
      PeripheralKit.JOYSTICK: 0x504
  }

  # The mask of Class of Device
  CLASS_OF_DEVICE_MASK = 0x1FFF

  # Map kit-specific HID type to abstract HID type
  HID_DEVICE_TYPE = {
      '0000': PeripheralKit.KEYBOARD,
      '0010': PeripheralKit.GAMEPAD,
      '0020': PeripheralKit.MOUSE,
      '0030': PeripheralKit.COMBO,
      '0040': PeripheralKit.JOYSTICK
  }

  # Map abstract authentication mode to decimal number
  AUTHENTICATION_MODE = {
      PeripheralKit.OPEN_MODE: '0',
      PeripheralKit.SSP_KEYBOARD_MODE: '1',
      PeripheralKit.SSP_JUST_WORK_MODE: '2',
      PeripheralKit.PIN_CODE_MODE: '4'
  }

  # Map abstract authentication mode to decimal number
  REV_AUTHENTICATION_MODE = {v: k for k, v in AUTHENTICATION_MODE.iteritems()}

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
    """Make the kit enter command mode.

    Enter command mode, creating the serial connection if necessary.
    This must happen before other methods can be called, as they generally rely
    on sending commands.

    Returns:
      True if the kit succeessfully entered command mode.

    Raises:
      PeripheralKitException if there is an error in serial communication or
      if the kit gives an unexpected response.
      A kit-specific Exception if something else goes wrong.
    """
    # We must implement this contract, creating the device if it doesn't exist.
    if not self._serial:
      self.CreateSerialDevice()

    try:
      # The command to enter command mode is special. It does not end
      # with a newline. (It is an invalid command once in command mode.)
      # The result is something like '...CMD\r\n' where '...' means
      # some possible random characters in the serial buffer.
      self.SerialSendReceive(self.CMD_ENTER_COMMAND_MODE,
                             expect_in='CMD',
                             msg='entering command mode',
                             send_newline=False)
      logging.info('Entered command mode successfully.')
      self._command_mode = True
      return True
    except PeripheralKitException as e:
      # This exception happens when the expect fails in SerialSendRecieve.
      # This may happen if we are already in command mode, since commands must
      # be followed by a newline. Send a newline to try to reset the state.
      self.SerialSendReceive('')
      # Now, try to check if we are in command mode by reading a config value.
      try:
        advertised_name = self.GetAdvertisedName()
        if advertised_name.startswith(self.CHIP_NAME):
          msg = 'Correct advertised name when entering command mode: %s'
          logging.info(msg, advertised_name)
          self._command_mode = True
          return True
        else:
          msg = 'Incorrect advertised name when entering command mode: %s'
          logging.error(msg, advertised_name)
          raise RN42Exception(msg % advertised_name)
      except Exception as e:
        msg = 'Failure to get advertised name in entering command mode: %s.' % e
        logging.error(msg)
        raise RN42Exception(msg)

  def LeaveCommandMode(self, force=False):
    """Make the kit leave command mode.

    Args:
      force: True if we want to ignore potential errors and attempt to
             leave command mode regardless.

    Returns:
      True if the kit left command mode successfully.
    """
    # An 'END' string is returned from RN-42 if it leaves the command mode
    # normally.
    if self._command_mode or force:
      expect_in = '' if force else 'END'
      self.SerialSendReceive(self.CMD_LEAVE_COMMAND_MODE,
                             expect_in=expect_in,
                             msg='leaving command mode')
      self._command_mode = False
    return True

  def Reboot(self):
    """Reboot (or partially reset) the chip.

    On the RN42 kit, this does not reset the pairing info.

    Returns:
      True if the kit rebooted successfully.
    """
    self.SerialSendReceive(self.CMD_REBOOT,
                           expect_in='Reboot',
                           msg='rebooting RN-42')
    time.sleep(self.REBOOT_SLEEP_SECS)
    return True

  def FactoryReset(self):
    """Factory reset the chip.

    Reset the chip to the factory defaults.

    Returns:
      True if the kit is reset successfully.
    """
    self.SerialSendReceive(self.CMD_FACTORY_RESET,
                           msg='factory reset RN-42')
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
    return self.SerialSendReceive(self.CMD_GET_ADVERTISED_NAME,
                                  expect_in='RNBT',
                                  msg='getting advertised name')

  def GetFirmwareVersion(self):
    """Get the firmware version of the kit.

    The chip returns something like
    'Ver 6.15 04/26/2013\\r\\n(c) Roving Networks\\r\\n'
    Note that the version must be higher than 6.11 to support HID profile.

    Returns:
      The firmware version of the kit.
    """
    return self.SerialSendReceive(self.CMD_GET_FIRMWARE_VERSION,
                                  expect_in='Ver',
                                  msg='getting firmware version')

  def GetOperationMode(self):
    """Get the operation mode.

    This is master/slave in Bluetooth BR/EDR.

    Returns:
      The operation mode of the kit.
    """
    result = self.SerialSendReceive(self.CMD_GET_OPERATION_MODE,
                                    msg='getting operation mode')
    return self.OPERATION_MODE.get(result)

  def SetMasterMode(self):
    """Set the kit to master mode.

    Returns:
      True if master mode was set successfully.
    """
    self.SerialSendReceive(self.CMD_SET_MASTER_MODE,
                           expect=self.AOK,
                           msg='setting master mode')
    return True

  def SetSlaveMode(self):
    """Set the kit to slave mode.

    Returns:
      True if slave mode was set successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SLAVE_MODE,
                           expect=self.AOK,
                           msg='setting slave mode')
    return True

  def GetAuthenticationMode(self):
    """Get the authentication mode.

    This specifies how the device will authenticate with the DUT, for example,
    a PIN code may be used.

    Returns:
      The authentication mode of the kit (from the choices in PeripheralKit).
    """
    result = self.SerialSendReceive(self.CMD_GET_AUTHENTICATION_MODE,
                                    msg='getting authentication mode')
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
      raise RN42Exception(error_msg)

    digit_mode = self.AUTHENTICATION_MODE.get(mode)

    self.SerialSendReceive(self.CMD_SET_AUTHENTICATION_MODE + digit_mode,
                           expect=self.AOK,
                           msg='setting authentication mode "%s"' % mode)
    if mode == PeripheralKit.PIN_CODE_MODE:
      return self._SetDefaultPinCode()
    return True

  def GetPinCode(self):
    """Get the pin code.

    Returns:
      A string representing the pin code.
    """
    result = self.SerialSendReceive(self.CMD_GET_PIN_CODE,
                                    msg='getting pin code')
    return result

  def SetPinCode(self, pin):
    """Set the pin code.

    Returns:
      True if the pin code is set successfully,

    Raises:
      A kit-specifc exception if the pin code is invalid.
    """
    if len(pin) > self.MAX_PIN_LEN:
      vals = (pin, self.MAX_PIN_LEN)
      msg = 'The pin code "%s" is longer than max length (%d).' % vals
      logging.warn(msg)
      raise RN42Exception(msg)

    result = self.SerialSendReceive(self.CMD_SET_PIN_CODE + pin,
                                    msg='setting pin code')
    time.sleep(self.SET_PIN_CODE_SLEEP_SECS)
    # Sometimes SetPinCode seems to return empty string instead of AOK
    # But the pin seems to get set anyhow.
    # Handle this by checking the pin
    if not bool(result):
      logging.info("Got return '%s' in SetPinCode", result)
      actual_pin = self.GetPinCode()
      if actual_pin != pin:
        logging.error("Pincode set %s does not match returned %s",
                      pin, actual_pin)
        return False
      else:
        logging.info('Pincode matches.')
        return True
    else:
      return bool(result)

  def GetServiceProfile(self):
    """Get the service profile.

    Returns:
      The service profile currently in use (as per constant in PeripheralKit)
    """
    result = self.SerialSendReceive(self.CMD_GET_SERVICE_PROFILE,
                                    msg='getting service profile')
    return self.SERVICE_PROFILE.get(result)

  def SetServiceProfileSPP(self):
    """Set SPP as the service profile.

    Returns:
      True if the service profile was set to SPP successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SERVICE_PROFILE_SPP,
                           expect=self.AOK,
                           msg='setting SPP as service profile')
    return True

  def SetServiceProfileHID(self):
    """Set HID as the service profile.

    Returns:
      True if the service profile was set to HID successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SERVICE_PROFILE_HID,
                           expect=self.AOK,
                           msg='setting HID as service profile')
    return True

  def GetLocalBluetoothAddress(self):
    """Get the local (kit's) Bluetooth MAC address.

    The kit should always return a valid MAC address in the proper format:
    12 digits with colons between each pair, like so: '00:06:66:75:A9:6F'

    The RN-42 kit returns a raw address like '00066675A96F'.
    It is converted to something like '00:06:66:75:A9:6F'.

    Returns:
      The Bluetooth MAC address of the kit, None if the kit has no MAC address
      The RN-42 should always return a MAC address, though.
    """
    raw_address = self.SerialSendReceive(self.CMD_GET_RN42_BLUETOOTH_MAC,
                                         msg='getting local bluetooth address')
    if len(raw_address) == 12:
      return ':'.join([raw_address[i:i+2]
                       for i in range(0, len(raw_address), 2)])
    else:
      logging.error('RN42 bluetooth address is invalid: %s', raw_address)
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
    connection = result.split(',')[0]
    return connection == '1'

  def EnableConnectionStatusMessage(self):
    """Enable the connection status message.

    On the RN-42, this is required to use connection-related methods.

    If this is enabled, a connection status message shows
      '...CONNECT...' when connected and
      '...DISCONNECT...' when disconnected
    in the serial console.

    Returns:
      True if enabling the connection status message successfully.
    """
    self.SerialSendReceive(self.CMD_ENABLE_CONNECTION_STATUS_MESSAGE,
                           expect=self.AOK,
                           msg='enabling connection status message')
    return True

  def DisableConnectionStatusMessage(self):
    """Disable the connection status message.

    If this is disabled, the serial console would not show any connection
    status message when connected/disconnected.

    Returns:
      True if disabling the connection status message successfully.
    """
    self.SerialSendReceive(self.CMD_DISABLE_CONNECTION_STATUS_MESSAGE,
                           expect=self.AOK,
                           msg='disabling connection status message')
    return True

  def GetRemoteConnectedBluetoothAddress(self):
    """Get the Bluetooth MAC address of the current connected remote host.

    The RN-42 kit returns a raw address like '00066675A96F'.
    It is converted to something like '00:06:66:75:A9:6F'.

    Returns:
      The Bluetooth MAC address of the remote connected device if applicable,
      or None if there is no remote connected device. If not None, this will
      be properly formatted as a 12-digit MAC address with colons.
    """
    result = self.SerialSendReceive(self.CMD_GET_REMOTE_CONNECTED_BLUETOOTH_MAC,
                                    msg='getting local bluetooth address')
    # result is '000000000000' if there is no remote connected device
    if result == '000000000000':
      return None
    if len(result) == 12:
      return ':'.join([result[i:i+2]
                       for i in range(0, len(result), 2)])
    else:
      logging.error('remote bluetooth address is invalid: %s', result)
      return None

  def GetHIDDeviceType(self):
    """Get the HID device type.

    Returns:
      A string representing the HID device type (from PeripheralKit)
    """
    result = self.SerialSendReceive(self.CMD_GET_HID,
                                    msg='getting HID device type')
    return self.HID_DEVICE_TYPE.get(result)

  def SetHIDType(self, device_type):
    """Set HID type to the specified device type.

    Args:
      device_type: the HID type to emulate, from PeripheralKit

    Returns:
      True if successful

    Raises:
      A kit-specific exception if that device type is not supported.
    """
    if device_type == self.KEYBOARD:
      self.SerialSendReceive(self.CMD_SET_HID_KEYBOARD,
                             expect=self.AOK,
                             msg='setting keyboard as HID type')
    elif device_type == self.GAMEPAD:
      self.SerialSendReceive(self.CMD_SET_HID_GAMEPAD,
                             expect=self.AOK,
                             msg='setting gamepad as HID type')
    elif device_type == self.MOUSE:
      self.SerialSendReceive(self.CMD_SET_HID_MOUSE,
                             expect=self.AOK,
                             msg='setting mouse as HID type')
    elif device_type == self.COMBO:
      self.SerialSendReceive(self.CMD_SET_HID_COMBO,
                             expect=self.AOK,
                             msg='setting combo as HID type')
    elif device_type == self.JOYSTICK:
      self.SerialSendReceive(self.CMD_SET_HID_JOYSTICK,
                             expect=self.AOK,
                             msg='setting joystick as HID type')
    else:
      msg = "Failed to set HID type, not supported: %s" % device_type
      logging.error(msg)
      raise RN42Exception(msg)
    return True

  def GetClassOfService(self):
    """Get the class of service.

    Usually, a hexadeciaml string is used to represent the class of service,
    which usually uses certain numbers assigned by the Bluetooth SIG.
    In this case, it is provided as decimal.
    Supported on BR/EDR with RN-42.

    Returns:
      A decimal integer representing the class of service.
    """
    result = self.SerialSendReceive(self.CMD_GET_CLASS_OF_SERVICE,
                                    msg='getting class of service')
    return int(result, 16)

  def _To4DigitHex(self, value):
    """Convert the value to a 4-digit hexadecimal string.

    For example, the decimal value 42 is converted to '002A'

    Args:
      value: the value to convert

    Returns:
      a 4-digit hexadecimal string of the value
    """
    return '%04X' % value

  def SetClassOfService(self, class_of_service):
    """Set the class of service.

    The class of service is a number usually assigned by the Bluetooth SIG.
    Supported on BR/EDR with RN-42.

    Args:
      class_of_service: A decimal integer representing the class of service.

    Returns:
      True if the class of service was set successfully, or if this action is
      not supported.

    Raises:
      A kit-specific expection if the class of service is not supported.
    """
    result = self.SerialSendReceive(
        self.CMD_SET_CLASS_OF_SERVICE + self._To4DigitHex(class_of_service),
        msg='setting class of service')
    return result

  def GetClassOfDevice(self):
    """Get the class of device.

    The chip uses a hexadeciaml string to represent the class of device.
    It is converted to a decimal number as the return value.
    The class of device is a number usually assigned by the Bluetooth SIG.
    Supported on RN-42 with BR/EDR.

    Returns:
      A decimal integer representing the class of device.
    """
    result = self.SerialSendReceive(self.CMD_GET_CLASS_OF_DEVICE,
                                    msg='getting class of device')
    return int(result, 16)

  def _SetClassOfDevice(self, class_of_device):
    """Set the class of device.

    Returns:
      True if setting the class of device successfully.
    """
    result = self.SerialSendReceive(
        self.CMD_SET_CLASS_OF_DEVICE + self._To4DigitHex(class_of_device),
        msg='setting class of device')
    return result

  def SetClassOfDevice(self, device_type):
    """Set the class of device.

    The class of device is a number usually assigned by the Bluetooth SIG.
    Supported on RN-42 with BR/EDR.

    Args:
      device_type: A decimal integer representing the class of device.

    Returns:
      True if the class of device was set successfully, or if this action is
      not supported.

    Raises:
      A kit-specific expection if the class of device is not supported.
    """
    if device_type in self.CLASS_OF_DEVICE:
      return self._SetClassOfDevice(self.CLASS_OF_DEVICE.get(device_type))
    else:
      error_msg = 'device type is not supported: %s' % device_type
      logging.error(error_msg)
      raise RN42Exception(error_msg)

  def SetRemoteAddress(self, remote_address):
    """Set the remote Bluetooth address.

    (Usually this will be the device under test that we want to connect with,
    where the kit starts the connection.)

    Args:
      remote_address: the remote Bluetooth MAC address, which must be given as
                      12 hex digits with colons between each pair.
                      For reference: '00:29:95:1A:D4:6F'

    Returns:
      True if the remote address was set successfully.

    Raises:
      PeripheralKitException if the given address was malformed.
    """
    reduced_address = remote_address.replace(':', '')
    self.SerialSendReceive(self.CMD_SET_REMOTE_ADDRESS + reduced_address,
                           expect=self.AOK,
                           msg='setting a remote address ' + reduced_address)
    return True

  def Connect(self):
    """Connect to the stored remote bluetooth address.

    In the case of a timeout (or a failure causing an exception), the caller
    is responsible for retrying when appropriate.

    When a connection command is issued, it first returns a response 'TRYING'.
    If the connection is successful, it returns something like
    '...%CONNECT,6C29951AD46F,0'  where '6C29951AD46F' is the remote_address
    after a few seconds.

    Returns:
      True if connecting to the stored remote address succeeded, or
      False if a timeout occurs.
    """
    # Expect an immediately 'TRYING' response.
    self.SerialSendReceive(self.CMD_CONNECT_REMOTE_ADDRESS,
                           expect='TRYING',
                           msg='connecting to the stored remote address')

    # Expect a 'CONNECT' response in a few seconds.
    try:
      # It usually takes a few seconds to establish a connection.
      common.WaitForCondition(lambda: 'CONNECT' in self._serial.Receive(size=0),
                              True,
                              self.RETRY_INTERVAL_SECS,
                              self.CONNECTION_TIMEOUT_SECS)

      # Have to wait for a while. Otherwise, the initial characters sent
      # may get lost.
      time.sleep(self.POST_CONNECTION_WAIT_SECS)
      return True
    except common.TimeoutError:
      # The connection process may be flaky. Hence, do not raise an exception.
      # Just return False and let the caller handle the connection timeout.
      logging.error('RN42 failed to connect.')
      return False

  def Disconnect(self):
    """Disconnect from the remote device.

    Specifically, this causes the peripheral emulation kit to disconnect from
    the remote connected device, usually the DUT.

    Returns:
      True if disconnecting from the remote device succeeded.
    """
    # This is done by sending a 0x0.
    # A '%DISCONNECT' string would be received as a response.
    self.SerialSendReceive(self.CMD_DISCONNECT_REMOTE_ADDRESS,
                           expect_in='DISCONNECT',
                           msg='disconnecting from the remote device')
    return True

  # TODO(alent): Refactor this part of the API, it's too RN-42-specific!

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
      codes = RawKeyCodes(modifiers=[RN42.LEFT_SHIFT, RN42.LEFT_ALT],
                          keys=[RN42.SCAN_I])

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
        raise RN42Exception(error)
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
      self.SerialSendReceive(mouse_codes, msg='RN42: MouseMove')

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
      self.SerialSendReceive(mouse_codes, msg='RN42: MouseScroll')

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
      self.SerialSendReceive(mouse_codes, msg='RN42: MousePressButtons')

  def MouseReleaseAllButtons(self):
    """Release all mouse buttons."""
    self._MouseButtonStateClear()
    mouse_codes = self._RawMouseCodes(buttons=self.RAW_HID_BUTTONS_RELEASED)
    self.SerialSendReceive(mouse_codes, msg='RN42: MouseReleaseAllButtons')

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
      codes = PressShorthandCodes(modifiers=[RN42.LEFT_SHIFT, RN42.LEFT_ALT],
                                  keys=[RN42_I])

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

  def GetKitInfo(self, connect_separately=False, test_reset=False):
    """A simple demo of getting kit information."""
    # TODO(josephsih): This compatability test is very, very basic
    if connect_separately:
      print 'create serial device: ', self.CreateSerialDevice()
    print 'enter command mode:', self.EnterCommandMode()
    if test_reset:
      print 'factory reset: ', self.FactoryReset()
    print 'advertised name:', self.GetAdvertisedName()
    print 'firmware version:', self.GetFirmwareVersion()
    print 'operation mode:', self.GetOperationMode()
    print 'authentication mode:', self.GetAuthenticationMode()
    print 'service profile:', self.GetServiceProfile()
    print 'local bluetooth address:', self.GetLocalBluetoothAddress()
    print 'connection status:', self.GetConnectionStatus()
    remote_addr = self.GetRemoteConnectedBluetoothAddress()
    print 'remote bluetooth address:', remote_addr
    print 'HID device type:', self.GetHIDDeviceType()
    # The class of service/device is None for LE kits (it is BR/EDR-only)
    class_of_service = self.GetClassOfService()
    try:
      class_of_service = hex(class_of_service)
    except TypeError:
      pass
    print 'Class of service:', class_of_service
    class_of_device = self.GetClassOfDevice()
    try:
      class_of_device = hex(class_of_device)
    except TypeError:
      pass
    print 'Class of device:', class_of_device
    print 'leave command mode:', self.LeaveCommandMode()


if __name__ == '__main__':
  kit_instance = RN42()
  kit_instance.GetKitInfo()
  if len(sys.argv) > 1 and sys.argv[1] == '--list':
    print("\nKnown device serial numbers:")
    for device in kit_instance.KNOWN_DEVICE_SET:
      print("%s" % device)
