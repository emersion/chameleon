# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides an abstraction of a Bluefruit LE Friend kit.

This module was implemented so as to reuse as much as possible of the interface
from the RN42 abstraction. Since the AT command set of the Bluefruit LE Friend
is generally simpler and higher-level than that of the RN42, and is
LE-specific, some commands are no-ops, and some just fake out certain
functionality.
"""
# TODO(josephsih): Attempt to get features we need added to the firmware.


import logging
import time

from bluetooth_peripheral_kit import GetKitInfo
from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_peripheral_kit import PeripheralKitException


class BluefruitLEException(PeripheralKitException):
  """A dummy exception for BluefruitLE-related tasks"""
  pass


class BluefruitLE(PeripheralKit):
  """This is an abstraction of the Adafruit Bluefruit LE Friend kit.

  This was written specifically for the v2 hardare running the v0.7.7 firmware.
  Check the version with the command 'ATI', or by calling GetFirmwareVersion().
  For more details, see:
  https://learn.adafruit.com/introducing-adafruit-ble-bluetooth-low-energy-friend?view=all
  """

  # Serial port settings (override)
  # NOTE: Versions v3 and higher of this kit have a different driver. We use v2.
  DRIVER = 'ftdi_sio'
  BAUDRATE = 9600
  USB_VID = '0403'
  USB_PID = '6015'

  # Timing info
  RESET_SLEEP_SECONDS = 3

  # HID Types that the Bleufruit LE Combines into one
  UNDISTINGUISHABLE_HID_TYPES = [PeripheralKit.KEYBOARD,
                                 PeripheralKit.MOUSE,
                                 PeripheralKit.COMBO]

  # A reason for not being able to do something
  UNSUPPORTED_REASON = "Not supported by Bluefruit LE as of v0.7.7"

  # Common Command Parts
  AT = 'AT'
  RESULT_OK = 'OK'
  RESULT_ERROR = 'ERROR'
  SUFFIX_EXISTS = '?'
  SUFFIX_ENABLE = '=1'

  # Specific Commands
  CMD_FACTORY_RESET = '+FACTORYRESET'
  CMD_GET_DEVICE_NAME = '+GAPDEVNAME'
  CMD_INFO = 'I'
  CMD_PARTIAL_RESET = 'Z'
  CMD_GET_CONNECTION_STATUS = '+GAPGETCONN'
  CMD_GET_LOCAL_ADDRESS = '+BLEGETADDR'
  CMD_GET_REMOTE_ADDRESS = '+BLEGETPEERADDR'
  CMD_DISCONNECT = '+GAPDISCONNECT'
  CMD_BLE_HID_ENABLE = '+BLEHIDEN'
  CMD_BLE_HID_GAMEPAD_ENABLE = '+BLEHIDGAMEPADEN'

  def _ValidateAndExtractResult(self, command, result, validate_only, message):
    """Validate Bluefruit LE command result, and extract return value.

    This only works for commands that return OK in all meaningful,
    recoverable-error result cases, and for commands that also may return a
    single-line result (See valdate_only).

    The Bluefruit LE kit, unlike the RN42, has echo enabled by default.
    So, for a setter command AT+SOMETHING=1, we get:
    AT+SOMETHING=1\\r\\n
    OK\\r\\n
    But for a getter command AT+SOMETHING, we might get:
    AT+SOMETHING\\r\\n
    1\\r\\n
    OK\\r\\n
    [Note that \\ above should be read as a single backslash.]
    This method validates and optionally extracts a result.

    Args:
      command: The command sent with SerialSendReceive
      result: The result of the SerialSendReceive call
      validate_only: Do not extract a result when True, just confirm success
      message: A SerialSendReceive-stlye message to put into debug logs.

    Returns:
      True if validate_only and validation succeeds, otherwise the string
      returned by the command if validation succeeds

    Raises:
      BluefruitLEException if validation fails.
    """
    # TODO(josephsih): Make this optionally handle more lines and optionally
    # handle ERROR as a bool result.
    result_parts = result.split(self.NEWLINE)
    actual_length = len(result_parts)
    expected_length = 2 if validate_only else 3
    ok_index = 1 if validate_only else 2
    if actual_length != expected_length:
      values = (message, expected_length, actual_length, result)
      error = "Incorrect number of lines in %s, wanted %s, got %s: %s" % values
      logging.error(error)
      raise BluefruitLEException(error)
    if result_parts[0] != command: # Command always echoed first
      values = (message, command, result)
      error = "Unexpected command echo in %s, wanted %s, got: %s" % values
      logging.error(error)
      raise BluefruitLEException(error)
    if result_parts[ok_index] != self.RESULT_OK:
      values = (message, self.RESULT_OK, result)
      error = "Not-OK command result in %s, wanted %s, got: %s" % values
      logging.error(error)
      raise BluefruitLEException(error)
    else:
      return True if validate_only else result_parts[1]

  def __init__(self):
    """Initialize the state of this kit abstraction.

    Initially unknown, but current code assumes an adapter reset, more or less.
    This seems reasonable as some, but not all, state is lost across reboots,
    and this object is generally only create on daemon restarts, which can
    include reboots.
    """
    super(BluefruitLE, self).__init__()
    # The HID type when the Bluefruit can't distinguish (mouse/keyboard/combo)
    # This is because it's always a combo internally
    # Note it's Appearance value is (apparently always a keyboard like this?)
    self._hid_fake_type = None

  def GetCapabilities(self):
    """What can this kit do/not do that tests need to adjust for?

    Returns:
      A dictionary from PeripheralKit.CAP_* strings to an appropriate value.
      See PeripheralKit for details.
    """
    return {PeripheralKit.CAP_TRANSPORTS: [PeripheralKit.TRANSPORT_LE],
            PeripheralKit.CAP_HAS_PIN: False,
            PeripheralKit.CAP_INIT_CONNECT: False}

  # TODO(alent): Run AT+MODESWITCHEN=local,0 to disable mode switch. (This would
  # prevent us from leaving command mode if we get +++, w/o escaping + to \+.)
  # TODO(alent): Way to detect mode switch or mode is wrong?
  def EnterCommandMode(self):
    """Make the kit enter command mode.

    Enter command mode, creating the serial connection if necessary.
    This must happen before other methods can be called, as they generally rely
    on sending commands.

    Long story short, the Bluefruit LE Friend has a physical mode switch,
    so when it starts up it should be set to command mode (assuming that the
    switch was set properly).
    It can switch at runtime with +++\\r\\n over the USB tty, unless disabled.
    We never *need* to enter/leave command mode, unlike the RN42, so no-op it.
    [Note that \\ above should be read as a single backslash.]

    Returns:
      True if the kit succeessfully entered command mode.

    Raises:
      PeripheralKitException if there is an error in serial communication or
      if the kit gives an unexpected response.
      A kit-specific Exception if something else goes wrong.
    """
    if not self._serial:
      self.CreateSerialDevice()
    if not self._command_mode:
      self._command_mode = True
    return True

  def LeaveCommandMode(self, force=False):
    """Make the kit leave command mode.

    As above, we never switch out of command mode.

    Args:
      force: True if we want to ignore potential errors and attempt to
             leave command mode regardless.

    Returns:
      True if the kit left command mode successfully.
    """
    if self._command_mode or force:
      self._command_mode = False
    return True

  def Reboot(self):
    """Reboot (or partially reset) the kit.

    Rebooting or resetting the kit is required to make some settings take
    effect after they are changed.

    This destroys bonding data! Only do this when breaking the bond with the
    remote device under test is acceptable.

    Returns:
      True if the kit rebooted successfully.

    Raises:
      A kit-specifc exception if something goes wrong.
    """
    command = self.AT + self.CMD_PARTIAL_RESET
    message = '(partially) resetting Bluefruit LE'
    result = self.SerialSendReceive(command, msg=message)
    return self._ValidateAndExtractResult(command, result, True, message)

  def FactoryReset(self):
    """Factory reset the kit.

    Reset the kit to the factory defaults.

    Returns:
      True if the kit is reset successfully.

    Raises:
      A kit-specifc exception if something goes wrong.
    """
    command = self.AT + self.CMD_FACTORY_RESET
    message = 'factory reset Bluefruit LE'
    result = self.SerialSendReceive(command, msg=message)
    # TODO(alent): Need the wait?
    time.sleep(self.RESET_SLEEP_SECONDS)
    return self._ValidateAndExtractResult(command, result, True, message)

  def GetAdvertisedName(self):
    """Get the name advertised by the kit.

    Returns:
      The name that the kit advertises to other Bluetooth devices.
    """
    command = self.AT + self.CMD_GET_DEVICE_NAME
    message = 'getting the advertisied name of the kit'
    result = self.SerialSendReceive(command, msg=message)
    return self._ValidateAndExtractResult(command, result, False, message)

  def GetFirmwareVersion(self):
    """Get the firmware version of the kit.

    This is useful for checking what features are supported if we want to
    support muliple versions of some kit.

    An example result is below:
    ATI\\r\\n\\r\\n
    BLEFRIEND32\\r\\n
    nRF51822 QFACA10\\r\\n
    6C280528C970FCDF\\r\\n
    0.7.7\\r\\n
    0.7.7\\r\\n
    Dec 13 2016\\r\\n
    S110 8.0.0, 0.2\\r\\n
    OK
    [Note that \\ above should be read as a single backslash.]

    Returns:
      The firmware version of the kit.
    """
    # TODO(alent): Generalize _ValidateAndExtractResult to do this?
    result = self.SerialSendReceive(self.AT + self.CMD_INFO,
                                    msg='getting Board Info')
    info = result.split(self.NEWLINE)
    # The 5th line of result contains the version that we want, probably.
    return info[4]

  def GetOperationMode(self):
    """Get the operation mode.

    This is master/slave in Bluetooth BR/EDR; the Bluetooth LE equivalent is
    central/peripheral. For legacy reasons, we call it MASTER or SLAVE only.

    The Bluefruit LE Friend does not support the central role, only peripheral.

    Returns:
      The operation mode of the kit.
    """
    # TODO(alent): Better way to propagate this constant?
    # TODO(alent): Is PERIPHERAL more appropriate for BLE? Does this matter?
    logging.debug("GetOperationMode is a NOP on BluefruitLE")
    return "SLAVE"

  def SetMasterMode(self):
    """Set the kit to central mode.

    In BLE, this would be the Central role.
    The Bluefruit LE Friend firmware can't do this.

    Returns:
      True if central mode was set successfully.

    Raises:
      A kit-specific exception if central mode is unsupported.
    """
    error_msg = "Failed to set master/central mode: " + self.UNSUPPORTED_REASON
    logging.error(error_msg)
    raise BluefruitLEException(error_msg)

  def SetSlaveMode(self):
    """Set the kit to slave/peripheral mode.

    Silently succeeds, because the Bleufruit LE is always a PERIPHERAL

    Returns:
      True if slave/peripheral mode was set successfully.

    Raises:
      A kit-specific exception if slave/peripheral mode is unsupported.
    """
    logging.debug("SetSlaveMode is a NOP on BluefruitLE")
    return True

  def GetAuthenticationMode(self):
    """Get the authentication mode.

    This specifies how the device will authenticate with the DUT, for example,
    a PIN code may be used.

    Returns:
      The authentication mode of the kit (from the choices in PeripheralKit).
    """
    logging.debug("GetAuthenticationMode is a NOP on BluefruitLE")
    # TODO(alent): Fake PIN code necessary to make existing code work?
    # TODO(alent): implement NONE?
    return PeripheralKit.SSP_JUST_WORK_MODE

  def SetAuthenticationMode(self, mode):
    """Set the authentication mode to the specified mode.

    If mode is PIN_CODE_MODE, implementations must ensure the default PIN
    is set by calling _SetDefaultPinCode() as appropriate.

    Args:
      mode: the desired authentication mode (specified in PeripheralKit)

    Returns:
      True if the mode was set successfully,

    Raises:
      A kit-specific exception if given mode is not supported.
    """
    if mode == PeripheralKit.SSP_JUST_WORK_MODE:
      return True
    else:
      error_msg = "Bluefruit LE does not support authentication mode: %s" % mode
      error_msg = error_msg + ": " + self.UNSUPPORTED_REASON
      logging.error(error_msg)
      raise BluefruitLEException(error_msg)

  def GetPinCode(self):
    """Get the pin code.

    Returns:
      A string representing the pin code,
      None if there is no pin code stored.
    """
    warn_msg = "Bluefruit LE does not support PIN code mode, none exists: "
    warn_msg = warn_msg + self.UNSUPPORTED_REASON
    logging.warn(warn_msg)
    return None

  def SetPinCode(self, pin):
    """Set the pin code.

    This is not supported.

    Returns:
      True if the pin code is set successfully,
      False if the pin code is invalid.
    """
    warn_msg = "Bluefruit LE does not support PIN code mode, none exists: "
    warn_msg = warn_msg + self.UNSUPPORTED_REASON
    logging.warn(warn_msg)
    return False

  def GetServiceProfile(self):
    """Get the service profile.

    Returns:
      The service profile currently in use (as per constant in PeripheralKit)
    """
    # TODO(alent): Move this constant to PeripheralKit?
    logging.debug("GetServiceProfile is a NOP on BluefruitLE")
    return "HID"

  def SetServiceProfileSPP(self):
    """Set SPP as the service profile.

    In BLE, this would be something like a UART service.
    The Bluefruit LE Friend firmware can do that, but,
    the GATT profile is a proprietary Nordic Semiconductor one.
    For now, unrelated to our HID efforts, so don't bother.

    Returns:
      True if the service profile was set to SPP successfully.

    Raises:
      A kit-specifc exception if unsuppported.
    """
    error_msg = "Failed to set SPP service profile: " + self.UNSUPPORTED_REASON
    logging.error(error_msg)
    raise BluefruitLEException(error_msg)

  def SetServiceProfileHID(self):
    """Set HID as the service profile.

    This is currently a NOP on BluefruitLE, as it currently does only HID.

    Returns:
      True if the service profile was set to HID successfully.
    """
    logging.debug("GetAuthenticationMode is a NOP on BluefruitLE")
    return True

  def GetLocalBluetoothAddress(self):
    """Get the local (kit's) Bluetooth MAC address.

    The kit should always return a valid MAC address in the proper format:
    12 digits with colons between each pair, like so: '00:06:66:75:A9:6F'

    Returns:
      The Bluetooth MAC address of the kit
    """
    command = self.AT + self.CMD_GET_LOCAL_ADDRESS
    message = 'getting local (BluefruitLE\'s) MAC address'
    result = self.SerialSendReceive(command, msg=message)
    return self._ValidateAndExtractResult(command, result, False, message)

  def GetConnectionStatus(self):
    """Get the connection status.

    This indicates that the kit is connected to a remote device, usually the
    DUT.

    The kit will give us a 0 or 1 as a string, which we can parse into a bool.

    Returns:
      True if the kit is connected to a remote device.
    """
    command = self.AT + self.CMD_GET_CONNECTION_STATUS
    message = 'getting connection status'
    result = self.SerialSendReceive(command, msg=message)
    extracted = self._ValidateAndExtractResult(command, result, False, message)
    return extracted == '1'

  def EnableConnectionStatusMessage(self):
    """No-op enable connection status message.

    This does nothing and is not extant or necessary on the Bluefruit LE Friend.

    Returns:
      True
    """
    logging.debug("EnableConnectionStatusMessage is a NOP on BluefruitLE")
    return True

  def DisableConnectionStatusMessage(self):
    """No-op disable connection status message.

    This does nothing and is not extant or necessary on the Bluefruit LE Friend.

    Returns:
      True
    """
    logging.debug("DisableConnectionStatusMessage is a NOP on BluefruitLE")
    return True

  def GetRemoteConnectedBluetoothAddress(self):
    """Get the Bluetooth MAC address of the current connected remote host.

    On the Bluefruit LE, the docs indicate that AP+BLEGETPEERADDR, should give
    ERROR if not connected. For some reason, I get garbage instead, even when
    the device is not bonded. These semantics might differ slightly, but let's
    just use connection status instead of the buggy command.
    Maybe this will change in firmware versions > v0.7.7.

    Returns:
      The Bluetooth MAC address of the remote connected device if applicable,
      or None if there is no remote connected device. If not None, this will
      be properly formatted as a 12-digit MAC address with colons.
    """
    # TODO(josephsih): Investigate why this doesn't work
    # Not connected, do nothing
    if not self.GetConnectionStatus():
      return None
    # Otherwise, run the command:
    command = self.AT + self.CMD_GET_REMOTE_ADDRESS
    message = 'getting remote device\'s (DUT\'s) Bluetooth MAC'
    result = self.SerialSendReceive(command, msg=message)
    return self._ValidateAndExtractResult(command, result, False, message)

  def GetHIDDeviceType(self):
    # TODO(alent): Better documentation.
    """Get the HID type.

    The kit will give us a 0 or 1 as a string, which we can parse into a bool.

    Returns:
      A string representing the HID type (from PeripheralKit)
    """
    command_hid = self.AT + self.CMD_BLE_HID_ENABLE
    message_hid = 'getting HID enabled status, to determine device type'
    result_hid = self.SerialSendReceive(command_hid, msg=message_hid)
    extracted_hid = self._ValidateAndExtractResult(command_hid, result_hid,
                                                   False, message_hid)
    is_combo = extracted_hid == '1'
    command_gamepad = self.AT + self.CMD_BLE_HID_GAMEPAD_ENABLE
    message_gamepad = 'getting gamepad enabled status, to determine device type'
    result_gamepad = self.SerialSendReceive(command_gamepad,
                                            msg=message_gamepad)
    extracted_gamepad = self._ValidateAndExtractResult(command_gamepad,
                                                       result_gamepad, False,
                                                       message_gamepad)
    is_gamepad = extracted_gamepad == '1'
    if is_gamepad:
      return PeripheralKit.GAMEPAD
    elif is_combo and self._hid_fake_type:
      return self._hid_fake_type
    else:
      # TODO(alent): Formally describe error in this API.
      logging.error("Current HID Type is None")
      return None

  def SetHIDType(self, device_type):
    """Set HID type to the specified device type.

    Args:
      device_type: the HID type to emulate, from PeripheralKit

    Returns:
      True if successful

    Raises:
      A kit-specific exception if that device type is not supported.
    """
    device_needs_faking = device_type in self.UNDISTINGUISHABLE_HID_TYPES
    if device_needs_faking:
      command_of_type = self.CMD_BLE_HID_ENABLE
    elif device_type == PeripheralKit.GAMEPAD:
      command_of_type = self.CMD_BLE_HID_GAMEPAD_ENABLE
    else:
      error_msg = "Failed to set HID type, not supported: %s" % device_type
      logging.error(error_msg)
      raise BluefruitLEException(error_msg)
    command = self.AT + command_of_type + self.SUFFIX_ENABLE
    message = 'setting %s as HID type' % device_type
    result = self.SerialSendReceive(command, msg=message)
    extracted = self._ValidateAndExtractResult(command, result, True, message)
    if extracted:
      if device_needs_faking:
        self._hid_fake_type = device_type
      else:
        self._hid_fake_type = None
    return extracted

  def GetClassOfService(self):
    """Get the class of service, if supported.

    Not supported on Bluefruit LE, so None.

    Returns:
      None, the only reasonable value for BLE-only devices.
    """
    logging.debug("GetClassOfService is a NOP on BluefruitLE")
    return None

  def SetClassOfService(self, class_of_service):
    """Set the class of service, if supported.

    The class of service is a number usually assigned by the Bluetooth SIG.

    Not supported on Bluefruit LE, but fake it.

    Args:
      class_of_service: A decimal integer representing the class of service.

    Returns:
      True as this action is not supported.
    """
    logging.debug("SetClassOfService is a NOP on BluefruitLE")
    return True

  def GetClassOfDevice(self):
    """Get the class of device, if supported.

    Not supported on Bluefruit LE, so None.

    Returns:
      None, the only reasonable value for BLE-only devices.
    """
    logging.debug("GetClassOfDevice is a NOP on BluefruitLE")
    return None

  def SetClassOfDevice(self, device_type):
    """Set the class of device, if supported.

    The class of device is a number usually assigned by the Bluetooth SIG.

    Not supported on Bluefruit LE, but fake it.

    Args:
      device_type: A decimal integer representing the class of device.

    Returns:
      True as this action is not supported.
    """
    logging.debug("SetClassOfDevice is a NOP on BluefruitLE")
    return True

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
    error_msg = "Failed to set remote address: " + self.UNSUPPORTED_REASON
    logging.error(error_msg)
    raise BluefruitLEException(error_msg)

  def Connect(self):
    """Connect to the stored remote bluetooth address.

    In the case of a timeout (or a failure causing an exception), the caller
    is responsible for retrying when appropriate.

    Returns:
      True if connecting to the stored remote address succeeded, or
      False if a timeout occurs.
    """
    error_msg = "Failed to connect to remote device: " + self.UNSUPPORTED_REASON
    logging.error(error_msg)
    raise BluefruitLEException(error_msg)

  def Disconnect(self):
    """Disconnect from the remote device.

    Specifically, this causes the peripheral emulation kit to disconnect from
    the remote connected device, usually the DUT.

    Returns:
      True if disconnecting from the remote device succeeded.
    """
    command = self.AT + self.CMD_DISCONNECT
    message = 'disconnecting from the remote device (probably the DUT)'
    result = self.SerialSendReceive(command, msg=message)
    return self._ValidateAndExtractResult(command, result, True, message)


if __name__ == '__main__':
  GetKitInfo(BluefruitLE)
