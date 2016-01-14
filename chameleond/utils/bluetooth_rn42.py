# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides an abstraction of RN-42 bluetooth chip."""

import logging
import serial

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
  RETRY = 2                   # Try (RETRY + 1) times in total.

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
  CMD_SET_AUTHENTICATION_OPEN_MODE = 'SA,0'   # no authentication
  CMD_SET_AUTHENTICATION_PIN_MODE = 'SA,4'    # host to send a matching pin

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

  # HID device classes
  CMD_GET_HID = 'GH'
  CMD_SET_HID_KEYBOARD = 'SH,0000'
  CMD_SET_HID_GAMEPAD = 'SH,0010'
  CMD_SET_HID_MOUSE = 'SH,0020'
  CMD_SET_HID_COMBO = 'SH,0030'
  CMD_SET_HID_JOYSTICK = 'SH,0040'

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
  AUTHENTICATION_MODE = {
      '0': 'OPEN',
      '1': 'SSP_KEYBOARD',
      '2': 'SSP_JUST_WORK',
      '4': 'PIN_CODE'}

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

    try:
      self._serial = serial_utils.SerialDevice()
    except:
      raise RN42Exception('Fail to create a serial device.')

    try:
      self._serial.Connect(driver=self.DRIVER,
                           baudrate=self.BAUDRATE,
                           bytesize=self.BYTESIZE,
                           parity=self.PARITY,
                           stopbits=self.STOPBITS)
      logging.info('Connect to the serial port successfully.')
    except:
      raise RN42Exception('Fail to connect to the serial device.')

  def __del__(self):
    self.Close()

  def Close(self):
    """Close the device gracefully."""
    if not self._closed:
      self.LeaveCommandMode()
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

  def LeaveCommandMode(self):
    """Make the chip leave command mode.

    Returns:
      True if the kit left the command mode successfully.
    """
    if self._command_mode:
      self.SerialSendReceive(self.CMD_LEAVE_COMMAND_MODE,
                             expect='END',
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
                           expect='Reboot',
                           msg='rebooting RN-42')
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

  def SetAuthenticationOpenMode(self):
    """Set the authentication to open mode (no authentication).

    Returns:
      True if setting open mode successfully.
    """
    self.SerialSendReceive(self.CMD_SET_AUTHENTICATION_OPEN_MODE,
                           expect=self.AOK,
                           msg='setting authentication open mode')
    return True

  def SetAuthenticationPinMode(self):
    """Set the authentication to pin mode (host to send a matching pin).

    Returns:
      True if setting pin code mode successfully.
    """
    self.SerialSendReceive(self.CMD_SET_AUTHENTICATION_PIN_MODE,
                           expect=self.AOK,
                           msg='setting authentication pin mode')
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
