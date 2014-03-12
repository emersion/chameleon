# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for FPGA customized platform."""

import array
import logging
import os
import re
import subprocess
import tempfile
import time
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.interface import ChameleondInterface


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
  _HDMIRX_I2C_SLAVE = 0x48

  _HDMIRX_REG_RST_CTRL = 0x05
  _HDMIRX_MASK_SWRST = 0x01
  _HDMIRX_MASK_CDRRST = 0x80

  _HDMIRX_REG_SYS_STATE = 0x10
  _HDMIRX_MASK_PWR5V_DETECT = 0x01

  _HDMIRX_REG_VIDEO_MODE = 0x58
  _HDMIRX_MASK_MODE_CHANGED = 0x01
  _HDMIRX_MASK_VIDEO_STABLE = 0x08

  _HDMIRX_REG_HACTIVE_H = 0x5a
  _HDMIRX_REG_HACTIVE_L = 0x5b
  _HDMIRX_REG_VACTIVE_H = 0x60
  _HDMIRX_REG_VACTIVE_L = 0x61

  _DELAY_REG_SET = 0.001
  _DELAY_VIDEO_MODE_PROBE = 0.1
  _TIMEOUT_VIDEO_STABLE_PROBE = 10

  _TOOL_PATHS = {
    'i2cdump': '/usr/local/sbin/i2cdump',
    'i2cget': '/usr/local/sbin/i2cget',
    'i2cset': '/usr/local/sbin/i2cset',
    'memdump2file': '/usr/local/sbin/memdump2file',
    'memtool': '/usr/bin/memtool',
  }

  def __init__(self, *args, **kwargs):
    super(FpgaDriver, self).__init__(*args, **kwargs)
    self._i2cget_pattern = re.compile(r'0x[0-9a-f]{2}')
    self._i2cdump_pattern = re.compile(r'[0-9a-f]0:' + ' ([0-9a-f]{2})' * 16)
    self._memtool_pattern = re.compile(r'0x[0-9A-F]{8}:  ([0-9A-F]{8})')
    # Reserve index 0 as the default EDID.
    self._all_edids = [self._ReadDefaultEdid()]
    self.Reset()

    self._CheckRequiredTools()
    # Set all ports unplugged on initialization.
    for input_id in self.ProbeInputs():
      self.Unplug(input_id)

  def _CheckRequiredTools(self):
    """Checks all the required tools exist.

    Raises:
      FpgaDriverError if missing a tool.
    """
    for path in self._TOOL_PATHS.itervalues():
      if not os.path.isfile(path):
        raise FpgaDriverError('Required tool %s not existed' % path)

  def _IsModeChanged(self):
    """Returns whether the video mode is changed.

    Returns:
      True if the video mode is changed; otherwsie, False.
    """
    video_mode = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                              self._HDMIRX_REG_VIDEO_MODE)
    return bool(video_mode & self._HDMIRX_MASK_MODE_CHANGED)

  def _IsVideoInputStable(self):
    """Returns whether the video input is stable.

    Returns:
      True if the video input is stable; otherwise, False.
    """
    video_mode = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                              self._HDMIRX_REG_VIDEO_MODE)
    return bool(video_mode & self._HDMIRX_MASK_VIDEO_STABLE)

  def _IsFrameLocked(self):
    """Returns whether the FPGA frame is locked.

    It compares the resolution reported from the HDMI receiver with the FPGA.

    Returns:
      True if the frame is locked; otherwise, False.
    """
    return self._GetResolutionFromFpga() == self._GetResolutionFromReceiver()

  def _RestartReceiverIfNeeded(self, raise_error_if_no_input):
    """Restarts the HDMI receiver if needed.

    The HDMI receiver should be restarted by checking the following conditions:
     - Video mode is changed, reported by the HDMI receiver;
     - Frame is not locked in FPGA.

    This method will be called when issuing a related command, like capturing
    a frame.

    Args:
      raise_error_if_no_input: The flag to control whether to raise an error
          if no video input is detected.
    """
    if self._IsPlugged(self._HDMI_ID):
      # Wait the vidoe input stable before the check.
      try:
        self._WaitForCondition(self._IsVideoInputStable, True,
                               self._TIMEOUT_VIDEO_STABLE_PROBE)
      except FpgaDriverError:
        if raise_error_if_no_input:
          raise FpgaDriverError('no video input detected')
        else:
          logging.info('no video input?')
          return

      need_restart = False
      if self._IsModeChanged():
        logging.info('Checked that the video mode is changed.')
        need_restart = True
      elif not self._IsFrameLocked():
        logging.info('Checked that the FPGA frame is not locked.')
        need_restart = True

      if need_restart:
        self._RestartReceiver()

  def _SetAndClearI2CRegister(self, bus, slave, offset, bitmask, delay=None):
    """Sets I2C registers with the bitmask and then clear it.

    Args:
      bus: The number of bus.
      slave: The number of slave address.
      offset: The offset of the register.
      bitmask: The bitmask to set and clear.
      delay: The time between set and clear. Default: self._DELAY_REG_SET
    """
    byte = self._GetI2C(bus, slave, offset)
    self._SetI2C(bus, slave, byte | bitmask, offset)
    if delay is None:
      delay = self._DELAY_REG_SET
    time.sleep(delay)
    self._SetI2C(bus, slave, byte & ~bitmask, offset)

  def _WaitForCondition(self, func, value, timeout):
    """Waits for the given function matches the given value.

    Args:
      func: The function to be tested.
      value: The value to fit the condition.
      timeout: The timeout in second to break the check.

    Raises:
      FpgaDriverError if timeout.
    """
    end_time = start_time = time.time()
    while end_time - start_time < timeout:
      if func() == value:
        break
      logging.info('Waiting for condition %s == %s', func.__name__, str(value))
      time.sleep(self._DELAY_VIDEO_MODE_PROBE)
      end_time = time.time()
    else:
      raise FpgaDriverError('Timeout on waiting for condition %s == %s' %
                            (str(func), str(value)))

  def _RestartReceiver(self):
    """Restarts the HDMI receiver."""
    logging.info('Resetting HDMI receiver...')
    self._SetAndClearI2CRegister(
        self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE, self._HDMIRX_REG_RST_CTRL,
        self._HDMIRX_MASK_CDRRST | self._HDMIRX_MASK_SWRST)

    self._WaitForCondition(self._IsModeChanged, False,
                           self._TIMEOUT_VIDEO_STABLE_PROBE)
    self._WaitForCondition(self._IsFrameLocked, True,
                           self._TIMEOUT_VIDEO_STABLE_PROBE)
    logging.info('Video is stable.')

  def Reset(self):
    """Resets Chameleon board."""
    logging.info('Execute the reset process.')
    self._ApplyDefaultEdid()
    self._RestartReceiverIfNeeded(raise_error_if_no_input=False)

  def _IsPhysicalPlugged(self, input_id):
    """Returns if the physical cable is plugged.

    It checks the source power +5V/+3.3V pin.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    if input_id == self._HDMI_ID:
      sys_state = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                               self._HDMIRX_REG_SYS_STATE)
      return bool(sys_state & self._HDMIRX_MASK_PWR5V_DETECT)
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def ProbeInputs(self):
    """Probes all the display connectors on Chameleon board.

    Returns:
      A tuple of input_id, for the connectors connected to DUT.
    """
    # TODO(waihong): Probe the daughter card to see if it is a HDMI card.
    # TODO(waihong): Support more cards, like DVI and DP.
    input_ids = []
    # So far, only HDMI (index: 1) supported.
    for input_id in (self._HDMI_ID, ):
      if self._IsPhysicalPlugged(input_id):
        input_ids.append(input_id)
    return tuple(input_ids)

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

  def DestroyEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    if edid_id > 0:
      self._all_edids[edid_id] = None
    else:
      raise FpgaDriverError('Not a valid edid_id.')

  # TODO(waihong): Move to some Python native library for I2C communication.
  def _DumpI2C(self, bus, slave):
    """Dumps all I2C content on the given bus and slave address.

    Args:
      bus: The number of bus.
      slave: The number of slave address.

    Returns:
      A byte-array of the I2C content.
    """
    command = [self._TOOL_PATHS['i2cdump'], '-f', '-y', str(bus), str(slave)]
    message = subprocess.check_output(command, stderr=subprocess.STDOUT)
    matches = self._i2cdump_pattern.findall(message)
    return array.array(
        'B', [int(s, 16) for match in matches for s in match]).tostring()

  def _GetI2C(self, bus, slave, offset):
    """Gets the byte value of the given I2C bus, slave, and offset address.

    Args:
      bus: The number of bus.
      slave: The number of slave address.
      offset: The offset address to read.

    Returns:
      An integer of the byte value.
    """
    command = [self._TOOL_PATHS['i2cget'], '-f', '-y', str(bus),
               str(slave), str(offset)]
    message = subprocess.check_output(command, stderr=subprocess.STDOUT)
    matches = self._i2cget_pattern.match(message)
    if matches:
      return int(matches.group(0), 0)
    else:
      raise FpgaDriverError('The output format of i2cget is not matched.')

  def _SetI2C(self, bus, slave, data, offset=0):
    """Sets the given I2C content on the given bus and slave address.

    Args:
      bus: The number of bus.
      slave: The number of slave address.
      data: A byte or a byte-array of content to set.
      offset: The offset which the data starts from this address.
    """
    command = [self._TOOL_PATHS['i2cset'], '-f', '-y', str(bus), str(slave)]
    if isinstance(data, str):
      for index in xrange(0, len(data), 8):
        subprocess.check_call(command + [str(offset + index)] +
            [str(ord(d)) for d in data[index:index+8]] + ['i'])
    elif isinstance(data, int) and 0 <= data <= 0xff:
      subprocess.check_call(command + [str(offset), str(data)])
    else:
      raise FpgaDriverError('The argument data is not a valid type.')

  # TODO(waihong): Move to some Python native library for memory access.
  def _ReadMem(self, address):
    """Reads the 32-bit integer from the given memory address.

    Args:
      address: The memory address.

    Returns:
      An integer.
    """
    command = [self._TOOL_PATHS['memtool'], '-32', '%#x' % address, '1']
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
    command = [self._TOOL_PATHS['memtool'], '-32', '%#x=%#x' % (address, data)]
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

  def _ApplyHdmiEdid(self, edid_id):
    """Applies the EDID to the HDMI input.

    This method does not check edid_id valid.

    Args:
      edid_id: The ID of the EDID.
    """
    # TODO(waihong): Implement I2C slave for EDID response.
    gpio_value = self._ReadMem(self._GPIO_MEM_ADDRESS)
    # Disable EEPROM write-protection.
    self._WriteMem(self._GPIO_MEM_ADDRESS,
                   gpio_value | self._GPIO_EEPROM_WP_N_MASK)
    self._SetI2C(self._MAIN_I2C_BUS, self._EEPROM_I2C_SLAVE,
                 self._all_edids[edid_id])
    self._WriteMem(self._GPIO_MEM_ADDRESS, gpio_value)

  def ApplyEdid(self, input_id, edid_id):
    """Applies the EDID to the selected input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      input_id: The ID of the input connector.
      edid_id: The ID of the EDID.
    """
    if input_id == self._HDMI_ID:
      if edid_id > 0:
        self._ApplyHdmiEdid(edid_id)
      else:
        raise FpgaDriverError('Not a valid edid_id.')
    else:
      raise FpgaDriverError('Not a valid input_id.')

  def _ReadDefaultEdid(self):
    """Reads the default EDID from file.

    Returns:
      A byte array of EDID data.
    """
    driver_dir = os.path.dirname(os.path.realpath(__file__))
    edid_path = os.path.join(driver_dir, '..', 'data', 'default_edid.bin')
    return open(edid_path).read()

  def _ApplyDefaultEdid(self):
    """Applies the default EDID to the HDMI input."""
    if self.ReadEdid(self._HDMI_ID).data != self._all_edids[0]:
      logging.info('Apply the default EDID.')
      self._ApplyHdmiEdid(0)

  def _IsPlugged(self, input_id):
    """Returns if the HPD line is plugged.

    Returns:
      True if the HPD line is plugged; otherwise, False.
    """
    if not self._IsPhysicalPlugged(input_id):
      return False

    if input_id == self._HDMI_ID:
      gpio_value = self._ReadMem(self._GPIO_MEM_ADDRESS)
      return not (gpio_value & self._GPIO_HPD_MASK)
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
    if not self._IsPlugged(input_id):
      raise FpgaDriverError('HPD is unplugged. No signal is expected.')

    if input_id == self._HDMI_ID:
      self._RestartReceiverIfNeeded(raise_error_if_no_input=True)
      byte_per_pixel = 4
      # Capture the whole screen first.
      total_width, total_height = self.DetectResolution(input_id)
      total_size = total_width * total_height * byte_per_pixel
      with tempfile.NamedTemporaryFile() as f:
        # TODO(waihong): Direct memory dump instead of calling memdump2file.
        # XXX: memdump2file bug, should unconditional plus 1
        command = [self._TOOL_PATHS['memdump2file'],
                   str(total_size / 1024 + 1), f.name]
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

  def _GetResolutionFromFpga(self):
    """Gets the resolution reported from the FPGA.

    Returns:
      A (width, height) tuple.
    """
    width = self._ReadMem(self._FRAME_WIDTH_ADDRESS)
    height = self._ReadMem(self._FRAME_HEIGHT_ADDRESS)
    return (width, height)

  def _GetResolutionFromReceiver(self):
    """Gets the resolution reported from the HDMI receiver.

    Returns:
      A (width, height) tuple.
    """
    hactive_h = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                             self._HDMIRX_REG_HACTIVE_H)
    hactive_l = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                             self._HDMIRX_REG_HACTIVE_L)
    vactive_h = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                             self._HDMIRX_REG_VACTIVE_H)
    vactive_l = self._GetI2C(self._MAIN_I2C_BUS, self._HDMIRX_I2C_SLAVE,
                             self._HDMIRX_REG_VACTIVE_L)
    width = (hactive_h & 0xf0) << 4 | hactive_l
    height = (vactive_h & 0xf0) << 4 | vactive_l
    return (width, height)

  def DetectResolution(self, input_id):
    """Detects the source resolution.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A (width, height) tuple.
    """
    if not self._IsPlugged(input_id):
      raise FpgaDriverError('HPD is unplugged. No signal is expected.')

    if input_id == self._HDMI_ID:
      self._RestartReceiverIfNeeded(raise_error_if_no_input=True)
      return self._GetResolutionFromFpga()
    else:
      raise FpgaDriverError('Not a valid input_id.')
