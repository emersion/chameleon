# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides emulation of bluetooth HID devices."""

import argparse
import logging
import sys
import time

from bluetooth_rn42 import RN42, RN42Exception


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
    self.authentication_mode = authentication_mode
    self.send_delay = send_delay

  def Init(self):
    """Initialize the emulated device."""
    # Enter command mode for configuration.
    self.EnterCommandMode()

    # Set HID as the service profile.
    self.SetServiceProfileHID()

    # Set the HID device type.
    self.SetHIDDevice(self.device_type)

    # Set authentication to the specified mode.
    self.SetAuthenticationMode(self.authentication_mode)

    # Set RN-42 to work as a slave.
    self.SetSlaveMode()

    # Enable the connection status message so that we could get the message
    # of connection/disconnection status.
    self.EnableConnectionStatusMessage()

    # Reboot so that the configurations above take in effect.
    self.Reboot()

    # Should enter command mode again after reboot.
    self.EnterCommandMode()

    logging.info('A HID "%s" device is created successfully.', self.device_type)

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


class BluetoothHIDMouse(BluetoothHID):
  """A bluetooth HID mouse emulator class."""

  # Definitions of buttons
  BUTTONS_RELEASED = 0x0
  LEFT_BUTTON = 0x01
  RIGHT_BUTTON = 0x02

  def __init__(self, authentication_mode):
    """Initialization of BluetoothHIDMouse

    Args:
      authentication_mode: the authentication mode
    """
    super(BluetoothHIDMouse, self).__init__(BluetoothHID.MOUSE,
                                            authentication_mode)

  def Move(self, delta_x=0, delta_y=0):
    """Move the mouse (delta_x, delta_y) pixels.

    Args:
      delta_x: the pixels to move horizontally
               positive values: moving right; max value = 127.
               negative values: moving left; max value = -127.
      delta_y: the pixels to move vertically
               positive values: moving down; max value = 127.
               negative values: moving up; max value = -127.
    """
    if delta_x or delta_y:
      mouse_codes = self.RawMouseCodes(x_stop=delta_x, y_stop=delta_y)
      self.SerialSendReceive(mouse_codes, msg='BluetoothHIDMouse.Move')
      time.sleep(self.send_delay)

  def _PressButtons(self, buttons):
    """Press down the specified buttons

    Args:
      buttons: the buttons to press
    """
    if buttons:
      mouse_codes = self.RawMouseCodes(buttons=buttons)
      self.SerialSendReceive(mouse_codes, msg='BluetoothHIDMouse._PressButtons')
      time.sleep(self.send_delay)

  def _ReleaseButtons(self):
    """Release buttons."""
    mouse_codes = self.RawMouseCodes(buttons=self.BUTTONS_RELEASED)
    self.SerialSendReceive(mouse_codes, msg='BluetoothHIDMouse._ReleaseButtons')
    time.sleep(self.send_delay)

  def PressLeftButton(self):
    """Press the left button."""
    self._PressButtons(self.LEFT_BUTTON)

  def ReleaseLeftButton(self):
    """Release the left button."""
    self._ReleaseButtons()

  def PressRightButton(self):
    """Press the right button."""
    self._PressButtons(self.RIGHT_BUTTON)

  def ReleaseRightButton(self):
    """Release the right button."""
    self._ReleaseButtons()

  def LeftClick(self):
    """Make a left click."""
    self.PressLeftButton()
    self.ReleaseLeftButton()

  def RightClick(self):
    """Make a right click."""
    self.PressRightButton()
    self.ReleaseRightButton()

  def ClickAndDrag(self, delta_x=0, delta_y=0):
    """Click and drag (delta_x, delta_y)

    Args:
      delta_x: the pixels to move horizontally
      delta_y: the pixels to move vertically
    """
    self.PressLeftButton()
    self.Move(delta_x, delta_y)
    self.ReleaseLeftButton()

  def Scroll(self, wheel):
    """Scroll the wheel.

    Args:
      wheel: the steps to scroll
             The scroll direction depends on which scroll method is employed,
             traditional scrolling or Australian scrolling.
    """
    if wheel:
      mouse_codes = self.RawMouseCodes(wheel=wheel)
      self.SerialSendReceive(mouse_codes, msg='BluetoothHIDMouse.Scroll')
      time.sleep(self.send_delay)


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
  keyboard.Init()

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


def DemoBluetoothHIDMouse(remote_address):
  """A simple demo of acting as a HID mouse.

  Args:
    remote_address: the bluetooth address of the target remote device
  """
  print 'Creating an emulated bluetooth mouse...'
  mouse = BluetoothHIDMouse(BluetoothHID.PIN_CODE_MODE)
  mouse.Init()

  print 'Connecting to the remote address %s...' % remote_address
  try:
    if mouse.ConnectToRemoteAddress(remote_address):
      print 'Click and drag horizontally.'
      mouse.ClickAndDrag(delta_x=100)
      time.sleep(1)

      print 'Make a right click.'
      mouse.RightClick()
      time.sleep(1)

      print 'Move the cursor upper left.'
      mouse.Move(delta_x=-30, delta_y=-40)
      time.sleep(1)

      print 'Make a left click.'
      mouse.LeftClick()
      time.sleep(1)

      print 'Move the cursor left.'
      mouse.Move(delta_x=-100)
      time.sleep(1)

      print 'Move the cursor up.'
      mouse.Move(delta_y=-90)
      time.sleep(1)

      print 'Move the cursor down right.'
      mouse.Move(delta_x=100, delta_y=90)
      time.sleep(1)

      print 'Scroll in one direction.'
      mouse.Scroll(-80)
      time.sleep(1)

      print 'Scroll in the opposite direction.'
      mouse.Scroll(100)
    else:
      print 'Something is wrong. Not able to connect to the remote address.'
  finally:
    print 'Disconnecting...'
    try:
      mouse.Disconnect()
    except RN42Exception:
      # RN-42 may have already disconnected.
      pass

  print 'Closing the mouse...'
  mouse.Close()


def _Parse():
  """Parse the command line options."""
  prog = sys.argv[0]
  example_usage = ('Example:\n' +
                   '  python %s keyboard 00:11:22:33:44:55\n' % prog +
                   '  python %s mouse 00:11:22:33:44:55\n'% prog)
  parser = argparse.ArgumentParser(
      description='Emulate a HID device.\n' + example_usage,
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('device',
                      choices=['keyboard', 'mouse'],
                      help='the device type to emulate')
  parser.add_argument('remote_host_address',
                      help='the remote host address')
  parser.add_argument('-c', '--chars_to_send',
                      default='echo hello world',
                      help='characters to send to the remote host')
  args = parser.parse_args()

  if len(args.remote_host_address.replace(':', '')) != 12:
    print '"%s" is not a valid bluetooth address.' % args.remote_host_address
    exit(1)

  print ('Emulate a %s and connect to remote host at %s' %
         (args.device, args.remote_host_address))
  return args


def Demo():
  """Make demonstrations about how to use the HID emulation classes."""
  args = _Parse()
  device = args.device.lower()
  if device == 'keyboard':
    DemoBluetoothHIDKeyboard(args.remote_host_address, args.chars_to_send)
  elif device == 'mouse':
    DemoBluetoothHIDMouse(args.remote_host_address)
  else:
    args.print_help()


if __name__ == '__main__':
  Demo()
