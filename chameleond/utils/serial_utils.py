# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities for serial port communication.

For some test cases, DUT needs to communicates with fixuture via USB-Serial
dungle. We provides FindTtyByDriver() to help finding the right
/dev/tty* path for the given driver; and OpenSerial() to open a serial port.

Provides an interface to communicate w/ a serial device: SerialDevice. See
class comment for details.
"""

from __future__ import print_function
import glob
import logging
import os
import re
# site-packages: dev-python/pyserial
import serial
import time

def OpenSerial(**kwargs):
  """Tries to open a serial port.

  Args:
    kwargs: a dict of parameters for a serial connection. Should contain
            'port'. For other parameters, like 'baudrate', 'bytesize', 'parity',
            'stopbits' and 'timeout', please refer pySerial documentation.

  Returns:
    serial object if successful.

  Raises:
    ValueError if kwargs is invalid; otherwise, serial.SerialException.
  """
  port = kwargs.get('port')
  if not port:
    raise ValueError('Missing parameter "port".')
  ser = serial.Serial(**kwargs)
  if not ser.isOpen():
    raise serial.SerialException('Failed to open serial: %r' % port)
  return ser


def FindTtyByDriver(driver_name, interface_protocol=None, multiple_ports=False):
  """Finds the tty terminal matched to driver_name and interface protocol.

  Checks the interface protocol if specified. In some situations where there
  may exist multiple ports with the same driver, use the interface_protocol
  to distinguish between them. An example is Arduino DUE board with a
  Programming Port and a Native USB Port.

  In some cases there may be multiple ports with the same driver and with the
  same interface_protocol, set multiple_ports to True and all matched paths
  found will be returned in a list.

  Args:
    driver_name: driver name for the target TTY device.
    interface_protocol: the interface protocol for the target TTY device.
    multiple_ports: determines whether it returns all matched paths by list, or
        just return the first found one.

  Returns:
    If multiple_ports is True, return /dev/tty path if driver_name is matched;
        None if not found.
    If multiple_ports is False, return a list of all matched /dev/tty path; An
        empty list if not found.
  """
  matched_candidates = []
  for candidate in glob.glob('/dev/tty*'):
    device_path = '/sys/class/tty/%s/device' % os.path.basename(candidate)
    driver_path = os.path.realpath(os.path.join(device_path, 'driver'))

    # Check if driver_name exist at the tail of driver_path.
    if re.search(driver_name + '$', driver_path):
      if (interface_protocol is None or
          interface_protocol == DeviceInterfaceProtocol(device_path)):
        if multiple_ports:
          matched_candidates.append(candidate)
        else:
          return candidate
  if multiple_ports:
    return matched_candidates
  else:
    return None


def FindTtyByPortIndex(port_index, driver_name=None):
  """Finds serial port path tty* with given port index.

  Port index is fixed as the layout of physical ports.
  Example: if serial path is ttyUSB0 for port_index = 1-1, the system path
           /sys/class/tty/ttyUSB0/device will be linked to
           /sys/devices/pci0000..../..../usb1/1-1/...

  Args:
    port_index: String for serial connection port index.
    driver_name: String for serial connection driver.

  Returns:
    matched /dev/tty path. Return None if no port has been detected.
  """
  for candidate in glob.glob('/dev/tty*'):
    device_path = '/sys/class/tty/%s/device' % os.path.basename(candidate)
    driver_path = os.path.realpath(os.path.join(device_path, 'driver'))

    # If driver_name is given, check if driver_name exists at the tail of
    # driver_path.
    if driver_name and not driver_path.endswith(driver_name):
      continue

    device_path = os.path.realpath(device_path)
    # Check if port_index exists in device_path.
    if '/%s/' % port_index in device_path:
      logging.info('Find serial path : %s', candidate)
      return candidate
  return None


def FindTtyByUsbVidPid(usb_vid, usb_pid, driver_name=None):
  """Finds the tty for the usb device with given vid, pid, and driver.

  This is more useful than port index or driver alone, but only works if your
  devices have different VID/PID/(optionally driver) values.
  Otherwise, it won't help, and you'll have to probe something else.

  Args:
    usb_vid: The USB VID (Vendor ID) as a hexadecimal string
    usb_pid: The USB PID (Product ID) as a hexadecimal string
    driver_name: String for serial connection driver.

  Returns:
    matched /dev/tty path. Return None if no port has been detected.
  """
  try:
    import pyudev
  except ImportError:
    logging.error("Failed to import pyudev")
    return None

  port = None
  context = pyudev.Context()
  for device in context.list_devices(subsystem='tty'):
    if 'ID_VENDOR' not in device:
      continue
    if usb_vid is not None:
      if device['ID_VENDOR_ID'] != usb_vid:
        continue
    if usb_pid is not None:
      if device['ID_MODEL_ID'] != usb_pid:
        continue
    if driver_name is not None:
      if device['ID_USB_DRIVER'] != driver_name:
        continue
    port = device.device_node
    break

  logging.info('Found USB serial tty: %s', port)
  return port


def FindTtyListByUsbVidPid(usb_vid, usb_pid):
  """Returns list of TTYs matching vid/pid and driver (if provided).

  There may be more than one attached serial peripheral with matching
  {vid,pid,driver}. To distinguish between peripherals in this case,
  give caller an opportunity to select specific port to connect on.

  Args:
    usb_vid: The USB VID (Vendor ID) as a hexadecimal string
    usb_pid: The USB PID (Product ID) as a hexadecimal string
    driver_name: String for serial connection driver.

  Returns:
  List of serial devices with additional attributes
  """
  serial_devices = []

  # TODO(yuhsuan): There is no pyudev package in chameleon and pip is broken
  # now. Add a handler here to avoid chameleon crash until we get new image of
  # chameleon. (crbug.com/951703)
  try:
    import pyudev
  except ImportError:
    logging.error("Failed to import pyudev")
    return serial_devices

  context = pyudev.Context()
  for device in context.list_devices(subsystem='tty'):
    if 'ID_VENDOR' not in device:
      continue
    if usb_vid is not None:
      if device['ID_VENDOR_ID'] != usb_vid:
        continue
    if usb_pid is not None:
      if device['ID_MODEL_ID'] != usb_pid:
        continue
    if 'ID_SERIAL_SHORT' not in device:
      continue
      # (vid,pid) match. Append device to list for caller to validate
      # serial number.
    serial_devices.append({'vid'    : device['ID_VENDOR_ID'],
                           'pid'    : device['ID_MODEL_ID'],
                           'serial' : device['ID_SERIAL_SHORT'],
                           'port'   : device.device_node})
  return serial_devices


def ReadSysfsFile(path):
  """Extracts the contents of the given sysfs file.

  Intended for use on the one-line files in sysfs that contain small amounts of
  data we want to know.

  Args:
    path: The path to the sysfs file to read.

  Returns:
    The file if found else ''
  """
  try:
    with open(path) as f:
      return f.read().strip()
  except IOError:
    return ''


def DeviceInterfaceProtocol(device_path):
  """Extracts the interface protocol of the specified device path.

  Args:
    device_path: The tty device path in the sysfs.

  Returns:
    The interface protocol if found else ''
  """
  interface_protocol_path = os.path.join(device_path, 'bInterfaceProtocol')
  try:
    with open(interface_protocol_path) as f:
      return f.read().strip()
  except IOError:
    return ''


class SerialDevice(object):
  """Interface to communicate with a serial device.

  Instead of giving a fixed port, it can look up port by driver name.

  It has several handy methods, like SendRecv() and SendExpectRecv(),
  which support fail retry.

  Property:
    log: True to enable logging.

  Usage:
    fixture = SerialDevice()
    fixture.Connect(driver='pl2303')

    # Send 'P' for ping fixture and expect an 'OK' response.
    # Allow to retry twice.
    fixture.SendExpectReceive('P', 'OK', retry=2)

    # Send 'FID' for getting fixture ID. Return received result. No retry.
    fixture_id = fixture.SendRecv('FID')
  """

  def __init__(self, send_receive_interval_secs=0.2, retry_interval_secs=0.5,
               log=False):
    """Constructor.

    Sets intervals between send/receive and between retries.
    Also, setting log to True to emit actions to logging.info.

    Args:
      send_receive_interval_secs: interval (seconds) between send-receive.
      retry_interval_secs: interval (seconds) between retrying command.
      log: True to enable logging.
    """
    self._serial = None
    self.port = ''
    self.send_receive_interval_secs = send_receive_interval_secs
    self.retry_interval_secs = retry_interval_secs
    self.log = log

  def __del__(self):
    self.Disconnect()

  def Connect(self, driver=None, port=None, usb_vid=None, usb_pid=None,
              known_device_set=None,
              baudrate=9600, bytesize=serial.EIGHTBITS,
              parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
              timeout=0.5, writeTimeout=0.5):
    """Opens a serial connection by port, by device driver name, or by VID/PID.

    All three of driver, usb_vid, and usb_pid must be specified to lookup by
    VID/PID.

    Args:
      driver: driver name of the target serial connection. used to look up port
          if port is not specified.
      usb_vid: USB VID of the target serial connection. used to look up port
          if port is not specified.
      usb_pid: USB PID of the target serial connection. used to look up port
          if port is not specified.
      port: See serial.Serial().
      baudrate: See serial.Serial().
      bytesize: See serial.Serial().
      parity: See serial.Serial().
      stopbits: See serial.Serial().
      timeout: See serial.Serial().
      writeTimeout: See serial.Serial().

    Raises:
      SerialException on errors.
    """
    if driver and not port:
      if usb_vid and usb_pid:
        if known_device_set:
          devices = FindTtyListByUsbVidPid(usb_vid, usb_pid)
          for device in devices:
            if device['serial'] in known_device_set:
              port = device['port']
              break
        else:
          port = FindTtyByUsbVidPid(usb_vid, usb_pid, driver_name=driver)
      else:
        port = FindTtyByDriver(driver)

    if not port:
      raise serial.SerialException(
          'Serial device with driver %r not found' % driver)

    self.port = port

    self._serial = OpenSerial(
        port=port, baudrate=baudrate, bytesize=bytesize, parity=parity,
        stopbits=stopbits, timeout=timeout, writeTimeout=writeTimeout)

    if self.log:
      logging.info('Serial port %r opened', port)

  def Disconnect(self):
    """Closes the connection if it exists."""
    if self._serial:
      self._serial.close()

  def SetTimeout(self, read_timeout, write_timeout):
    """Overrides read/write timeout.

    Args:
      read_timeout: read timeout.
      write_timeout: write timeout.
    """
    self._serial.setTimeout(read_timeout)
    self._serial.setWriteTimeout(write_timeout)

  def GetTimeout(self):
    """Returns (read timeout, write timeout)."""
    return (self._serial.getTimeout(), self._serial.getWriteTimeout())

  def Send(self, command, flush=True):
    """Sends a command.

    It blocks at most write_timeout seconds.

    Args:
      command: command to send.
      flush: call flush() after write(). Default True.

    Raises:
      SerialTimeoutException if it is timeout and fails to send the command.
      SerialException if it is disconnected during sending.
    """
    try:
      start_time = time.time()
      self._serial.write(command)
      if flush:
        self._serial.flush()
      if self.log:
        duration = time.time() - start_time
        logging.info('Successfully sent %r. Took %.3f seconds', command,
                     duration)
    except serial.SerialTimeoutException:
      error_message = 'Send %r timeout after %.2f seconds' % (
          command, self._serial.getWriteTimeout())
      if self.log:
        logging.warning(error_message)
      raise serial.SerialTimeoutException(error_message)
    except serial.SerialException:
      raise serial.SerialException('Serial disconnected')

  def Receive(self, size=1):
    """Receives N bytes.

    It blocks at most timeout seconds.

    Args:
      size: number of bytes to receive. 0 means receiving what already in the
          input buffer.

    Returns:
      Received N bytes.

    Raises:
      SerialTimeoutException if it fails to receive N bytes.
    """
    start_time = time.time()
    if size == 0:
      size = self._serial.inWaiting()
    response = self._serial.read(size)
    if len(response) == size:
      if self.log:
        duration = time.time() - start_time
        logging.info('Successfully received %r. Took %.3f seconds', response,
                     duration)
      return response
    else:
      error_message = 'Receive %d bytes timeout after %.2f seconds' % (
          size, self._serial.getTimeout())
      if self.log:
        logging.warning(error_message)
      raise serial.SerialTimeoutException(error_message)

  def ReceiveLine(self):
    """Receives one line.

    It blocks at most timeout seconds.

    Returns:
      Received data of one line.
    """
    return self._serial.readline()

  def FlushBuffer(self):
    """Flushes input/output buffer."""
    self._serial.flushInput()
    self._serial.flushOutput()

  def SendReceive(self, command, size=1, retry=0, interval_secs=None,
                  suppress_log=False):
    """Sends a command and returns a N bytes response.

    Args:
      command: command to send
      size: number of bytes to receive. 0 means receiving what already in the
          input buffer.
      retry: number of retry.
      interval_secs: #seconds to wait between send and receive. If specified,
          overrides self.send_receive_interval_secs.
      suppress_log: True to disable log regardless of self.log value.

    Returns:
      Received N bytes.

    Raises:
      SerialTimeoutException if it fails to receive N bytes.
    """
    for nth_run in range(retry + 1):
      self.FlushBuffer()
      try:
        self.Send(command)
        if interval_secs is None:
          time.sleep(self.send_receive_interval_secs)
        else:
          time.sleep(interval_secs)
        response = self.Receive(size)
        if not suppress_log and self.log:
          logging.info('Successfully sent %r and received %r', command,
                       response)
        return response
      except serial.SerialTimeoutException:
        if nth_run < retry:
          time.sleep(self.retry_interval_secs)

    error_message = 'Timeout receiving %d bytes for command %r' % (size,
                                                                   command)
    if not suppress_log and self.log:
      logging.warning(error_message)
    raise serial.SerialTimeoutException(error_message)

  def SendExpectReceive(self, command, expect_response, retry=0,
                        interval_secs=None):
    """Sends a command and expects to receive a response.

    Args:
      command: command to send
      expect_response: expected response received
      retry: number of retry.
      interval_secs: #seconds to wait between send and receive. If specified,
          overrides self.send_receive_interval_secs.

    Returns:
      True if command is sent and expected response received.
    """
    try:
      response = self.SendReceive(command, len(expect_response), retry=retry,
                                  interval_secs=interval_secs,
                                  suppress_log=True)
    except serial.SerialTimeoutException:
      if self.log:
        logging.warning('SendReceive timeout for command %r', command)
      return False

    if self.log:
      if response == expect_response:
        logging.info('Successfully sent %r and received expected response %r',
                     command, expect_response)
      else:
        logging.warning('Sent %r but received %r (expected: %r)',
                        command, response, expect_response)
    return response == expect_response
