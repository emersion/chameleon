# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Bluez Service clients (for Bluetooth/BLE HID) - mainly intended for
   standalone verification of functionality.
"""

from __future__ import print_function

import bluez_service_consts
import dbus
import dbus.service
import dbus.mainloop.glib
import logging
import threading
import time

# Refer to comment re 'ImportError' in raspi_bluez_service.py
try:
  from bluetooth import *
except ImportError:
  pass

from bluez_service_consts import *
from dbus.mainloop.glib import DBusGMainLoop


class BluezKeyboardClient(object):
  """Implementation of a client of a BluezKeyboardService.

  This class connects to BluezKeyboardService over DBus
  and sends pre-programmed keystrokes. This is intended for
  standalone testing of the keyboard service implementation.
  """

  KEY_DOWN_TIME = 0.01
  KEY_DELAY = 0.1

  def __init__(self):
    self._report = [
        0xA1, #Input report
        0x01, #Usage report = Keyboard
        # Bitmap for Modifier keys
        # See bluetooth_bluez_service_consts.modmap for mapping
        0x0,
        0x00,   #Vendor reserved
        0x00,   #rest is space for 6 keys
        0x00,
        0x00,
        0x00,
        0x00,
        0x00]
    # mapping of printable characters to keymapkey values
    # for characters that cannot be part of a legal field name.
    self._char_to_key_map = {
        "'": ("KEY_APOSTROPHE", "MOD_NONE"),
        " ": ("KEY_SPACE", "MOD_NONE"),
        ".": ("KEY_PERIOD", "MOD_NONE"),
        "\n": ("KEY_ENTER", "MOD_NONE"),
        "!": ("KEY_1", "MOD_SHIFT_LEFT")
    }
    self._bus = dbus.SystemBus()
    self._service = self._bus.get_object(BLUEZ_KEYBOARD_SERVICE_NAME,
                                         BLUEZ_KEYBOARD_SERVICE_PATH)
    self._iface = dbus.Interface(self._service, BLUEZ_KEYBOARD_SERVICE_NAME)

  def keys_sent_handler(self):
    pass

  def keys_error_handler(self, err):
    logging.error("keys_error_handler: %s", err)

  def send_report(self):
    """sends a single frame of the current key state to the emulator server"""

    modifier = self._report[2]
    self._iface.send_keys(modifier, self._report[4:10],
                          reply_handler=self.keys_sent_handler,
                          error_handler=self.keys_error_handler)

  def send_key_down(self, scancode):
    """sends a key down event to the server"""

    self._report[4] = scancode
    self.send_report()

  def send_key_up(self):
    """sends a key up event to the server"""

    self._report[4] = 0
    self.send_report()

  def register_connected_handler(self):
    self._signal = self._bus.add_signal_receiver(
        path="/org/chromium/autotest/btkbservice",
        handler_function=self.send_string_thread,
        dbus_interface="org.chromium.autotest.btkbservice",
        signal_name="connected")

  def send_string_thread(self):
    threadid = threading.Thread(target=self.send_string,
                                args=("You can't handle the tooth!",))
    threadid.start()

  def send_string(self, string_to_send):
    # Delay to prevent loss of first characters
    # due to keyboard activity starting too quickly
    # after connection.
    time.sleep(1)

    for c in string_to_send:
      self._report[2] = modmap['MOD_NONE']
      if c in self._char_to_key_map:
        keymapkey = self._char_to_key_map[c][0]
        self._report[2] = modmap[self._char_to_key_map[c][1]]
      else:
        # Set SHIFT key if uppercase
        if c.upper() == c:
          self._report[2] = modmap['MOD_SHIFT_LEFT']
        keymapkey = "KEY_"+c.upper()

      scancode = keymap[keymapkey]
      self.send_key_down(scancode)
      time.sleep(self.KEY_DOWN_TIME)
      self.send_key_up()
      time.sleep(self.KEY_DELAY)
