# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for FPGA customized platform."""

import array
import re
import subprocess
import tempfile
import time
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from interface import ChameleondInterface


class FpgaDriverError(Exception):
    """Exception raised when any error on FPGA driver."""
    pass


class FpgaDriver(ChameleondInterface):
  """Chameleond Driver for FPGA customized platform."""

  _HDMI_ID = 1

  _GPIO_MEM_ADDRESS = 0xff2100d0
  _FRAME_WIDTH_ADDRESS = 0xff210100
  _FRAME_HEIGHT_ADDRESS = 0xff210104

  _GPIO_EEPROM_WP_N_MASK = 0x1
  _GPIO_HPD_MASK = 0x2

  _MAIN_I2C_BUS = 0
  _EEPROM_I2C_SLAVE = 0x50

  def __init__(self, *args, **kwargs):
    super(FpgaDriver, self).__init__(*args, **kwargs)
    self._i2cdump_pattern = re.compile(r'[0-9a-f]0:' + ' ([0-9a-f]{2})' * 16)
    self._memtool_pattern = re.compile(r'0x[0-9A-F]{8}:  ([0-9A-F]{8})')
    self._all_edids = ["RESERVED"]

  def Reset(self):
    """Resets Chameleon board."""
    # TODO(waihong): Add the procedure to reset the board.
    pass

  def ProbeInputs(self):
    """Probes all the display connectors on Chameleon board.

    Returns:
      A tuple of input_id, for the connectors connected to DUT.
    """
    # TODO(waihong): Add the +5V pin detection.
    # TODO(waihong): Probe the daughter card to see if it is a HDMI card.
    # TODO(waihong): Support more cards, like DVI and DP.

    # So far, only HDMI (index: 1) supported.
    return (self._HDMI_ID, )

  def GetConnectorType(self, input_id):
    """Returns the human readable string for the connector type.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A string, like "VGA", "DVI", "HDMI", or "DP".
    """
    # TODO(waihong): Support more connectors, like DVI and DP.
    if input_id == self._HDMI_ID:
      return 'HDMI'
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def CreateEdid(self, edid):
    """Creates an internal record of EDID using the given byte array.

    Args:
      edid: A byte array of EDID data, wrapped in a xmlrpclib.Binary object.

    Returns:
      An edid_id.
    """
    if None in self._all_edids:
      last = self._all_edids.index(None)
      self._all_edids[last] = edid.data
    else:
      last = len(self._all_edids)
      self._all_edids.append(edid.data)
    return last

  def DestoryEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    self._all_edids[edid_id] = None

  # TODO(waihong): Move to some Python native library for I2C communication.
  def _DumpI2C(self, bus, slave):
    """Dumps all I2C content on the given bus and slave address.

    Args:
      bus: The number of bus.
      slave: The number of slave address.

    Returns:
      A byte-array of the I2C content.
    """
    command = ['i2cdump', '-f', '-y', str(bus), str(slave)]
    message = subprocess.check_output(command, stderr=subprocess.STDOUT)
    matches = self._i2cdump_pattern.findall(message)
    return array.array(
        'B', [int(s, 16) for match in matches for s in match]).tostring()

  def _SetI2C(self, bus, slave, data):
    """Sets the given I2C content on the given bus and slave address.

    Args:
      bus: The number of bus.
      slave: The number of slave address.
      data: The byte-array of content to set.
    """
    command = ['i2cset', '-f', '-y', str(bus), str(slave)]
    for index in xrange(0, len(data), 8):
      subprocess.check_call(command + [str(index)] +
          [str(ord(d)) for d in data[index:index+8]] + ['i'])

  # TODO(waihong): Move to some Python native library for memory access.
  def _ReadMem(self, address):
    """Reads the 32-bit integer from the given memory address.

    Args:
      address: The memory address.

    Returns:
      An integer.
    """
    command = ['memtool', '-32', '%#x' % address, '1']
    message = subprocess.check_output(command, stderr=subprocess.STDOUT)
    matches = self._memtool_pattern.search(message)
    if matches:
      return int(matches.group(1), 16)

  def _WriteMem(self, address, data):
    """Writes the given 32-bit integer to the given memory address.

    Args:
      address: The memory address.
      data: The 32-bit integer to write.
    """
    command = ['memtool', '-32', '%#x=%#x' % (address, data)]
    subprocess.check_output(command, stderr=subprocess.STDOUT)

  def ReadEdid(self, input_id):
    """Reads the EDID content of the selected input on Chameleon.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object.
    """
    if input_id == self._HDMI_ID:
      return xmlrpclib.Binary(
          self._DumpI2C(self._MAIN_I2C_BUS, self._EEPROM_I2C_SLAVE))
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def ApplyEdid(self, input_id, edid_id):
    """Applies the EDID to the selected input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      input_id: The ID of the input connector.
      edid_id: The ID of the EDID.
    """
    if input_id == self._HDMI_ID:
      # TODO(waihong): Implement I2C slave for EDID response.
      gpio_value = self._ReadMem(self._GPIO_MEM_ADDRESS)
      # Disable EEPROM write-protection.
      self._WriteMem(self._GPIO_MEM_ADDRESS,
                     gpio_value | self._GPIO_EEPROM_WP_N_MASK)
      self._SetI2C(self._MAIN_I2C_BUS, self._EEPROM_I2C_SLAVE,
                   self._all_edids[edid_id])
      self._WriteMem(self._GPIO_MEM_ADDRESS, gpio_value)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def Plug(self, input_id):
    """Asserts HPD line to high, emulating plug.

    Args:
      input_id: The ID of the input connector.
    """
    if input_id == self._HDMI_ID:
      gpio_value = self._ReadMem(self._GPIO_MEM_ADDRESS)
      self._WriteMem(self._GPIO_MEM_ADDRESS, gpio_value & ~self._GPIO_HPD_MASK)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def Unplug(self, input_id):
    """Deasserts HPD line to low, emulating unplug.

    Args:
      input_id: The ID of the input connector.
    """
    if input_id == self._HDMI_ID:
      gpio_value = self._ReadMem(self._GPIO_MEM_ADDRESS)
      self._WriteMem(self._GPIO_MEM_ADDRESS, gpio_value | self._GPIO_HPD_MASK)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def FireHpdPulse(self, input_id, deassert_interval_usec,
                   assert_interval_usec=None, repeat_count=1):
    """Fires a HPD pulse (high -> low -> high) or multiple HPD pulses.

    Args:
      input_id: The ID of the input connector.
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
      repeat_count: The count of repeating the HPD pulses.
    """
    if input_id == self._HDMI_ID:
      deassert_in_sec = float(deassert_interval_usec) / 1000000
      if assert_interval_usec:
        assert_in_sec = float(assert_interval_usec) / 1000000
      else:
        # Fall back to use the same value as deassertion if not given.
        assert_in_sec = deassert_in_sec
      for i in range(repeat_count):
        self.Unplug(input_id)
        time.sleep(deassert_in_sec)
        self.Plug(input_id)
        if i < repeat_count - 1:
          time.sleep(assert_in_sec)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def DumpPixels(self, input_id, x=None, y=None, width=None, height=None):
    """Dumps the raw pixel array of the selected area.

    If not given the area, default to capture the whole screen.

    Args:
      input_id: The ID of the input connector.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    if input_id == self._HDMI_ID:
      byte_per_pixel = 4
      # Capture the whole screen first.
      total_width, total_height = self.DetectResolution(input_id)
      total_size = total_width * total_height * byte_per_pixel
      with tempfile.NamedTemporaryFile() as f:
        # TODO(waihong): Direct memory dump instead of calling memdump2file.
        # XXX: memdump2file bug, should unconditional plus 1
        command = ['memdump2file', str(total_size / 1024 + 1), f.name]
        subprocess.call(command)
        screen = f.read()[:total_size]

      if x is not None and y is not None and width and height:
        # Return the given area.
        area = ''
        for pos_y in range(y, y + height):
          line_start = (pos_y * total_width + x) * byte_per_pixel
          line_end = line_start + width * byte_per_pixel
          area += screen[line_start:line_end]
        return xmlrpclib.Binary(area)
      else:
        return xmlrpclib.Binary(screen)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def ComputePixelChecksum(self, input_id, x=None, y=None, width=None,
        height=None):
    """Computes the checksum of pixels in the selected area.

    If not given the area, default to compute the whole screen.

    Args:
      input_id: The ID of the input connector.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      The checksum of the pixels.
    """
    raise NotImplementedError('ComputePixelChecksum')

  def DetectResolution(self, input_id):
    """Detects the source resolution.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A (width, height) tuple.
    """
    if input_id == self._HDMI_ID:
      width = self._ReadMem(self._FRAME_WIDTH_ADDRESS)
      height = self._ReadMem(self._FRAME_HEIGHT_ADDRESS)
      return (width, height)
    else:
      raise FpgaDriverError('Not a valid input_id.')
