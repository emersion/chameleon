# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""GPIO monitor module.

Before using, please make sure the correspondent pins are configured as GPIO in
SocKit IO pinmux setting.

For those GPIO which are not configured as interrupt input, we monitor the
change of value periodically instead of using polling system call.
"""

import logging
import os
import threading
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import lcm_queue


class GpioError(Exception):
  """Exception raise when any unexpected behavior happened on GPIO."""
  pass


class Gpio(object):
  """A Class for GPIO monitor and controller."""

  LOW = 0
  HIGH = 1
  EDGE_RISING = 2
  EDGE_FALLING = 3
  EDGE_BOTH = 4

  _POLL_INTERVAL = 0.2

  # Ref: https://www.kernel.org/doc/Documentation/gpio/sysfs.txt
  _GPIO_ROOT = '/sys/class/gpio'
  _EXPORT_FILE = os.path.join(_GPIO_ROOT, 'export')
  _UNEXPORT_FILE = os.path.join(_GPIO_ROOT, 'unexport')
  _GPIO_PIN_PATTERN = os.path.join(_GPIO_ROOT, 'gpio%d')

  def __init__(self, port, trigger=None):
    """Constructs a Gpio object.

    Args:
      port: The GPIO port index.
      trigger: The trigger mode.
    """
    self._port = port
    self._trigger = trigger
    self._state = None
    self._ExportSysfs()

  def __del__(self):
    self._UnexportSysfs()

  def Read(self):
    """Reads the current GPIO value.

    Returns:
      GPIO value. 1 for high and 0 for low.
    """
    with open(self._GetSysfsPath('value'), 'r') as f:
      return int(f.read().strip())

  def Write(self, value):
    """Writes the GPIO value.

    Args:
      value: GPIO value. 1 for high and 0 for low.
    """
    # set gpio direction to output mode
    self._SetDirection('out')
    with open(self._GetSysfsPath('value'), 'w') as f:
      f.write(str(value))

  def Poll(self, timeout=1000):
    """Polls GPIO until an trigger event occurs.

    Args:
      timeout: The timeout in seconds to break the check. Set 0 for forever.
    """
    if self._trigger is None:
      raise GpioError('Cannot use Poll() if trigger mode is not selected...')
    # set gpio direction to input mode
    self._SetDirection('in')
    self._state = self.Read()
    end_time = start_time = time.time()
    while not timeout or end_time - start_time < timeout:
      time.sleep(self._POLL_INTERVAL)
      state = self.Read()
      if state == self._trigger:
        return
      if state != self._state:
        if self._trigger == self.EDGE_BOTH:
          return
        if self._trigger == self.EDGE_RISING and state:
          return
        if self._trigger == self.EDGE_FALLING and not state:
          return
      self._state = state
      end_time = time.time()
    raise GpioError('Timeout occured when polling after %f seconds' % timeout)

  def _GetSysfsPath(self, attribute=None):
    """Gets the path of GPIO sysfs interface.

    Args:
      attribute: Optional read/write attribute.

    Returns:
      The corresponding full sysfs path.
    """
    gpio_path = self._GPIO_PIN_PATTERN % self._port
    if attribute:
      return os.path.join(gpio_path, attribute)
    else:
      return gpio_path

  def _ExportSysfs(self):
    """Exports GPIO sysfs interface."""
    logging.info('export GPIO port %d', self._port)
    if not os.path.exists(self._GetSysfsPath()):
      with open(self._EXPORT_FILE, 'w') as f:
        f.write(str(self._port))

  def _UnexportSysfs(self):
    """Unexports GPIO sysfs interface."""
    logging.info('unexport GPIO port %d', self._port)
    if not os.path.exists(self._GetSysfsPath()):
      return  # GPIO is not exported
    with open(self._UNEXPORT_FILE, 'w') as f:
      f.write(str(self._port))

  def _SetDirection(self, direction):
    """Sets GPIO direction to sysfs.

    Args:
      direction: 'in' for input mode; 'out' for output mode.
    """
    with open(self._GetSysfsPath('direction'), 'w') as f:
      f.write(direction)
    if self._GetDirection() != direction:
      raise GpioError('Cannot configure GPIO port %d as %sput mode...' %
                      (self._port, direction))

  def _GetDirection(self):
    """Gets GPIO direction from sysfs.

    Returns:
      GPIO direction in string, 'in' or 'out'.
    """
    with open(self._GetSysfsPath('direction'), 'r') as f:
      return f.read().strip()


class Key(Gpio):
  """A class of key-press monitor.

  For PollEvent() function, Key object will poll GPIO until the edge-trigger
  event occurs, then push LcmEvent of key-press to input queue to notice display
  UI (the queue consumer).
  """
  def __init__(self, port, key_name, key_index, event_queue, active_low=True):
    """Constructs a Key object.

    Args:
      port: The GPIO port index.
      key_name: The string of key name to put on LcmEvent notice.
      key_index: The key index.
      event_queue: The Queue object to push key-press event.
      active_low: To determine whether GPIO is active_low for key pressing.
    """
    super(Key, self).__init__(
        port, Gpio.EDGE_RISING if active_low else Gpio.EDGE_FALLING)
    self._key_index = key_index
    self._queue = event_queue
    self._event = lcm_queue.LcmEvent('key event %s' % key_name, key_index)
    self._RunDaemon()

  def _RunDaemon(self):
    """Runs the polling daemon of key-press monitoring."""
    thread = threading.Thread(target=self._PollEvent)
    thread.daemon = True
    thread.start()

  def _PollEvent(self):
    """The routine of polling key-press and push event into queue."""
    while True:
      self._event.Clear()
      self.Poll(0)  # wait key press detected from gpio
      self._queue.put(self._event)

      self._event.Wait()  # wait until key event is processed


class Led(Gpio):
  """A class of LED controller."""
  def __init__(self, port):
    """Constructs a Led object.

    Args:
      port: The GPIO port index.
    """
    super(Led, self).__init__(port)

  def On(self):
    """Turns LED on."""
    self.Write(1)

  def Off(self):
    """Turns LED off."""
    self.Write(0)

  def Toggle(self):
    """Toggles LED."""
    self.Write(0 if self.Read() else 1)

  def Blink(self, interval=0.1):
    """Makes LED blink once.

    Args:
      interval: The duration of blinking on, in seconds.
    """
    self.Write(1)
    time.sleep(interval)
    self.Write(0)

  def IsOn(self):
    """Checks whether LED is on.

    Returns:
      True if LED is on; otherwise False.
    """
    return bool(self.Read())
