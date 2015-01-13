# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""EDID module to abstract different EDID behaviors."""

import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c
from chameleond.utils import ids
from chameleond.utils import io
from chameleond.utils import rx


class FRam(i2c.I2cSlave):
  """A Class to abstract the behavior of F-RAM."""

  HDMI_SLAVE = 0x49
  DP_SLAVE = 0x50
  SLAVE_ADDRESSES = (HDMI_SLAVE, DP_SLAVE)

  # M24C02 eeprom needs at most 5ms write time.
  # FM24CL04B fram doesn't need this delay.
  # TODO(waihong): Zero this delay if all boards use FM24CL04B.
  _WRITE_DELAY = 0.005

  def Write(self, data):
    """Writes the given data to the F-RAM.

    Args:
      data: A byte-array of content to write.
    """
    for i in range(0, len(data), 8):
      self.Set(data[i:i+8], i)
      time.sleep(self._WRITE_DELAY)

  def Read(self, size):
    """Reads the F-RAM content.

    Args:
      size: The total size to read.

    Returns:
      A string of data of the F-RAM content.
    """
    return self.Get(0, size)


class DpEdid(object):
  """Class to abstract the EDID of DisplayPort.

  The EDID of DisplayPort is stored in a F-RAM behind DisplayPort receiver.
  The receiver responses an EDID request by reading the F-RAM content and
  converting it to AUX signals.

  When programming the F-RAM, it switches the F-RAM from behind the receiver
  to the main I2C bus, such that ARM can see and program it.
  """
  _EDID_SIZE = 256
  _EDID_SRAM_MUXES = {
      ids.DP1: io.MuxIo.MASK_DP1_EDID_SRAM_MUX,
      ids.DP2: io.MuxIo.MASK_DP2_EDID_SRAM_MUX
  }

  def __init__(self, input_id, main_i2c_bus):
    """Constructs a DpEdid object.

    Args:
      input_id: The ID of the input.
      main_i2c_bus: The main I2cBus object.
    """
    self._input_id = input_id
    self._mux_io = main_i2c_bus.GetSlave(io.MuxIo.SLAVE_ADDRESSES[0])
    self._fram = main_i2c_bus.GetSlave(FRam.DP_SLAVE)
    self._on_main_before_access = None

  def _SwitchRamToMain(self):
    """Switches the F-RAM to the main I2C bus."""
    self._mux_io.SetOutputMask(self._EDID_SRAM_MUXES[self._input_id])

  def _SwitchRamToRx(self):
    """Switches the F-RAM to the I2C bus behind receiver for EDID."""
    self._mux_io.ClearOutputMask(self._EDID_SRAM_MUXES[self._input_id])

  def _IsRamOnMain(self):
    """Returns True if the F-RAM is on the main I2C bus; otherwise, False."""
    return bool(self._mux_io.GetOutput() &
                self._EDID_SRAM_MUXES[self._input_id])

  def Disable(self):
    """Disables the EDID response."""
    self._SwitchRamToMain()

  def Enable(self):
    """Enables the EDID response."""
    self._SwitchRamToRx()

  def _BeginAccess(self):
    """Performs the sequence before EDID access."""
    # Switch F-RAM to the main I2C main before access.
    self._on_main_before_access = self._IsRamOnMain()
    if not self._on_main_before_access:
      self._SwitchRamToMain()

  def _EndAccess(self):
    """Performs the sequence after EDID access."""
    if not self._on_main_before_access:
      self._SwitchRamToRx()

  def WriteEdid(self, data):
    """Writes the EDID content.

    Args:
      data: The EDID control to write.
    """
    self._BeginAccess()
    try:
      self._fram.Write(data)
    finally:
      self._EndAccess()

  def ReadEdid(self):
    """Reads the EDID content.

    Returns:
      A byte array of EDID data.
    """
    self._BeginAccess()
    try:
      edid = self._fram.Read(self._EDID_SIZE)
    finally:
      self._EndAccess()
    return edid


class HdmiEdid(object):
  """Class to abstract the EDID of HDMI.

  The EDID of HDMI is stored in an internal RAM of the HDMI receiver.
  By configuring the receiver, the internal RAM acts as a standard EEPROM,
  such that we can program and read its content.
  """
  _EDID_SIZE = 256

  def __init__(self, main_i2c_bus):
    """Constructs a HdmiEdid object.

    Args:
      main_i2c_bus: The main I2cBus object.
    """
    self._rx = main_i2c_bus.GetSlave(rx.HdmiRx.SLAVE_ADDRESSES[0])
    self._fram = main_i2c_bus.GetSlave(FRam.HDMI_SLAVE)
    self._enabled_before_access = None

  def _BeginAccess(self):
    """Performs the sequence before EDID access."""
    # Disable the EDID response during the update.
    self._enabled_before_access = self._rx.IsEdidEnabled()
    if self._enabled_before_access:
      self._rx.DisableEdid()
    self._rx.SetEdidSlave(FRam.HDMI_SLAVE)
    self._rx.EnableEdidAccess()

  def _EndAccess(self):
    """Performs the sequence after EDID access."""
    self._rx.DisableEdidAccess()
    if self._enabled_before_access:
      self._rx.EnableEdid()

  def _ValidateEdid(self, data):
    """Validates the EDID on the HDMI receiver.

    It updates the checksum to the receiver and makes the EDID validated.

    Args:
      data: The EDID control to write.
    """
    for block in (0, 1):
      # Skip the last byte, i.e. checksum.
      checksum = ((-sum(map(ord, data[128 * block:128 * (block + 1) - 1])))
                  & 0xff)
      self._rx.UpdateEdidChecksum(block, checksum)

  def Disable(self):
    """Disables the EDID response."""
    self._rx.DisableEdid()

  def Enable(self):
    """Enables the EDID response."""
    self._rx.EnableEdid()

  def WriteEdid(self, data):
    """Writes the EDID content.

    Args:
      data: The EDID control to write.
    """
    self._BeginAccess()
    try:
      self._fram.Write(data)
      self._ValidateEdid(data)
    finally:
      self._EndAccess()

  def ReadEdid(self):
    """Reads the EDID content.

    Returns:
      A byte array of EDID data.
    """
    self._BeginAccess()
    try:
      edid = self._fram.Read(self._EDID_SIZE)
    finally:
      self._EndAccess()
    return edid


class VgaEdid(object):
  """Class to abstract the EDID of VGA.

  The request of EDID of VGA is reponsed by the FPGA. There is a memory space
  in FPGA which stores the EDID content.
  """
  def __init__(self, fpga_ctrl):
    """Constructs a HdmiEdid object.

    Args:
      fpga_ctrl: The FpgaController object.
    """
    self._vga_edid = fpga_ctrl.vga_edid

  def Disable(self):
    """Disables the EDID response."""
    self._vga_edid.Disable()

  def Enable(self):
    """Enables the EDID response."""
    self._vga_edid.Enable()

  def WriteEdid(self, data):
    """Writes the EDID content.

    Args:
      data: The EDID control to write.
    """
    self._vga_edid.WriteEdid(data)

  def ReadEdid(self):
    """Reads the EDID content.

    Returns:
      A byte array of EDID data.
    """
    return self._vga_edid.ReadEdid()
