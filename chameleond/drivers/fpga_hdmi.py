# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for FPGA customized platform."""

import logging
import os
import re
import tempfile
import time
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.interface import ChameleondInterface
from chameleond.utils import i2c_tool as i2c
from chameleond.utils import mem_tool as mem
from chameleond.utils import system_tools


class DriverError(Exception):
  """Exception raised when any error on FPGA driver."""
  pass


class ChipError(Exception):
  """Exception raised when any unexpected behavior happened on a chip."""
  pass


class BoardError(Exception):
  """Exception raised when any unexpected behavior happened on the board."""
  pass


class ErrorLevel(object):
  """Class to define the error level."""
  GOOD = 0
  # Chip error, be recovered by restarting Chameleond.
  CHIP_ERROR = 1
  # Board error, be recovered by rebooting the board.
  BOARD_ERROR = 2


class ChameleondDriver(ChameleondInterface):
  """Chameleond Driver for FPGA customized platform."""

  _HDMI_ID = 1

  _PIXEL_FORMAT = 'rgba'

  _GPIO_MEM_ADDRESS = 0xff2100d0
  _FRAME_WIDTH_ADDRESS = 0xff210100
  _FRAME_HEIGHT_ADDRESS = 0xff210104

  _GPIO_EEPROM_WP_N_MASK = 0x1
  _GPIO_HPD_MASK = 0x2

  _HDMIRX_I2C_BUS = 0
  _DDC_I2C_BUS = 1
  _EEPROM_I2C_SLAVE = 0x50
  _HDMIRX_I2C_SLAVE = 0x48

  # Peripheral Module Reset Register
  _PERMODRST_MEM_ADDRESS = 0xffd05014
  _I2C_RESET_MASK = {
      _HDMIRX_I2C_BUS: 0x1000,
      _DDC_I2C_BUS: 0x2000
  }
  # FIXME: no document about width of the reset pulse; this is from experience
  _DELAY_I2C_RESET = 0.1

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

  _DELAY_VIDEO_MODE_PROBE = 0.1
  _TIMEOUT_VIDEO_STABLE_PROBE = 10

  def __init__(self, *args, **kwargs):
    super(ChameleondDriver, self).__init__(*args, **kwargs)
    self._hpd_control_pattern = re.compile(r'HPD=([01])')
    # Reserve index 0 as the default EDID.
    self._all_edids = [self._ReadDefaultEdid()]
    self._active_edid_id = -1
    self._error_level = ErrorLevel.GOOD
    self._tools = system_tools.SystemTools
    self._memory = mem.Memory
    self._hdmirx_bus = i2c.I2cBus(self._tools, self._HDMIRX_I2C_BUS)
    self._hdmirx_bus.RegisterResetter(
        lambda: self._ResetI2CBus(self._HDMIRX_I2C_BUS))
    self._ddc_bus = i2c.I2cBus(self._tools, self._DDC_I2C_BUS)
    self._ddc_bus.RegisterResetter(lambda: self._ResetI2CBus(self._DDC_I2C_BUS))
    self._hdmirx = self._hdmirx_bus.CreateSlave(self._HDMIRX_I2C_SLAVE)
    self._eeprom = self._ddc_bus.CreateSlave(self._EEPROM_I2C_SLAVE)

    # Skip the BoardError, like I2C access failure, in order not to block the
    # start-up of the RPC server. The repair routine will perform later.
    try:
      self.Reset()
    except (DriverError, ChipError, BoardError):
      pass

    # Set all ports unplugged on initialization.
    for input_id in self.ProbeInputs():
      self.Unplug(input_id)

  def _IsModeChanged(self):
    """Returns whether the video mode is changed.

    Returns:
      True if the video mode is changed; otherwsie, False.
    """
    video_mode = self._hdmirx.Get(self._HDMIRX_REG_VIDEO_MODE)
    return bool(video_mode & self._HDMIRX_MASK_MODE_CHANGED)

  def _IsVideoInputStable(self):
    """Returns whether the video input is stable.

    Returns:
      True if the video input is stable; otherwise, False.
    """
    video_mode = self._hdmirx.Get(self._HDMIRX_REG_VIDEO_MODE)
    return bool(video_mode & self._HDMIRX_MASK_VIDEO_STABLE)

  def _IsFrameLocked(self):
    """Returns whether the FPGA frame is locked.

    It compares the resolution reported from the HDMI receiver with the FPGA.

    Returns:
      True if the frame is locked; otherwise, False.
    """
    fpga = self._GetResolutionFromFpga()
    rx = self._GetResolutionFromReceiver()
    if fpga == rx:
      logging.info('same resolution: %dx%d', *fpga)
      return True
    else:
      logging.info('diff resolution: fpga:%dx%d != rx:%dx%d', *(fpga + rx))
      return False

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
    if self.IsPlugged(self._HDMI_ID):
      # Wait the vidoe input stable before the check.
      if not self.WaitVideoInputStable(self._HDMI_ID):
        # Sometime the video-stable-bit not set is caused by a receiver issue.
        # Safer to mark it as a chip error, such that it can be repaired.
        self._error_level = ErrorLevel.CHIP_ERROR
        if raise_error_if_no_input:
          raise DriverError('no video input detected')
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

  def _WaitForCondition(self, func, value, timeout):
    """Waits for the given function matches the given value.

    Args:
      func: The function to be tested.
      value: The value to fit the condition.
      timeout: The timeout in second to break the check.

    Raises:
      DriverError if timeout.
    """
    end_time = start_time = time.time()
    while end_time - start_time < timeout:
      if func() == value:
        break
      logging.info('Waiting for condition %s == %s', func.__name__, str(value))
      time.sleep(self._DELAY_VIDEO_MODE_PROBE)
      end_time = time.time()
    else:
      raise DriverError('Timeout on waiting for condition %s == %s' %
                        (str(func), str(value)))

  def _RestartReceiver(self):
    """Restarts the HDMI receiver."""
    logging.info('Resetting HDMI receiver...')
    self._hdmirx.SetAndClear(self._HDMIRX_REG_RST_CTRL,
       self._HDMIRX_MASK_CDRRST | self._HDMIRX_MASK_SWRST)

    try:
      self._WaitForCondition(self._IsModeChanged, False,
                             self._TIMEOUT_VIDEO_STABLE_PROBE)
      self._WaitForCondition(self._IsFrameLocked, True,
                             self._TIMEOUT_VIDEO_STABLE_PROBE)
    except DriverError as e:
      self._error_level = ErrorLevel.CHIP_ERROR
      raise ChipError(e)

    logging.info('Video is stable.')

  def Reset(self):
    """Resets Chameleon board."""
    logging.info('Execute the reset process.')
    self._ApplyDefaultEdid()
    self._RestartReceiverIfNeeded(raise_error_if_no_input=False)
    logging.info('Done Execute the reset process.')

  def IsHealthy(self):
    """Returns if the Chameleon is healthy or any repair is needed.

    Returns:
      True if the Chameleon is healthy; otherwise, False, need to repair.
    """
    return self._error_level == ErrorLevel.GOOD

  def Repair(self):
    """Repairs the Chameleon.

    It can be an asynchronous call, e.g. do the repair after return. An
    approximate time of the repair is returned. The caller should wait that
    time before the next action.

    Returns:
      An approximate repair time in second.
    """
    logging.info('Error Level: %d', self._error_level)
    if self._error_level == ErrorLevel.CHIP_ERROR:
      logging.info('Try to restart Chameleond...')
      self._tools.DelayedCall(1, 'chameleond', 'restart')
      return 20
    elif self._error_level == ErrorLevel.BOARD_ERROR:
      logging.info('Try to reboot the board...')
      self._tools.DelayedCall(1, 'reboot')
      return 120
    return 0

  def GetSupportedInputs(self):
    """Returns all supported connectors on the board.

    Not like the ProbeInputs() method which only returns the connectors which
    are connected, this method returns all supported connectors on the board.

    Returns:
      A tuple of input_id, for all supported connectors on the board.
    """
    return (self._HDMI_ID, )

  def IsPhysicalPlugged(self, input_id):
    """Returns if the physical cable is plugged.

    It checks the source power +5V/+3.3V pin.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    if input_id == self._HDMI_ID:
      sys_state = self._hdmirx.Get(self._HDMIRX_REG_SYS_STATE)
      return bool(sys_state & self._HDMIRX_MASK_PWR5V_DETECT)
    else:
      raise DriverError('Not a valid input_id.')

  def ProbeInputs(self):
    """Probes all the display connectors on Chameleon board.

    Returns:
      A tuple of input_id, for the connectors connected to DUT.
    """
    # TODO(waihong): Probe the daughter card to see if it is a HDMI card.
    # TODO(waihong): Support more cards, like DVI and DP.
    input_ids = []
    # So far, only HDMI (index: 1) supported.
    for input_id in self.GetSupportedInputs():
      if self.IsPhysicalPlugged(input_id):
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
      raise DriverError('Not a valid input_id.')

  def WaitVideoInputStable(self, input_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      input_id: The ID of the input connector.
      timeout: The time period to wait for.

    Returns:
      True if the video input becomes stable within the timeout period;
      otherwise, False.
    """
    if input_id == self._HDMI_ID:
      if timeout is None:
        timeout = self._TIMEOUT_VIDEO_STABLE_PROBE
      try:
        self._WaitForCondition(self._IsVideoInputStable, True, timeout)
      except DriverError:
        return False
      return True
    else:
      raise DriverError('Not a valid input_id.')

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
      raise DriverError('Not a valid edid_id.')

  def _ResetI2CBus(self, bus):
    """Resets the I2C controller for the given I2C bus.

    Args:
      bus: The number of bus.
    """
    self._memory.SetAndClearMask(self._PERMODRST_MEM_ADDRESS,
                                 self._I2C_RESET_MASK[bus],
                                 self._DELAY_I2C_RESET)

  def ReadEdid(self, input_id):
    """Reads the EDID content of the selected input on Chameleon.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object.
    """
    if input_id == self._HDMI_ID:
      try:
        return xmlrpclib.Binary(self._eeprom.Dump())
      except i2c.I2cBusError as e:
        self._error_level = ErrorLevel.BOARD_ERROR
        raise BoardError(e)
    else:
      raise DriverError('Not a valid input_id.')

  def _ApplyHdmiEdid(self, edid_id):
    """Applies the EDID to the HDMI input.

    This method does not check the validity of edid_id.

    Args:
      edid_id: The ID of the EDID.
    """
    # TODO(waihong): Implement I2C slave for EDID response.
    # Disable EEPROM write-protection.
    self._memory.SetMask(self._GPIO_MEM_ADDRESS, self._GPIO_EEPROM_WP_N_MASK)
    try:
      self._eeprom.Set(self._all_edids[edid_id])
    except i2c.I2cBusError as e:
      self._error_level = ErrorLevel.BOARD_ERROR
      raise BoardError(e)
    finally:
      # Enable EEPROM write-protection.
      self._memory.ClearMask(self._GPIO_MEM_ADDRESS,
                             self._GPIO_EEPROM_WP_N_MASK)

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
        raise DriverError('Not a valid edid_id.')
    else:
      raise DriverError('Not a valid input_id.')

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
    if self._active_edid_id != 0:
      logging.info('Apply the default EDID.')
      self._ApplyHdmiEdid(0)

  def IsPlugged(self, input_id):
    """Returns if the HPD line is plugged.

    Args:
      input_id: The ID of the input connector.

    Returns:
      True if the HPD line is plugged; otherwise, False.
    """
    if not self.IsPhysicalPlugged(input_id):
      return False

    if input_id == self._HDMI_ID:
      message = self._tools.Output('hpd_control', 'status')
      matches = self._hpd_control_pattern.match(message)
      if matches:
        return bool(matches.group(1) == '1')
      else:
        raise DriverError('hpd_control has wrong format.')
    else:
      raise DriverError('Not a valid input_id.')

  def Plug(self, input_id):
    """Asserts HPD line to high, emulating plug.

    Args:
      input_id: The ID of the input connector.
    """
    if input_id == self._HDMI_ID:
      self._tools.Call('hpd_control', 'plug')
    else:
      raise DriverError('Not a valid input_id.')

  def Unplug(self, input_id):
    """Deasserts HPD line to low, emulating unplug.

    Args:
      input_id: The ID of the input connector.
    """
    if input_id == self._HDMI_ID:
      self._tools.Call('hpd_control', 'unplug')
    else:
      raise DriverError('Not a valid input_id.')

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
      if assert_interval_usec is None:
        # Fall back to use the same value as deassertion if not given.
        assert_interval_usec = deassert_interval_usec
      self._tools.Call('hpd_control', 'repeat_pulse', deassert_interval_usec,
                       assert_interval_usec, repeat_count)
    else:
      raise DriverError('Not a valid input_id.')

  def GetPixelFormat(self):
    """Returns the pixel format for the output of DumpPixels.

    Returns:
      A string of the format, like 'rgba', 'bgra', 'rgb', etc.
    """
    return self._PIXEL_FORMAT

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
    if not self.IsPlugged(input_id):
      raise DriverError('HPD is unplugged. No signal is expected.')

    if input_id == self._HDMI_ID:
      self._RestartReceiverIfNeeded(raise_error_if_no_input=True)

      total_width, total_height = self.DetectResolution(input_id)
      with tempfile.NamedTemporaryFile() as f:
        if x is None or y is None or not width or not height:
          self._tools.Call('pixeldump', f.name, total_width, total_height,
                           len(self._PIXEL_FORMAT))
        else:
          self._tools.Call('pixeldump', f.name, total_width, total_height,
                           len(self._PIXEL_FORMAT), x, y, width, height)
        screen = f.read()
      return xmlrpclib.Binary(screen)
    else:
      raise DriverError('Not a valid input_id.')

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
    width = self._memory.Read(self._FRAME_WIDTH_ADDRESS)
    height = self._memory.Read(self._FRAME_HEIGHT_ADDRESS)
    return (width, height)

  def _GetResolutionFromReceiver(self):
    """Gets the resolution reported from the HDMI receiver.

    Returns:
      A (width, height) tuple.
    """
    hactive_h = self._hdmirx.Get(self._HDMIRX_REG_HACTIVE_H)
    hactive_l = self._hdmirx.Get(self._HDMIRX_REG_HACTIVE_L)
    vactive_h = self._hdmirx.Get(self._HDMIRX_REG_VACTIVE_H)
    vactive_l = self._hdmirx.Get(self._HDMIRX_REG_VACTIVE_L)
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
    if not self.IsPlugged(input_id):
      raise DriverError('HPD is unplugged. No signal is expected.')

    if input_id == self._HDMI_ID:
      self._RestartReceiverIfNeeded(raise_error_if_no_input=True)
      return self._GetResolutionFromFpga()
    else:
      raise DriverError('Not a valid input_id.')
