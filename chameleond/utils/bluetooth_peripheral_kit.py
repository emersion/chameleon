# -*- coding: utf-8 -*-
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common functionality for abstracting peripheral emulation kits."""

import logging
import serial
import time

import serial_utils
import usb_powercycle_util

class PeripheralKitException(Exception):
  """A dummpy exception class for the PeripheralKit class."""
  pass


class PeripheralKit(object):
  """A generalized abstraction of a Bluetooth peripheral emulation kit

  Note: every public member method should
        return True or a non-None object if successful;
        return False or Raise an exception (preferable) otherwise.
  """

  # Serial port settings
  # Kit implementations should set these constants appropriately.
  # Use only the kit's default settings, to allow kits to be factory reset.
  # Default settings common to all current kits have been provided,
  # with the exception of driver, baud rate, and VID/PID
  DRIVER = None # The name of the kernel driver. Ex: 'ftdi_sio'
  BAUDRATE = None # The default baud rate of a kit's serial interface
  BYTESIZE = serial.EIGHTBITS
  PARITY = serial.PARITY_NONE
  STOPBITS = serial.STOPBITS_ONE
  USB_VID = None # The USB VID (Vendor ID) of the kit, as a hexadecimal string
  USB_PID = None # The USB PID (Product ID) of the kit, as a hexadecimal string

  # Timing settings
  # Serial commands will retry (RETRY + 1) times,
  RETRY = 2
  # TODO(josephsih): Improve timing values, find/describe source thereof
  # with RETRY_INTERVAL_SECS seconds between retries.
  RETRY_INTERVAL_SECS = 0.1
  # Wait CREATE_SERIAL_DEVICE_SLEEP_SECS seconds between creating a serial
  # device and returning.
  CREATE_SERIAL_DEVICE_SLEEP_SECS = 1

  # A newline is a carriage return '\r' followed by line feed '\n'.
  NEWLINE = '\r\n'

  # Supported device types
  KEYBOARD = 'KEYBOARD'
  GAMEPAD = 'GAMEPAD'
  MOUSE = 'MOUSE'
  COMBO = 'COMBO'
  JOYSTICK = 'JOYSTICK'
  A2DP_SINK = 'A2DP_SINK'

  # Authentication modes (currently references SSP, which is BR/EDR only)
  OPEN_MODE = 'OPEN'
  SSP_KEYBOARD_MODE = 'SSP_KEYBOARD'
  SSP_JUST_WORK_MODE = 'SSP_JUST_WORK'
  PIN_CODE_MODE = 'PIN_CODE'

  # Capability strings
  # NOTE: Strings updated here must be kept in sync with Autotest.
  # A list of supported transports, from TRANSPORT_* below.
  CAP_TRANSPORTS = "CAP_TRANSPORTS"
  # Strings representing supported transports.
  # A dual device would have ["TRANSPORT_LE","TRANSPORT_BREDR"]
  TRANSPORT_LE = "TRANSPORT_LE"
  TRANSPORT_BREDR = "TRANSPORT_BREDR"
  # True if gettigng a PIN code is allowed & meaningful.
  CAP_HAS_PIN = "CAP_HAS_PIN"
  # True if the kit can initiate a connection (esp. to a paired device)
  CAP_INIT_CONNECT = "CAP_INIT_CONNECT"

  # Kit implementations should set these values if the generic methods that
  # use them are a desired part of the implementation
  # The default class of service
  DEFAULT_CLASS_OF_SERVICE = None
  # The default PIN code
  DEFAULT_PIN_CODE = None

  # Mouse constants
  MOUSE_VALUE_MIN = -127
  MOUSE_VALUE_MAX = 127
  MOUSE_BUTTON_LEFT = "MOUSE_BUTTON_LEFT"
  MOUSE_BUTTON_RIGHT = "MOUSE_BUTTON_RIGHT"

  def __init__(self):
    self._command_mode = False
    self._closed = False
    self._serial = None
    self._tty = None
    self._buttons_pressed = set()

  def __del__(self):
    self.Close()

  def SerialSendReceive(self, command, expect='', expect_in='',
                        msg='serial SendReceive()', send_newline=True):
    """A wrapper of SerialDevice.SendReceive().

    Args:
      command: the serial command to send
      expect: expect the exact string matching the response
      expect_in: expect the string in the response
      msg: the message to log
      send_newline: send a newline following the command

    Returns:
      the result received from the serial console

    Raises:
      PeripheralKitException if the response is not expected or if another
      problem occurs.
    """
    try:
      # All commands must end with a newline.
      # size=0 means to receive all waiting characters.
      # Retry a few times since sometimes the serial communication
      # may not be reliable.
      # Strip the result which ends with a newline too.
      full_command = command + self.NEWLINE if send_newline else command
      result = self._serial.SendReceive(full_command,
                                        size=0,
                                        retry=self.RETRY).strip()
      logging.debug('  SerialSendReceive: %s', result)
    except Exception as e:
      logging.error('Failure in %s: %s', msg, e)
      raise PeripheralKitException(msg)

    if ((expect and expect != result) or
        (expect_in and expect_in not in result)):
      # TODO(alent): Make error more helpful!
      error_msg = 'Unexpected response in %s: %s' % (msg, result)
      logging.error(error_msg)
      raise PeripheralKitException(error_msg)

    logging.info('Success in %s: %s', msg, result)
    return result

  def CreateSerialDevice(self):
    """Create a serial device.

    Attempts to create a serial connection.

    Returns:
      True if successful.

    Raises:
      PeripheralKitException if unsuccessful.
    """
    try:
      self._serial = serial_utils.SerialDevice()
    except Exception as e:
      msg = 'Failed to create a serial device: %s' % e
      logging.error(msg)
      raise PeripheralKitException(msg)

    try:
      self._serial.Connect(driver=self.DRIVER,
                           usb_vid=self.USB_VID,
                           usb_pid=self.USB_PID,
                           known_device_set=self.KNOWN_DEVICE_SET,
                           baudrate=self.BAUDRATE,
                           bytesize=self.BYTESIZE,
                           parity=self.PARITY,
                           stopbits=self.STOPBITS)
      self._tty = self._serial.port
      logging.info('Connected to the serial port successfully: %s', self._tty)
    except Exception as e:
      msg = 'Failed to connect to the serial device: %s' % e
      logging.error(msg)
      raise PeripheralKitException(msg)

    self._closed = False
    time.sleep(self.CREATE_SERIAL_DEVICE_SLEEP_SECS)
    return True

  def Close(self):
    """Attempt to close the device gracefully."""
    if not self._closed:
      try:
        # It is possible that the kit has already left command mode. In that
        # case, do not expect any response from the kit.
        self.LeaveCommandMode(force=True)
        self._serial.Disconnect()
        # Ensure serial port is re-created on next run
        self._serial = None
      except Exception as e:
        logging.warn('The serial device was probably already closed: %s', e)
      self._closed = True
    return True

  def CheckSerialConnection(self):
    """Check the USB serial connection between to the kit."""
    if self.KNOWN_DEVICE_SET:
      devices = serial_utils.FindTtyListByUsbVidPid(self.USB_VID, self.USB_PID)
      if devices is None:
        return False
      for device in devices:
        if device['serial'] in self.KNOWN_DEVICE_SET:
          tty = device['port']
          break
    else:
      tty = serial_utils.FindTtyByUsbVidPid(self.USB_VID, self.USB_PID,
                                            driver_name=self.DRIVER)
    logging.info('CheckSerialConnection: port is %s', tty)
    if tty != self._tty:
      logging.warn('CheckSerialConnection: Port %s is not current port %s',
                   tty, self._tty)
    return bool(tty)

  def GetPort(self):
    """Get the tty device path of the serial port.

    Returns:
      A string representing the tty device path of the serial port.
    """
    return self._tty

  def GetCapabilities(self):
    """What can this kit do/not do that tests need to adjust for?

    Returns:
      A dictionary from PeripheralKit.CAP_* strings to an appropriate value.
      See above (CAP_*) for details.
    """
    raise NotImplementedError("Not Implemented")

  def EnterCommandMode(self):
    """Make the kit enter command mode.

    Enter command mode, creating the serial connection if necessary.
    This must happen before other methods can be called, as they generally rely
    on sending commands.

    Kit implementations must create the serial device if it does not exist.
    Suggested code fragment:
    if not self._serial:
      self.CreateSerialDevice()

    Returns:
      True if the kit succeessfully entered command mode.

    Raises:
      PeripheralKitException if there is an error in serial communication or
      if the kit gives an unexpected response.
      A kit-specific Exception if something else goes wrong.
    """
    raise NotImplementedError("Not Implemented")

  def LeaveCommandMode(self, force=False):
    """Make the kit leave command mode.

    Kit implementations must implement appropriate behavior for force.
    Suggested code fragment:
    if not self._closed or force:
      # Leave command mode

    Args:
      force: True if we want to ignore potential errors and attempt to
             leave command mode regardless.

    Returns:
      True if the kit left command mode successfully.
    """
    raise NotImplementedError("Not Implemented")

  def Reboot(self):
    """Reboot (or partially reset) the kit.

    Rebooting or resetting the kit is required to make some settings take
    effect after they are changed. On some kits, this may result in a
    partial reset that clears pairing/bonding data.

    Returns:
      True if the kit rebooted successfully.

    Raises:
      A kit-specifc exception if something goes wrong.
    """
    raise NotImplementedError("Not Implemented")

  def FactoryReset(self):
    """Factory reset the kit.

    Reset the kit to the factory defaults.

    Returns:
      True if the kit is reset successfully.

    Raises:
      A kit-specifc exception if something goes wrong.
    """
    raise NotImplementedError("Not Implemented")

  def PowerCycle(self):
    """Power cycle the USB port where kit is attached.

    Power cycle the USB port where kit is connected. This is
    required to reset some kits, since rebooting the chameleond
    host might not power down the kits.

    Returns:
      True if the USB port is power cycled.
    """
    return usb_powercycle_util.PowerCycleUSBPort(self.USB_VID, self.USB_PID)

  def GetAdvertisedName(self):
    """Get the name advertised by the kit.

    Returns:
      The name that the kit advertises to other Bluetooth devices.
    """
    raise NotImplementedError("Not Implemented")

  def GetFirmwareVersion(self):
    """Get the firmware version of the kit.

    This is useful for checking what features are supported if we want to
    support muliple versions of some kit.

    Returns:
      The firmware version of the kit.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): check spec about master/slave roles applicable to LE
  def GetOperationMode(self):
    """Get the operation mode.

    This is master/slave in Bluetooth BR/EDR; the Bluetooth LE equivalent is
    central/peripheral. For legacy reasons, we call it MASTER or SLAVE only.
    Not all kits may support all modes.

    Returns:
      The operation mode of the kit.
    """
    raise NotImplementedError("Not Implemented")

  def SetMasterMode(self):
    """Set the kit to master/central mode.

    Returns:
      True if master/central mode was set successfully.

    Raises:
      A kit-specific exception if master/central mode is unsupported.
    """
    raise NotImplementedError("Not Implemented")

  def SetSlaveMode(self):
    """Set the kit to slave/peripheral mode.

    Returns:
      True if slave/peripheral mode was set successfully.

    Raises:
      A kit-specific exception if slave/peripheral mode is unsupported.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): check spec about authentication modes applicable to LE
  def GetAuthenticationMode(self):
    """Get the authentication mode.

    This specifies how the device will authenticate with the DUT, for example,
    a PIN code may be used.

    Returns:
      The authentication mode of the kit (from the choices in PeripheralKit).
    """
    raise NotImplementedError("Not Implemented")

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
    raise NotImplementedError("Not Implemented")

  def GetPinCode(self):
    """Get the pin code.

    Returns:
      A string representing the pin code,
      None if there is no pin code stored.
    """
    raise NotImplementedError("Not Implemented")

  def SetPinCode(self, pin):
    """Set the pin code.

    Returns:
      True if the pin code is set successfully,

    Raises:
      A kit-specifc exception if the pin code is invalid.
    """
    raise NotImplementedError("Not Implemented")

  def _SetDefaultPinCode(self):
    """Set the default pin code.

    Returns:
      True if the pin code is set to the default value successfully.
    """
    return self.SetPinCode(self.DEFAULT_PIN_CODE)

  def GetServiceProfile(self):
    """Get the service profile.

    Returns:
      The service profile currently in use (as per constant in PeripheralKit)
    """
    # TODO(alent): Is the assetion above about constants and PeripheralKit true?
    raise NotImplementedError("Not Implemented")

  def SetServiceProfileSPP(self):
    """Set SPP as the service profile.

    Returns:
      True if the service profile was set to SPP successfully.

    Raises:
      A kit-specifc exception if unsuppported.
    """
    raise NotImplementedError("Not Implemented")

  def SetServiceProfileHID(self):
    """Set HID as the service profile.

    Returns:
      True if the service profile was set to HID successfully.
    """
    raise NotImplementedError("Not Implemented")

  def GetLocalBluetoothAddress(self):
    """Get the local (kit's) Bluetooth MAC address.

    The kit should always return a valid MAC address in the proper format:
    12 digits with colons between each pair, like so: '00:06:66:75:A9:6F'

    Returns:
      The Bluetooth MAC address of the kit, None if the kit has no MAC address
    """
    raise NotImplementedError("Not Implemented")

  def GetConnectionStatus(self):
    """Get the connection status.

    This indicates that the kit is connected to a remote device, usually the
    DUT.

    Returns:
      True if the kit is connected to a remote device.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): Figure out a better API for such kit-specific actions?
  def EnableConnectionStatusMessage(self):
    """Enable the connection status message.

    On some kits, this is required to use connection-related methods.

    Returns:
      True if enabling the connection status message successfully.
    """
    raise NotImplementedError("Not Implemented")

  def DisableConnectionStatusMessage(self):
    """Disable the connection status message.

    Returns:
      True if disabling the connection status message successfully.
    """
    raise NotImplementedError("Not Implemented")

  def GetRemoteConnectedBluetoothAddress(self):
    """Get the Bluetooth MAC address of the current connected remote host.

    Returns:
      The Bluetooth MAC address of the remote connected device if applicable,
      or None if there is no remote connected device. If not None, this will
      be properly formatted as a 12-digit MAC address with colons.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): Rename to GetHIDType to be less redundant/
  def GetHIDDeviceType(self):
    """Get the HID type.

    Returns:
      A string representing the HID type (from PeripheralKit)
    """
    raise NotImplementedError("Not Implemented")

  def SetHIDType(self, device_type):
    """Set HID type to the specified device type.

    Args:
      device_type: the HID type to emulate, from PeripheralKit

    Returns:
      True if successful

    Raises:
      A kit-specific exception if that device type is not supported.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): Figure out how to better indicate BR/EDR-only functionality
  # The reason for the None result is that that is what the autotest API
  # expects on LE, True if not supported to allow tests to complete.
  def GetClassOfService(self):
    """Get the class of service, if supported.

    Usually, a hexadeciaml string is used to represent the class of service,
    which usually uses certain numbers assigned by the Bluetooth SIG.
    In this case, it is provided as decimal.
    Usually supported only on BR/EDR kits.

    Returns:
      A decimal integer representing the class of service, unless unsupported,
      then None.
    """
    raise NotImplementedError("Not Implemented")

  def SetClassOfService(self, class_of_service):
    """Set the class of service, if supported.

    The class of service is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Args:
      class_of_service: A decimal integer representing the class of service.

    Returns:
      True if the class of service was set successfully, or if this action is
      not supported.

    Raises:
      A kit-specific expection if the class of service is not supported.
    """
    raise NotImplementedError("Not Implemented")

  def SetDefaultClassOfService(self):
    """Set the default class of service, if supported.

    Kit implementations must set the constant DEFAULT_CLASS_OF_SERVICE.

    Returns:
      True if the class of service was set to the default successfully,
      or if this action is not supported.
    """
    return self.SetClassOfService(self.DEFAULT_CLASS_OF_SERVICE)

  def GetClassOfDevice(self):
    """Get the class of device, if supported.

    The kit uses a hexadeciaml string to represent the class of device.
    It is converted to a decimal number as the return value.
    The class of device is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Returns:
      A decimal integer representing the class of device, unless unsupported,
      then None.
    """
    raise NotImplementedError("Not Implemented")

  def SetClassOfDevice(self, device_type):
    """Set the class of device, if supported.

    The class of device is a number usually assigned by the Bluetooth SIG.
    Usually supported only on BR/EDR kits.

    Args:
      device_type: A decimal integer representing the class of device.

    Returns:
      True if the class of device was set successfully, or if this action is
      not supported.

    Raises:
      A kit-specific expection if the class of device is not supported.
    """
    raise NotImplementedError("Not Implemented")

  # TODO(alent): How to handle not supported by kit in the API?
  # TODO(alent): Implement/require validation logic?
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
    raise NotImplementedError("Not Implemented")

  # TODO(alent): API consistency with False vs exception
  def Connect(self):
    """Connect to the stored remote bluetooth address.

    In the case of a timeout (or a failure causing an exception), the caller
    is responsible for retrying when appropriate.

    Returns:
      True if connecting to the stored remote address succeeded, or
      False if a timeout occurs.
    """
    raise NotImplementedError("Not implemented")

  def ConnectToRemoteAddress(self, remote_address):
    """Connect to the remote address.

    This is performed by the following steps:
    1. Set the remote address to connect.
    2. Connect to the remote address.

    Args:
      remote_address: the remote Bluetooth MAC address, which must be given as
                      12 hex digits with colons between each pair.
                      For reference: '00:29:95:1A:D4:6F'

    Returns:
      True if connecting to the remote address succeeded
    """
    return self.SetRemoteAddress(remote_address) and self.Connect()

  def Disconnect(self):
    """Disconnect from the remote device.

    Specifically, this causes the peripheral emulation kit to disconnect from
    the remote connected device, usually the DUT.

    Returns:
      True if disconnecting from the remote device succeeded.
    """
    raise NotImplementedError("Not implemented")

  # Helper methods for implementing a system that remembers button state
  def _MouseButtonStateUnion(self, buttons_to_press):
    """Add to the current set of pressed buttons.

    Args:
      buttons_to_press: A set of buttons, as PeripheralKit MOUSE_BUTTON_*
                        values, that will stay pressed.
    """
    self._buttons_pressed = self._buttons_pressed.union(buttons_to_press)

  def _MouseButtonStateSubtract(self, buttons_to_release):
    """Remove from the current set of pressed buttons.

    Args:
      buttons_to_release: A set of buttons, as PeripheralKit MOUSE_BUTTON_*
                          values, that will be released.
    """
    self._buttons_pressed = self._buttons_pressed.difference(buttons_to_release)

  def _MouseButtonStateClear(self):
    """Clear the mouse button pressed state."""
    self._buttons_pressed = set()

  # Methods starting with "Mouse" should not be exposed to Autotest directly,
  # especially those dealing with button sets.
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
    raise NotImplementedError("Not implemented")

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
    raise NotImplementedError("Not implemented")

  def MousePressButtons(self, buttons):
    """Press the specified mouse buttons.

    The kit will continue to press these buttons until otherwise instructed, or
    until its state has been reset.

    Args:
      buttons: A set of buttons, as PeripheralKit MOUSE_BUTTON_* values, that
               will be pressed (and held down).
    """
    raise NotImplementedError("Not implemented")

  def MouseReleaseAllButtons(self):
    """Release all mouse buttons."""
    raise NotImplementedError("Not implemented")
