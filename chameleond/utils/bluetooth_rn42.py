# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides an abstraction of RN-42 bluetooth chip."""

import logging
import serial
import time

import common
import serial_utils


class RN42Exception(Exception):
  """A dummpy exception class for RN42 class."""
  pass


class RN42(object):
  """This is an abstraction of Roving Network's RN-42 bluetooth evaluation kit.

  RN-42 supports SPP and HID protocols. The primary use case is to
  configure it to use the HID protocol to emulate a keyboard, a mouse,
  or a combo of both.

  For user guide about serial control of the kit, refer to
  http://ww1.microchip.com/downloads/en/DeviceDoc/50002325A.pdf

  For advanced information about configuring HID profile, refer to
  http://ww1.microchip.com/downloads/en/DeviceDoc/bluetooth_cr_UG-v1.0r.pdf
  """

  # Serial port settings
  BAUDRATE = 115200
  BYTESIZE = serial.EIGHTBITS
  PARITY = serial.PARITY_NONE
  STOPBITS = serial.STOPBITS_ONE

  DRIVER = 'ftdi_sio'
  CHIP_NAME = 'RNBT'
  RETRY = 2                     # Try (RETRY + 1) times in total.
  RETRY_INTERVAL_SECS = 0.1     # the time interval between retries in seconds
  CONNECTION_TIMEOUT_SECS = 10  # the connection timeout in seconds
  POST_CONNECTION_WAIT_SECS = 1 # waiting time in seconds for a connection
                                # to become stable
  REBOOT_SLEEP_SECS = 0.5       # the time to sleep after reboot.
  CREATE_SERIAL_DEVICE_SLEEP_SECS = 1
                                # waiting time after creating a serial device

  # A newline is a carriage return '\r' followed by line feed '\n'.
  NEWLINE = '\r\n'

  # Response status
  AOK = 'AOK'                 # Acknowledge OK
  UNKNOWN = '?'               # Unknown command

  # basic chip operations
  CMD_ENTER_COMMAND_MODE = '$$$'
  CMD_LEAVE_COMMAND_MODE = '---'
  CMD_REBOOT = 'R,1'

  # chip basic information
  CMD_GET_CHIP_NAME = 'GN'
  CMD_GET_FIRMWARE_VERSION = 'V'

  # operation modes: master or slave
  CMD_GET_OPERATION_MODE = 'GM'
  CMD_SET_MASTER_MODE = 'SM,1'
  CMD_SET_SLAVE_MODE = 'SM,0'

  # authentication mode
  CMD_GET_AUTHENTICATION_MODE = 'GA'
  CMD_SET_AUTHENTICATION_MODE = 'SA,'

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

  # the authentication mode
  OPEN_MODE = '0'
  SSP_KEYBOARD_MODE = '1'
  SSP_JUST_WORK_MODE = '2'
  PIN_CODE_MODE = '4'
  AUTHENTICATION_MODE = {
      OPEN_MODE: 'OPEN',
      SSP_KEYBOARD_MODE: 'SSP_KEYBOARD',
      SSP_JUST_WORK_MODE: 'SSP_JUST_WORK',
      PIN_CODE_MODE: 'PIN_CODE'}

  # the service profile
  SERVICE_PROFILE = {
      '0': 'SPP',
      '1': 'DUN_DCE',
      '2': 'DUN_DTE',
      '3': 'MDM_SPP',
      '4': 'SPP_AND_DUN_DCE',
      '5': 'APL',
      '6': 'HID'}

  # HID device types
  HID_DEVICE_TYPE = {
      '0000': 'KEYBOARD',
      '0001': 'GAMEPAD',
      '0010': 'MOUSE',
      '0011': 'COMBO',
      '0100': 'JOYSTICK'}

  def __init__(self):
    self._command_mode = False
    self._closed = False
    self._serial = None
    self._port = None

  def CreateSerialDevice(self):
    """Create the serial device."""
    try:
      self._serial = serial_utils.SerialDevice()
    except Exception as e:
      error_msg = 'Fail to create a serial device: %s' % e
      logging.error(error_msg)
      raise RN42Exception(error_msg)

    try:
      self._serial.Connect(driver=self.DRIVER,
                           baudrate=self.BAUDRATE,
                           bytesize=self.BYTESIZE,
                           parity=self.PARITY,
                           stopbits=self.STOPBITS)
      self._port = self._serial.port
      logging.info('Connect to the serial port successfully: %s', self._port)
    except Exception as e:
      error_msg = 'Fail to connect to the serial device: %s' % e
      logging.error(error_msg)
      raise RN42Exception(error_msg)
    time.sleep(self.CREATE_SERIAL_DEVICE_SLEEP_SECS)

  def __del__(self):
    self.Close()

  def Close(self):
    """Close the device gracefully."""
    if not self._closed:
      # It is possible that RN-42 has left command mode. In that case, do not
      # expect any response from the kit.
      self.LeaveCommandMode(expect_in='')
      self._serial.Disconnect()
      self._closed = True

  def SerialSendReceive(self, command, expect='', expect_in='',
                        msg='serial SendReceive()'):
    """A wrapper of SerialDevice.SendReceive().

    Args:
      command: the serial command
      expect: expect the exact string matching the response
      expect_in: expect the string in the response
      msg: the message to log

    Returns:
      the result received from the serial console

    Raises:
      RN42Exception if there is an error in serial communication or
      if the response is not expected.
    """
    try:
      # All commands must end with a newline.
      # size=0 means to receive all waiting characters.
      # Retry a few times since sometimes the serial communication
      # may not be reliable.
      # Strip the result which ends with a newline too.
      result = self._serial.SendReceive(command + self.NEWLINE,
                                        size=0,
                                        retry=self.RETRY).strip()
      logging.debug('  SerialSendReceive: %s', result)
      if ((expect and expect != result) or
          (expect_in and expect_in not in result)):
        error_msg = 'Failulre in %s: %s' % (msg, result)
        raise RN42Exception(error_msg)
    except:
      error_msg = 'Failulre in %s' % msg
      raise RN42Exception(error_msg)

    logging.info('Success in %s: %s', msg, result)
    return result

  def EnterCommandMode(self):
    """Make the chip enter command mode.

    Returns:
      True if entering the command mode successfully.

    Raises:
      RN42Exception if there is an error in serial communication or
      if the response is not expected.
    """
    # Create a serial device if not yet.
    if not self._serial:
      self.CreateSerialDevice()

    try:
      # The command to enter command mode is special. It does not end
      # with a newline.
      # The result is something like '...CMD\r\n' where '...' means
      # some possible random characters in the serial buffer.
      result = self._serial.SendReceive(self.CMD_ENTER_COMMAND_MODE,
                                        size=0,
                                        retry=self.RETRY).strip()
    except serial.SerialTimeoutException:
      raise RN42Exception('Failure in entering command mode.')

    if 'CMD' in result:
      logging.info('Enter command mode successfully.')
      self._command_mode = True
      return True
    elif result == '':
      # If the chip is already in command mode, this would cause timeout
      # and returns an empty string. So let's check if we could get the
      # chip name to make sure that it is indeed in command mode.
      try:
        chip_name = self.GetChipName()
        if chip_name.startswith(self.CHIP_NAME):
          msg = 'Correct chip name when entering command mode: %s'
          logging.info(msg, chip_name)
          self._command_mode = True
          return True
        else:
          msg = 'Incorrect chip name when entering command mode: %s'
          raise RN42Exception(msg % chip_name)
      except:
        msg = 'Failure to get chip name in entering command mode.'
        raise RN42Exception(msg)
    else:
      msg = 'Incorrect response in entering command mode: %s'
      raise RN42Exception(msg % result)

  def LeaveCommandMode(self, expect_in='END'):
    """Make the chip leave command mode.

    An 'END' string is returned from RN-42 if it leaves the command mode
    normally.

    Args:
      expect_in: expect the string in the response

    Returns:
      True if the kit left the command mode successfully.
    """
    if self._command_mode:
      self.SerialSendReceive(self.CMD_LEAVE_COMMAND_MODE,
                             expect_in=expect_in,
                             msg='leaving command mode')
      self._command_mode = False
    return True

  def Reboot(self):
    """Reboot the chip.

    Reboot is required to make some settings take effect when the
    settings are changed.

    Returns:
      True if the kit rebooted successfully.
    """
    self.SerialSendReceive(self.CMD_REBOOT,
                           expect_in='Reboot',
                           msg='rebooting RN-42')
    time.sleep(self.REBOOT_SLEEP_SECS)
    return True

  def GetChipName(self):
    """Get the chip name.

    The chip returns something like 'RNBT-A955\\r\\n'
    where 'RN' means Roving Network, 'BT' bluetooth, and
    'A955' the last four digits of its MAC address.

    Returns:
      the chip name
    """
    return self.SerialSendReceive(self.CMD_GET_CHIP_NAME,
                                  expect_in='RNBT',
                                  msg='getting chip name')

  def GetFirmwareVersion(self):
    """Get the firmware version of the chip.

    The chip returns something like
        'Ver 6.15 04/26/2013\\r\\n(c) Roving Networks\\r\\n'

    Note that the version must be higher than 6.11 to support HID profile.

    Returns:
      the firmware version
    """
    return self.SerialSendReceive(self.CMD_GET_FIRMWARE_VERSION,
                                  expect_in='Ver',
                                  msg='getting firmware version')

  def GetOperationMode(self):
    """Get the operation mode.

    Returns:
      the operation mode
    """
    result = self.SerialSendReceive(self.CMD_GET_OPERATION_MODE,
                                    msg='getting operation mode')
    return self.OPERATION_MODE.get(result)

  def SetMasterMode(self):
    """Set the chip to master mode.

    Returns:
      True if setting master mode successfully.
    """
    self.SerialSendReceive(self.CMD_SET_MASTER_MODE,
                           expect=self.AOK,
                           msg='setting master mode')
    return True

  def SetSlaveMode(self):
    """Set the chip to slave mode.

    Returns:
      True if setting slave mode successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SLAVE_MODE,
                           expect=self.AOK,
                           msg='setting slave mode')
    return True

  def GetAuthenticationMode(self):
    """Get the authentication mode.

    Returns:
      a string representing the authentication mode
    """
    result = self.SerialSendReceive(self.CMD_GET_AUTHENTICATION_MODE,
                                    msg='getting authentication mode')
    return self.AUTHENTICATION_MODE.get(result)

  def SetAuthenticationMode(self, mode):
    """Set the authentication mode to the specified mode.

    Args:
      mode: the authentication mode

    Returns:
      True if setting the mode successfully.
    """
    if mode not in self.AUTHENTICATION_MODE:
      raise RN42Exception('The mode "%s" is not supported.' % mode)

    self.SerialSendReceive(self.CMD_SET_AUTHENTICATION_MODE + mode,
                           expect=self.AOK,
                           msg='setting authentication mode "%s"' % mode)
    return True

  def GetServiceProfile(self):
    """Get the service profile.

    Returns:
      a string representing the service profile
    """
    result = self.SerialSendReceive(self.CMD_GET_SERVICE_PROFILE,
                                    msg='getting service profile')
    return self.SERVICE_PROFILE.get(result)

  def SetServiceProfileSPP(self):
    """Set SPP as service profile.

    Returns:
      True if setting SPP profile successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SERVICE_PROFILE_SPP,
                           expect=self.AOK,
                           msg='setting SPP as service profile')
    return True

  def SetServiceProfileHID(self):
    """Set HID as service profile.

    Returns:
      True if setting HID profile successfully.
    """
    self.SerialSendReceive(self.CMD_SET_SERVICE_PROFILE_HID,
                           expect=self.AOK,
                           msg='setting HID as service profile')
    return True

  def GetLocalBluetoothAddress(self):
    """Get the local RN-42 bluetooth mac address.

    Returns:
      the bluetooth mac address of the kit
    """
    return self.SerialSendReceive(self.CMD_GET_RN42_BLUETOOTH_MAC,
                                  msg='getting local bluetooth address')

  def GetConnectionStatus(self):
    """Get the connection status.

    the connection status returned from the kit could be
    '0,0,0': not connected
    '1,0,0': connected

    Returns:
      Ture if RN-42 is connected.
    """
    result = self.SerialSendReceive(self.CMD_GET_CONNECTION_STATUS,
                                    msg='getting connection status')
    connection = result.split(',')[0]
    return connection == '1'

  def EnableConnectionStatusMessage(self):
    """Enable the connection status message.

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
    """Get the bluetooth mac address of the current connected remote host.

    Returns:
      the bluetooth mac address of the remote connected device if applicable,
      or None if there is no remote connected device.
    """
    result = self.SerialSendReceive(self.CMD_GET_REMOTE_CONNECTED_BLUETOOTH_MAC,
                                    msg='getting local bluetooth address')
    #  result is '000000000000' if there is no remote connected device
    return None if result == '000000000000' else result

  def GetHIDDeviceType(self):
    """Get the HID device type.

    Returns:
      a string representing the HID device type
    """
    result = self.SerialSendReceive(self.CMD_GET_HID,
                                    msg='getting HID device type')
    return self.HID_DEVICE_TYPE.get(result)

  def SetHIDKeyboard(self):
    """Set keyboard as the HID device.

    Returns:
      True if setting keyboard as the HID device successfully.
    """
    self.SerialSendReceive(self.CMD_SET_HID_KEYBOARD,
                           expect=self.AOK,
                           msg='setting keyboard as HID device')
    return True

  def SetHIDGamepad(self):
    """Set game pad as the HID device.

    Returns:
      True if setting game pad as the HID device successfully.
    """
    self.SerialSendReceive(self.CMD_SET_HID_GAMEPAD,
                           expect=self.AOK,
                           msg='setting gamepad as HID device')
    return True

  def SetHIDMouse(self):
    """Set mouse as the HID device.

    Returns:
      True if setting mouse as the HID device successfully.
    """
    self.SerialSendReceive(self.CMD_SET_HID_MOUSE,
                           expect=self.AOK,
                           msg='setting mouse as HID device')
    return True

  def SetHIDCombo(self):
    """Set combo as the HID device.

    Returns:
      True if setting combo as the HID device successfully.
    """
    self.SerialSendReceive(self.CMD_SET_HID_COMBO,
                           expect=self.AOK,
                           msg='setting combo as HID device')
    return True

  def SetHIDJoystick(self):
    """Set joystick as the HID device.

    Returns:
      True if setting joystick as the HID device successfully.
    """
    self.SerialSendReceive(self.CMD_SET_HID_JOYSTICK,
                           expect=self.AOK,
                           msg='setting joystick as HID device')
    return True

  def SetRemoteAddress(self, remote_address):
    """Set the remote bluetooth address.

    Args:
      remote_address: the remote bluetooth address such as '0029951AD46F'
                      when given '00:29:95:1A:D4:6F', it will be
                      converted to '0029951AD46F' automatically.

    Returns:
      True if setting the remote address successfully.
    """
    reduced_remote_address = remote_address.replace(':', '')
    if len(reduced_remote_address) != 12:
      raise RN42Exception('"%s" is not a valid bluetooth address.' %
                          remote_address)

    self.SerialSendReceive(self.CMD_SET_REMOTE_ADDRESS + reduced_remote_address,
                           expect=self.AOK,
                           msg='setting a remote address ' + remote_address)
    return True

  def Connect(self):
    """Connect to the stored remote bluetooth address.

    When a connection command is issued, it first returns a response 'TRYING'.
    If the connection is successful, it returns something like
    '...%CONNECT,6C29951AD46F,0'  where '6C29951AD46F' is the remote_address
    after a few seconds.

    Returns:
      True if connecting to the stored remote address successfully, and
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

  def ConnectToRemoteAddress(self, remote_address):
    """Connect to the remote address.

    This is performed by the following steps:
    1. Set the remote address to connect.
    2. Connect to the remote address.

    Args:
      remote_address: the remote bluetooth address such as '0029951AD46F'
                      when given '00:29:95:1A:D4:6F', it will be
                      converted to '0029951AD46F' automatically.

    Returns:
      True if connecting to the remote address successfully; otherwise, False.
    """
    return self.SetRemoteAddress(remote_address) and self.Connect()

  def Disconnect(self):
    """Disconnect from the remote device.

    This is done by sending a 0x0.
    A '%DISCONNECT' string would be received as a response.

    Returns:
      True if disconnecting from the remote device successfully.
    """
    self.SerialSendReceive(self.CMD_DISCONNECT_REMOTE_ADDRESS,
                           expect_in='DISCONNECT',
                           msg='disconnecting from the remote device')
    return True

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

  def RawMouseCodes(self, buttons=0, x_stop=0, y_stop=0, wheel=0):
    """Generate the codes in mouse raw report format.

    This method sends data in the raw report mode. The first start
    byte chr(UART_INPUT_RAW_MODE) is stripped and the following bytes
    are sent without interpretation.

    For example, generate the codes of moving cursor 100 pixels left
    and 50 pixels down:
      codes = RawMouseCodes(x_stop=-100, y_stop=50)

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

      Args:
        value: a signed integer

      Returns:
        a signed character value
      """
      if value <= -127:
        # If the negative value is too small, limit it to -127.
        # Then perform two's complement: -127 + 256 = 129
        return 129
      elif value < 0:
        # Perform two's complement.
        return value + 256
      elif value > 127:
        # If the positive value is too large, limit it to 127
        # to prevent it from becoming negative.
        return 127
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


def GetRN42Info():
  """A simple demo of getting RN-42 information."""
  rn42 = RN42()
  print 'enter:', rn42.EnterCommandMode()
  print 'chip name:', rn42.GetChipName()
  print 'firmware version:', rn42.GetFirmwareVersion()
  print 'operation mode:', rn42.GetOperationMode()
  print 'authentication mode:', rn42.GetAuthenticationMode()
  print 'service profile:', rn42.GetServiceProfile()
  print 'local bluetooth address:', rn42.GetLocalBluetoothAddress()
  print 'connection status:', rn42.GetConnectionStatus()
  print 'remote bluetooth address:', rn42.GetRemoteConnectedBluetoothAddress()
  print 'HID device type:', rn42.GetHIDDeviceType()
  print 'leave:', rn42.LeaveCommandMode()


if __name__ == '__main__':
  GetRN42Info()
