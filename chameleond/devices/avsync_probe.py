# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides controls of A/V sync probe."""

import logging
import struct
import time

from chameleond.devices import chameleon_device
from chameleond.utils import serial_utils
from chameleond.utils import system_tools


class AVSyncProbeSerial(object):
  """A client of a serial port device.

   Typical usage example:

   client = AVSyncProbeSerial()
   client.serial.Send(<commands specific to each device>)
   client.serial.Receive(<bytes for receiving>)
   client.serial.ReceiveLine()
  """
  _DRIVER = 'ch341-uart'
  _DEVICE_TYPE = 'AV_SYNC_PROBE'

  _BAUD_RATE = 230400
  _STOP_COMMAND = 'd'
  _DEVICE_INFO_COMMAND = '?'
  _BINARY_TRANSMISSION_COMMAND = 'b'

  _SECONDS_TO_MILLISECONDS = 1000

  # Format of binary packet, written in the fmt string for struct.unpack.
  # Must be kept consistent with the encoding algorithm in the device firmware.
  _PACKET_FORMAT = '<IHHHHH'  # Little endian, uint32, uint16 * 5.

  # Number of bytes in one packet. Must be consistent with _PACKET_FORMAT.
  _PACKET_SIZE = 14

  def __init__(self):
    """Creates an instance of serial device client.

    This constructor checks if an expected type of device is connected.

    Raises:
      IOError: if an expected type of device is not found in the port.
    """
    self.serial = serial_utils.SerialDevice()
    try:
      self.serial.Connect(driver=self._DRIVER, baudrate=self._BAUD_RATE)
    except Exception as e:
      error_msg = 'AVSyncProbe Fail to connect to the serial device: %s' % e
      logging.error(error_msg)
      raise IOError(error_msg)

    if not self._CheckDeviceType():
      raise IOError('Device type did not match.')

  def _CheckDeviceType(self):
    """Check the device type to see if it is correct.

    Args:
      device_type: A string to identify the device type.

    Returns:
      True if the type is correct. False for not correct.
    """
    responses = []
    # Arduino devices didn't interpret several lines of input correctly after
    # it's plugged. This is a hack to avoid problems with such devices by
    # retrying.
    for _ in range(10):
      self.StopCapturing()
      response = self.GetDeviceType()
      responses.append(response)
      x = response.split(' ')
      logging.debug('AVSyncProbe Check Type: %r', x)
      if len(x) >= 2 and x[1] == self._DEVICE_TYPE:
        return True
      time.sleep(0.1)
    logging.error('AVSyncProbe Device type did not match')
    return False

  def GetDeviceType(self):
    """Get the device type name."""
    self.serial.Send(self._DEVICE_INFO_COMMAND)
    return self.serial.ReceiveLine()

  def _Decode(self, packet):
    values = struct.unpack(self._PACKET_FORMAT, packet)
    checksum = ((values[0] & 0xffff) ^ values[1] ^ values[2] ^ values[3] ^
                values[4])
    if values[-1] != checksum:
      raise IOError('checksum error: ' + str(values))
    # Trim the checksum field.
    return values[: -1]

  def StartCapturing(self, sample_duration_seconds):
    """Start capturing the data from AV Sync Probe device.

    The probe's sampling rate is 1 ms. So we will get about 1000 samples per
    second.

    Args:
      sample_duration_seconds: Specify how many seconds for capturing.

    Returns:
      A list contains the list values of [timestamp, video0, video1, video2,
                                          audio].
    """
    self.StopCapturing()
    self.serial.Send(self._BINARY_TRANSMISSION_COMMAND)
    responses = []

    # The device logs one millisecond of data per line.
    num_samples = int(sample_duration_seconds * self._SECONDS_TO_MILLISECONDS)
    for _ in xrange(num_samples):
      packet = self.serial.Receive(self._PACKET_SIZE)
      values = self._Decode(packet)
      responses.append(values)

    self.StopCapturing()
    return responses

  def StopCapturing(self):
    """Stop capturing data from AV Sync Probe device."""
    self.serial.Send(self._STOP_COMMAND)
    # Wait until the command takes effect.
    time.sleep(0.002)


class AVSyncProbe(chameleon_device.ChameleonDevice):
  """A client class of the A/V sync probe device."""

  _DEVICE_NAME = 'AVSyncProbe'
  _KERNEL_MODULE = 'ch341'
  _DETECT_RETRY = 3

  def __init__(self, port_id):
    """Initializes a AVSyncProbeFlow object.

    Args:
      port_id: the port id that represents the type of port used.
    """
    super(AVSyncProbe, self).__init__()
    logging.info('AVSyncProbe __init__ #%d.', port_id)
    self._port_id = port_id
    self._av_sync_probe = None
    system_tools.SystemTools.Call('modprobe', self._KERNEL_MODULE)

  def IsDetected(self):
    """Returns if the device can be detected."""
    # We need some time for system to detect the device.
    for i in xrange(self._DETECT_RETRY, 0, -1):
      try:
        self._av_sync_probe = AVSyncProbeSerial()
      except IOError:
        logging.info('AVSyncProbe: Retry detecting device (%d left).', i)
        time.sleep(1)
      else:
        return True
    return False

  def InitDevice(self):
    """Init the real device of chameleon board."""
    # No need to init the device.
    pass

  def Reset(self):
    """Reset chameleon device."""
    self._av_sync_probe.StopCapturing()

  def Capture(self, sample_duration_seconds=10.0):
    """Get the sample results of the probe.

    The probe's sampling rate is 1 ms. So we will get about 1000 samples per
    second.

    Args:
      sample_duration_seconds: Specify how many seconds for sampling.

    Returns:
      A list contains the list values of [timestamp, video0, video1, video2,
                                          audio].
    """
    if not self._av_sync_probe:
      return []

    response = self._av_sync_probe.StartCapturing(sample_duration_seconds)
    return response