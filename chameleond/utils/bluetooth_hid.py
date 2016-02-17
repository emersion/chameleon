# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides emulation of bluetooth HID devices."""

import logging
import sys
import time

from bluetooth_rn42 import RN42


class BluetoothHIDException(Exception):
  """A dummpy exception class for Bluetooth HID class."""
  pass


class BluetoothHID(RN42):
  """A base bluetooth HID emulator class using RN-42 evaluation kit."""

  # Suppoerted device types
  KEYBOARD = 'KEYBOARD'
  GAMEPAD = 'GAMEPAD'
  MOUSE = 'MOUSE'
  COMBO = 'COMBO'
  JOYSTICK = 'JOYSTICK'

  SEND_DELAY_SECS = 0.2     # Need to sleep for a short while otherwise
                            # the bits may get lost during transmission.

  def __init__(self, device_type, authentication_mode,
               send_delay=SEND_DELAY_SECS):
    """Initialization of BluetoothHID

    Args:
      device_type: the device type for emulation
      authentication_mode: the authentication mode
      send_delay: wait a while after sending data
    """
    super(BluetoothHID, self).__init__()
    self.device_type = device_type
    self.send_delay = send_delay

    # Enter command mode for configuration.
    self.EnterCommandMode()

    # Set HID as the service profile.
    self.SetServiceProfileHID()

    # Set the HID device type.
    self.SetHIDDevice(device_type)

    # Set authentication to the specified mode.
    self.SetAuthenticationMode(authentication_mode)

    # Set RN-42 to work as a slave.
    self.SetSlaveMode()

    # Enable the connection status message so that we could get the message
    # of connection/disconnection status.
    self.EnableConnectionStatusMessage()

    # Reboot so that the configurations above take in effect.
    self.Reboot()

    # Should enter command mode again after reboot.
    self.EnterCommandMode()

    logging.info('A HID "%s" device is created successfully.', device_type)

  def __del__(self):
    self.Close()

  def SetHIDDevice(self, device_type):
    """Set HID device to the specified device type.

    Args:
      device_type: the HID device type to emulate
    """
    if device_type == self.KEYBOARD:
      self.SetHIDKeyboard()
    elif device_type == self.GAMEPAD:
      self.SetHIDGamepad()
    elif device_type == self.MOUSE:
      self.SetHIDMouse()
    elif device_type == self.COMBO:
      self.SetHIDCombo()
    elif device_type == self.JOYSTICK:
      self.SetHIDJoystick()

  def Send(self, data):
    """Send HID reports to the remote host.

    Args:
      data: the data to send
    """
    raise NotImplementedError('An HID subclass must override this method')


class BluetoothHIDKeyboard(BluetoothHID):
  """A bluetooth HID keyboard emulator class."""

  def __init__(self, authentication_mode):
    """Initialization of BluetoothHIDKeyboard

    Args:
      authentication_mode: the authentication mode
    """
    super(BluetoothHIDKeyboard, self).__init__(BluetoothHID.KEYBOARD,
                                               authentication_mode)

  def Send(self, data):
    """Send data to the remote host.

    Args:
      data: data to send to the remote host
            data could be either a string of printable ASCII characters or
            a special key combination.
    """
    # TODO(josephsih): should have a method to check the connection status.
    # Currently, once RN-42 is connected to a remote host, all characters
    # except chr(0) transmitted through the serial port are interpreted
    # as characters to send to the remote host.
    # TODO(josephsih): Will support special keys and modifier keys soon.
    # Currently, only printable ASCII characters are supported.
    logging.debug('HID device sending %r...', data)
    self.SerialSendReceive(data, msg='BluetoothHID.Send')
    time.sleep(self.send_delay)

  def SendKeyCombination(self, modifiers=None, keys=None):
    """Send special key combinations to the remote host.

    Args:
      modifiers: a list of modifiers
      keys: a list of scan codes of keys
    """
    press_codes = self.PressShorthandCodes(modifiers=modifiers, keys=keys)
    release_codes = self.ReleaseShorthandCodes()
    if press_codes and release_codes:
      self.Send(press_codes)
      self.Send(release_codes)
    else:
      logging.warn('modifers: %s and keys: %s are not valid', modifiers, keys)
      return None


def _UsageAndExit():
  """The usage of this module."""
  print 'Usage: python bluetooth_hid.py remote_address text_to_send'
  print 'Example:'
  print '       python bluetooth_hid.py 6C:29:95:1A:D4:6F "echo hello world"'
  exit(1)


def DemoBluetoothHIDKeyboard(remote_address, chars):
  """A simple demo of acting as a HID keyboard.

  This simple demo works only after the HID device has already paired
  with the remote device such that a link key has been exchanged. Then
  the HID device could connect directly to the remote host without
  pin code and sends the message.

  A full flow would be letting a remote host pair with the HID device
  with the pin code of the HID device. Thereafter, either the host or
  the HID device could request to connect. This is out of the scope of
  this simple demo.

  Args:
    remote_address: the bluetooth address of the target remote device
    chars: the characters to send
  """
  print 'Creating an emulated bluetooth keyboard...'
  keyboard = BluetoothHIDKeyboard(BluetoothHID.PIN_CODE_MODE)

  print 'Connecting to the remote address %s...' % remote_address
  try:
    if keyboard.ConnectToRemoteAddress(remote_address):
      # Send printable ASCII strings a few times.
      for i in range(1, 4):
        print 'Sending "%s" for the %dth time...' % (chars, i)
        keyboard.Send(chars + ' ' + str(i))

      # Demo special key combinations below.
      print 'Create a new chrome tab.'
      keyboard.SendKeyCombination(modifiers=[RN42.LEFT_CTRL],
                                  keys=[RN42.SCAN_T])

      print 'Navigate to Google page.'
      keyboard.Send('www.google.com')
      time.sleep(1)

      print 'Search hello world.'
      keyboard.Send('hello world')
      time.sleep(1)

      print 'Navigate back to the previous page.'
      keyboard.SendKeyCombination(keys=[RN42.SCAN_F1])
      time.sleep(1)

      print 'Switch to the previous tab.'
      keyboard.SendKeyCombination(modifiers=[RN42.LEFT_CTRL, RN42.LEFT_SHIFT],
                                  keys=[RN42.SCAN_TAB])
    else:
      print 'Something is wrong. Not able to connect to the remote address.'
      print 'Have you already paired RN-42 with the remote host?'
  finally:
    print 'Disconnecting...'
    keyboard.Disconnect()

  print 'Closing the keyboard...'
  keyboard.Close()


if __name__ == '__main__':
  if len(sys.argv) != 3:
    _UsageAndExit()

  remote_host_address = sys.argv[1]
  chars_to_send = sys.argv[2]

  if len(remote_host_address.replace(':', '')) != 12:
    print '"%s" is not a valid bluetooth address.' % remote_host_address
    _UsageAndExit()

  DemoBluetoothHIDKeyboard(remote_host_address, chars_to_send)
