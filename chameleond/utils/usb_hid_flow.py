# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The control interface of USB HID flow module driver."""

import logging
import os
import select


class USBHIDFlowError(Exception):
  """Exception raised when any error occurs in USBHIDFlow."""
  pass


class USBHIDFlow(object):
  """The control interface of USB HID flow module driver."""

  _HID_FILE_PATTERN = '/dev/hidg%d'
  _POLL_TIMEOUT_MSECS = 50

  # Supported event types of Send() function
  _SUPPORTED_EVENTS = {'report': 'SendReport'}

  def __init__(self, port_id, connector_type, hid_id, report_length, bounce,
               usb_ctrl):
    """Initializes a USBHIDFlow object.

    Args:
      port_id: Port id that represents the type of port used.
      connector_type: String to be obtained by GetConnectorType().
      hid_id: Index of hid file. (regard to hid kernel module setting)
      report_length: The number of bytes for reports.
      bounce: Whether to send a zero string after each report.
      usb_ctrl: A USBController object that USBHIDFlow keep reference to.
    """
    self._port_id = port_id
    self._connector_type = connector_type
    self._hid_file = self._HID_FILE_PATTERN % hid_id
    self._report_length = report_length
    self._bounce = bounce
    self._usb_ctrl = usb_ctrl

  def Initialize(self):
    """Enables USB port controller.

    Enables USB port device mode controller so USB host on the other side will
    not get confused when trying to enumerate this USB device.
    """
    self._usb_ctrl.EnableUSBOTGDriver()
    logging.info('Initialized USB HID flow #%d.', self._port_id)

  def Select(self):
    """Selects the USB HID flow."""
    logging.info('Selected USB HID flow #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return self._connector_type

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    # TODO
    logging.warning(
        'IsPhysicalPlugged on USBHIDFlow is not implemented.'
        ' Always returns True')
    return True

  def IsPlugged(self):
    """Returns a Boolean value reflecting the status of USB hid gadget driver.

    Returns:
      True if USB hid gadget driver is enabled. False otherwise.
    """
    return self._usb_ctrl.DriverIsEnabled()

  def Plug(self):
    """Emulates plug for USB hid gadget by enabling hid gadget driver."""
    self._usb_ctrl.EnableDriver()

  def Unplug(self):
    """Emulates unplug for USB hid gadget by disabling hid gadget driver."""
    self._usb_ctrl.DisableDriver()

  def DoFSM(self):
    """Do nothing for USBHIDFlow.

    fpga_tio calls DoFSM after a flow is selected.
    """
    pass

  @property
  def supported_events(self):
    """Gets the list of supported event types."""
    return self._SUPPORTED_EVENTS.keys()

  def Send(self, event_type, *args, **kwargs):
    """A general function to send events with event_type and arguments.

    Args:
      event_type: Supported event type in keys of self._SUPPORTED_EVENTS

    Returns:
      Returns as event function if applicable.

    Raises:
      USBHIDFlowError if input event type is not supported.
    """
    args_string = ''
    for value in args:
      args_string += '{0}, '.format(value)
    for name, value in kwargs.items():
      args_string += '{0}={1}, '.format(name, value)
    logging.info('HID flow #%d Event: Type=%s, Args=(%s)',
                 self._port_id, event_type, args_string)

    if event_type.lower() in self.supported_events:
      return getattr(
          self, self._SUPPORTED_EVENTS[event_type.lower()])(*args, **kwargs)
    else:
      raise USBHIDFlowError('Unsupported event_type "%s"!! Supported: %s' %
                            (event_type, str(self.supported_events)))

  def _IsHIDFileExisted(self):
    """Checks if hid file is existed.

    Returns:
      Boolean.
    """
    return os.path.exists(self._hid_file)

  def SendReport(self, report_bytes):
    """Sends report bytes to hid module and receives feedback if applicable.

    Args:
      report_bytes: A list of reporting bytes.

    Returns:
      One byte feedback if applicable. None for no feedback.

    Raises:
      USBHIDFlowError if hid file dose not exist, or report byte length is not
        correct.
    """
    if not self._IsHIDFileExisted():
      raise USBHIDFlowError('HID device %s not existed!!' % self._hid_file)
    if len(report_bytes) != self._report_length:
      raise USBHIDFlowError('Wrong report length!! expected length = %d' %
                            self._report_length)

    # Send output bytes to hid module.
    logging.info(
        'HID flow #%d Send Report %s', self._port_id, str(report_bytes))
    with open(self._hid_file, 'r+') as f:
      report_string = ''.join([chr(c) for c in report_bytes])
      f.write(report_string)
      if self._bounce:
        f.write('\x00' * self._report_length)

    # Poll for byte input if there is feedback from hid module.
    # TODO(johnylin): Poll will always fail if hid_file just opened once. Need
    #   to find the root cause.
    with open(self._hid_file, 'r+') as f:
      p = select.poll()
      p.register(f.fileno(), select.POLLIN)
      events = p.poll(self._POLL_TIMEOUT_MSECS)
      if len(events):
        read_byte = ord(f.read(1))  # read one byte
        logging.info('HID flow #%d Feedback 0x%x', self._port_id, read_byte)
        return read_byte


class KeyboardUSBHIDFlow(USBHIDFlow):
  """Subclass of USBHIDFlow that emulates keyboard inputs."""

  _KEYBOARD_HID_ID = 0
  _KEYBOARD_REPORT_LENGTH = 8
  _KEYBOARD_BOUNCE = True

  # Mapping table for bitmask of mod keys
  _KEYBOARD_MODS = {'CTRL': 0x01,
                    'SHIFT': 0x02,
                    'ALT': 0x04}
  # Mapping table for special keys
  _KEYBOARD_SPECIAL_KEYS = {'<enter>': 0x28,
                            '<esc>': 0x29,
                            '<backspace>': 0x2a,
                            '<tab>': 0x2b,
                            '<spacebar>': 0x2c,
                            '<caps-lock>': 0x39,
                            '<f1>': 0x3a,
                            '<f2>': 0x3b,
                            '<f3>': 0x3c,
                            '<f4>': 0x3d,
                            '<f5>': 0x3e,
                            '<f6>': 0x3f,
                            '<f7>': 0x40,
                            '<f8>': 0x41,
                            '<f9>': 0x42,
                            '<f10>': 0x43,
                            '<f11>': 0x44,
                            '<f12>': 0x45,
                            '<insert>': 0x49,
                            '<home>': 0x4a,
                            '<pageup>': 0x4b,
                            '<del>': 0x4c,
                            '<end>': 0x4d,
                            '<pagedown>': 0x4e,
                            '<right>': 0x4f,
                            '<left>': 0x50,
                            '<down>': 0x51,
                            '<up>': 0x52,
                            '<num-lock>': 0x53}
  # Mapping table for symbols to (key_event_hex, is_shift_pressed)
  _KEYBOARD_SYMBOLS = {'!': (0x1e, True),
                       '@': (0x1f, True),
                       '#': (0x20, True),
                       '$': (0x21, True),
                       '%': (0x22, True),
                       '^': (0x23, True),
                       '&': (0x24, True),
                       '*': (0x25, True),
                       '(': (0x26, True),
                       ')': (0x27, True),
                       ' ': (0x2c, False),
                       '-': (0x2d, False),
                       '_': (0x2d, True),
                       '=': (0x2e, False),
                       '+': (0x2e, True),
                       '[': (0x2f, False),
                       '{': (0x2f, True),
                       ']': (0x30, False),
                       '}': (0x30, True),
                       '\\': (0x31, False),
                       '|': (0x31, True),
                       ';': (0x33, False),
                       ':': (0x33, True),
                       '\'': (0x34, False),
                       '\"': (0x34, True),
                       '`': (0x35, False),
                       '~': (0x35, True),
                       ',': (0x36, False),
                       '<': (0x36, True),
                       '.': (0x37, False),
                       '>': (0x37, True),
                       '/': (0x38, False),
                       '?': (0x38, True)}

  # Supported event types of Send() function
  _SUPPORTED_EVENTS = {'report': 'SendReport',
                       'key': 'SendKey',
                       'keys': 'SendKeys'}

  def __init__(self, port_id, usb_ctrl):
    """Initializes a KeyboardUSBHIDFlow object.

    Args:
      port_id: Port id that represents the type of port used.
      usb_ctrl: A USBController object that USBHIDFlow keep reference to.
    """
    super(KeyboardUSBHIDFlow, self).__init__(port_id, 'USBKeyboard',
                                             self._KEYBOARD_HID_ID,
                                             self._KEYBOARD_REPORT_LENGTH,
                                             self._KEYBOARD_BOUNCE,
                                             usb_ctrl)

  def SendKey(self, key, is_ctrl_pressed=False, is_shift_pressed=False,
              is_alt_pressed=False):
    """Sends a key pressed event.

    For key values such as all uppercase (ex. 'A', 'B') and some symbols (ex.
    '!', '<'), which need to be typed with shift key pressing in keyboard, this
    function will set is_shift_pressed to True automatically while sending.

    Args:
      key: The value could be a character (ex. 'a', 'B', '!'), or a special
          function key defined in self._KEYBOARD_SPECIAL_KEYS (ex. '<tab>',
          '<enter>').
      is_ctrl_pressed: Whether to send event with ctrl key pressing.
      is_shift_pressed: Whether to send event with shift key pressing.
      is_alt_pressed: Whether to send event with alt key pressing.

    Returns:
      Same as the retrun of self.SendReport() if applicable.

    Raises:
      USBHIDFlowError if it fails to parse the key value.
    """
    try:
      if not key:
        key_byte = 0x00
      elif key in self._KEYBOARD_SPECIAL_KEYS.keys():
        key_byte = self._KEYBOARD_SPECIAL_KEYS[key]
      elif key in self._KEYBOARD_SYMBOLS.keys():
        key_byte = self._KEYBOARD_SYMBOLS[key][0]
        is_shift_pressed = self._KEYBOARD_SYMBOLS[key][1]
      elif 'a' <= key <= 'z':
        key_byte = ord(key) - 0x5d
      elif 'A' <= key <= 'Z':
        key_byte = ord(key) - 0x3d
        is_shift_pressed = True
      elif '0' <= key <= '9':
        key_byte = 0x27 if key == '0' else (ord(key) - 0x13)
      else:
        raise USBHIDFlowError('Unsupported key value = %s!!' % key)
    except Exception as e:
      raise USBHIDFlowError('Error while parsing key value = %s: %s' % (key, e))

    mod_byte = 0x00
    if is_ctrl_pressed:
      mod_byte |= self._KEYBOARD_MODS['CTRL']
    if is_shift_pressed:
      mod_byte |= self._KEYBOARD_MODS['SHIFT']
    if is_alt_pressed:
      mod_byte |= self._KEYBOARD_MODS['ALT']

    return self.SendReport([
        mod_byte, 0x00, key_byte, 0x00, 0x00, 0x00, 0x00, 0x00])

  def SendKeys(self, key_list, press_enter_when_finished=False):
    """Sends a list of key values.

    Args:
      key_list: The value could be a string (ex. 'Hello World!'), or a literal
          list of keys if you want to contain special keys (ex. ['<backspace>',
          '1', '2', '<enter>']).
      press_enter_when_finished: If True, this function will send a enter key
          after sending the whole key_list.
    """
    for key in key_list:
      self.SendKey(key)
    if press_enter_when_finished:
      self.SendKey('<enter>')


class TouchUSBHIDFlow(USBHIDFlow):
  """Subclass of USBHIDFlow that emulates touch-screen inputs."""

  _TOUCH_HID_ID = 1
  _TOUCH_REPORT_LENGTH = 5
  _TOUCH_BOUNCE = False

  _TOUCH_OFF = 0x02
  _TOUCH_ON = 0x03
  # TODO(johnylin): implement attribute of device display resolution, and then
  #   input pixel-based points instead.
  _TOUCH_BOUNDARY = [0, 10000]

  # Supported event types of Send() function
  _SUPPORTED_EVENTS = {'report': 'SendReport',
                       'trace': 'SendTrace',
                       'tap': 'SendTap'}

  def __init__(self, port_id, usb_ctrl):
    """Initializes a TouchUSBHIDFlow object.

    Args:
      port_id: Port id that represents the type of port used.
      usb_ctrl: A USBController object that USBHIDFlow keep reference to.
    """
    super(TouchUSBHIDFlow, self).__init__(port_id, 'USBTouch',
                                          self._TOUCH_HID_ID,
                                          self._TOUCH_REPORT_LENGTH,
                                          self._TOUCH_BOUNCE,
                                          usb_ctrl)

  def _ConvertPointToChars(self, point):
    """Converts input point coordinate into byte format.

    Args:
      point: A tuple of point (x, y) coordinate.

    Returns:
      A 4-byte long list for presenting input point coordinate.

    Raises:
      USBHIDFlowError if point location is out of boundary.
    """
    chars = []
    for axis in point:
      if not self._TOUCH_BOUNDARY[0] <= axis <= self._TOUCH_BOUNDARY[1]:
        raise USBHIDFlowError('Point out of boundary %s: %s' % (
            str(self._TOUCH_BOUNDARY), str(point)))
      chars += [axis % 256, axis / 256]
    return chars

  def SendTrace(self, track_points):
    """Sends a trace event within a list of trajectory points.

    Args:
      track_points: A list of tuples of track points (x, y) coordinate.

    Raises:
      USBHIDFlowError if there are too few track points.
    """
    if len(track_points) < 2:
      raise USBHIDFlowError('At least 2 points needed in track point list!!')

    self.SendReport(
        [self._TOUCH_OFF] + self._ConvertPointToChars(track_points[0]))
    for point in track_points[1:]:
      self.SendReport([self._TOUCH_ON] + self._ConvertPointToChars(point))
    self.SendReport(
        [self._TOUCH_OFF] + self._ConvertPointToChars(track_points[-1]))

  def SendTap(self, point):
    """Sends a tap event on input point.

    Args:
      point: A tuple of point (x, y) coordinate.
    """
    point_in_chars = self._ConvertPointToChars(point)
    self.SendReport([self._TOUCH_OFF] + point_in_chars)
    self.SendReport([self._TOUCH_ON] + point_in_chars)
    self.SendReport([self._TOUCH_OFF] + point_in_chars)
