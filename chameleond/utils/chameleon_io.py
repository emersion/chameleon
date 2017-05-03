# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""I/O Expander module for controlling I2C I/O expander device."""

import logging
import struct
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c
from chameleond.utils import ids


class IoExpander(i2c.I2cSlave):
  """A class to abstract the behavior of the TCA6416A/TCA9995 I/O expander.

  TIO uses TCA6416A while the audio board uses TCA9995. Both I/O expanders
  share the same usage.
  """

  # TIO uses TCA6416A on 0x20, 0x21.
  # The audio board uses TCA9555 on 0x20, 0x21, 0x22.
  # The motor board uses TCA9555 on 0x23.
  SLAVE_ADDRESSES = (0x20, 0x21, 0x22, 0x23)

  _INPUT_BASE = 0
  _OUTPUT_BASE = 2
  _CONFIG_BASE = 6

  _REG_SET_DELAY_SECS = 0.001

  def _ReadPair(self, reg_base):
    """Reads the 2-byte value from a pair of registers.

    Args:
      reg_base: The register address of the low-byte.

    Returns:
      A 2-byte value.
    """
    return struct.unpack('H', self.Get(reg_base, 2))[0]

  def _WritePair(self, value, reg_base):
    """Writes the 2-byte value to a pair of registers.

    Args:
      value: A 2-byte value.
      reg_base: The register address of the low-byte.
    """
    data = struct.pack('H', value)
    self.Set(data, reg_base)

  def _GetDirection(self):
    """Gets the direction (input or output) for the ports.

    Returns:
      A 2-byte value of the direction mask (1: input, 0: output).
    """
    return self._ReadPair(self._CONFIG_BASE)

  def _SetBitDirection(self, offset, output):
    """Sets direction on a bit.

    Args:
      offset: The bit offset 0x0 to 0xf.
      output: True to set this bit as output. False to set this bit as input.
    """
    # Reads the current directions and only modifies the specified bit.
    old_value = self._GetDirection()

    if output:
      # 0 means output in SetDirection.
      mask = ~(1 << offset) & 0xffff
      new_value = old_value & mask
    else:
      # 1 means input in SetDirection.
      mask = (1 << offset) & 0xffff
      new_value = old_value | mask

    self.SetDirection(new_value)

  def IsDetected(self):
    """Checks if this I/O expander is detected.

    Returns:
      True if it is connected. False otherwise.
    """
    try:
      self._GetDirection()
      return True
    except i2c.I2cBusError:
      return False

  def GetInput(self):
    """Gets the input ports value.

    Returns:
      A 2-byte value of the input ports.
    """
    return self._ReadPair(self._INPUT_BASE)

  def GetOutput(self):
    """Gets the output ports value.

    Returns:
      A 2-byte value of the output ports.
    """
    return self._ReadPair(self._OUTPUT_BASE)

  def SetOutput(self, value):
    """Sets the ouput ports value.

    Args:
      value: a 2-byte value of the ouput ports.
    """
    self._WritePair(value, self._OUTPUT_BASE)

  def SetDirection(self, direction):
    """Sets the direction (input or output) for the ports.

    Args:
      direction: a 2-byte value of the direction mask (1: input, 0: output).
    """
    self._WritePair(direction, self._CONFIG_BASE)

  def SetOutputMask(self, mask):
    """Sets the mask on the current value of the output ports.

    Args:
      mask: The bitwise mask.
    """
    self.SetOutput(self.GetOutput() | mask)

  def ClearOutputMask(self, mask):
    """Clears the mask on the current value of the output ports.

    Args:
      mask: The bitwise mask.
    """
    self.SetOutput(self.GetOutput() & ~mask)

  def SetBit(self, offset, value):
    """Sets a bit as output and sets its value to 1 or 0.

    Args:
      offset: The bit offset 0x0 to 0xf.
      value: 1 or 0.
    """
    self._SetBitDirection(offset, True)
    mask = 1 << offset
    if value:
      self.SetOutputMask(mask)
    else:
      self.ClearOutputMask(mask)

  def ReadBit(self, offset):
    """Sets a bit as input and reads its value.

    Args:
      offset: The bit offset 0x0 to 0xf.

    Returns:
      1 or 0.
    """
    self._SetBitDirection(offset, False)
    mask = 1 << offset
    return 1 if self.GetInput() & mask else 0

  def ReadOutputBit(self, offset):
    """Reads the value of an output bit.

    Args:
      offset: The bit offset 0x0 to 0xf.

    Returns:
      1 or 0.
    """
    mask = 1 << offset
    return 1 if self.GetOutput() & mask else 0


class PowerIo(IoExpander):
  """A class to abstract the board I/O expander for power and reset.

  It is customized for the TIO daughter board.
  """

  SLAVE_ADDRESSES = (0x20, )

  MASK_RESERVED = 1 << 0
  MASK_EN_PP3300 = 1 << 1
  MASK_EN_PP1800 = 1 << 2
  MASK_EN_PP1200 = 1 << 3
  MASK_DP1_RST_L = 1 << 4
  MASK_DP2_RST_L = 1 << 5
  MASK_HDMI_RST_L = 1 << 6
  MASK_VGA_RST_L = 1 << 7
  MASK_DP1_INT_L = 1 << 8
  MASK_DP2_INT_L = 1 << 9
  MASK_HDMI_INT_L = 1 << 10
  MASK_LED_DP1 = 1 << 11
  MASK_LED_DP2 = 1 << 12
  MASK_LED_HDMI = 1 << 13
  MASK_LED_VGA = 1 << 14
  MASK_LED_I2C = 1 << 15

  _MASKS_RX_RST_L = {
      ids.DP1: MASK_DP1_RST_L,
      ids.DP2: MASK_DP2_RST_L,
      ids.HDMI: MASK_HDMI_RST_L,
      ids.VGA: MASK_VGA_RST_L
  }

  _RX_RESET_PULSE_SECS = 0.001
  _RX_RESET_DELAY_SECS = 0.1

  def __init__(self, i2c_bus, slave):
    """Constructs a PowerIo object.

    Args:
      i2c_bus: The I2cBus object.
      slave: The number of slave address.
    """
    super(PowerIo, self).__init__(i2c_bus, slave)
    logging.info('Initialize the Power I/O expander.')
    # Set all ports as output except the INT_L ones.
    self.SetDirection(
        self.MASK_DP1_INT_L | self.MASK_DP2_INT_L | self.MASK_HDMI_INT_L)
    # Enable all power and deassert reset.
    try:
      self.SetOutput(
          self.MASK_EN_PP3300 | self.MASK_EN_PP1800 | self.MASK_EN_PP1200 |
          self.MASK_DP1_RST_L | self.MASK_DP2_RST_L | self.MASK_HDMI_RST_L |
          self.MASK_VGA_RST_L)
    except i2c.I2cBusError:
      # This is to work around a problem where rx may pull i2c low for a short
      # amount of time (<3ms) when powered up for the very first time so
      # writing these two bytes out may cause the second byte to fail.
      logging.info('  ... re-enable the power for rx')
      self.SetOutput(
          self.MASK_EN_PP3300 | self.MASK_EN_PP1800 | self.MASK_EN_PP1200 |
          self.MASK_DP1_RST_L | self.MASK_DP2_RST_L | self.MASK_HDMI_RST_L |
          self.MASK_VGA_RST_L)

  def ResetReceiver(self, input_id):
    """Reset the given receiver.

    Args:
      input_id: The ID of the input connector.
    """
    self.ClearOutputMask(self._MASKS_RX_RST_L[input_id])
    time.sleep(self._RX_RESET_PULSE_SECS)
    self.SetOutputMask(self._MASKS_RX_RST_L[input_id])
    time.sleep(self._RX_RESET_DELAY_SECS)


class MuxIo(IoExpander):
  """A class to abstract the board I/O expander for muxes.

  It is customized for the TIO daughter board.
  """

  SLAVE_ADDRESSES = (0x21, )

  MASK_RX_A_MUX_OE_L = 1 << 0
  MASK_RX_A_MUX_S0 = 1 << 1
  MASK_RX_A_MUX_S1 = 1 << 2
  MASK_RX_B_MUX_OE_L = 1 << 3
  MASK_RX_B_MUX_S0 = 1 << 4
  MASK_RX_B_MUX_S1 = 1 << 5
  MASK_I2S_MUX_OE_L = 1 << 6
  MASK_I2S_MUX_S0 = 1 << 7
  MASK_I2S_MUX_S1 = 1 << 8
  MASK_DP1_AUX_BP_L = 1 << 9
  MASK_DP2_AUX_BP_L = 1 << 10
  MASK_HDMI_DDC_BP_L = 1 << 11
  MASK_DP1_EDID_SRAM_MUX = 1 << 12
  MASK_DP2_EDID_SRAM_MUX = 1 << 13
  MASK_VGA_BLOCK_SOURCE = 1 << 14
  MASK_LED_GREEN = 1 << 15

  CONFIG_MASK = 0x1ff
  CONFIG_DP1_DUAL = 0
  CONFIG_DP2_DUAL = MASK_RX_A_MUX_S0 | MASK_RX_B_MUX_S0 | MASK_I2S_MUX_S0
  CONFIG_HDMI_DUAL = MASK_RX_A_MUX_S1 | MASK_RX_B_MUX_S1 | MASK_I2S_MUX_S1
  CONFIG_VGA = MASK_RX_A_MUX_S0 | MASK_RX_A_MUX_S1 | MASK_RX_B_MUX_OE_L

  def __init__(self, i2c_bus, slave):
    """Constructs a PowerIo object.

    Args:
      i2c_bus: The I2cBus object.
      slave: The number of slave address.
    """
    super(MuxIo, self).__init__(i2c_bus, slave)
    logging.info('Initialize the Mux I/O expander.')
    # Set all ports as output.
    self.SetDirection(0)
    # Dual DP1 configuration, DP1 & DP2 AUX bypass, HDMI DDC bypass,
    # both SRAM connect to SINK, green led on.
    self.SetOutput(
        self.MASK_DP1_EDID_SRAM_MUX | self.MASK_DP2_EDID_SRAM_MUX |
        self.MASK_LED_GREEN)

  def SetConfig(self, config):
    """Set the configuration (video and audio paths) passing to FPGA.

    Args:
      config: The CONFIG_xxx value for the muxing.
    """
    self.SetOutput((self.GetOutput() & ~self.CONFIG_MASK) | config)
