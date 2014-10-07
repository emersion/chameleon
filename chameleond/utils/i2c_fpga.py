# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""I2C module for controlling I2C buses and I2C slaves.

It is customized for the FPGA board with the TIO (Three-In-One) daughter
card. It drives the I2C controllers emulated in the FPGA.
"""

import logging
import struct
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import mem_native as mem


class I2cBusError(Exception):
  """Exception raise when any unexpected behavior happened on I2C access."""
  pass


class I2cBus(object):
  """A Class to abstract the behavior of I2C bus."""

  # Register base addresses for the I2C bus 0, 1, and 2.
  _BASE_ADDRESSES = (0xff21b000, 0xff21c000, 0xff218000)

  def __init__(self, bus):
    """Constructs a I2cBus object.

    Args:
      bus: The bus number.
    """
    self.base_addr = self._BASE_ADDRESSES[bus]
    self._slaves = {}

  def _CreateSlave(self, slave, base_class=None):
    """Creates the I2C slave object of the given slave address.

    This method recursively finds the most matched subclass. A subclass
    should define its SLAVE_ADDRESSES class attribute, which is a tuple of
    the supported slave addresses. The class method IsSlaveSupported checks
    if the given slave is in the SLAVE_ADDRESSES.

    Args:
      slave: The number of slave address.
      base_class: The base class to find, default: I2cSlave.

    Returns:
      An I2cSlave or its subclass object.
    """
    if base_class is None:
      base_class = I2cSlave

    for cls in base_class.__subclasses__():
      if hasattr(cls, 'IsSlaveSupported') and cls.IsSlaveSupported(slave):
        return self._CreateSlave(slave, cls)

    logging.info('Create a %s object for slave %#x.',
                 base_class.__name__, slave)
    return base_class(self, slave)

  def GetSlave(self, slave):
    """Gets the I2C slave object of the given slave address.

    It returns the cached the I2cSlave objects if they are already created.

    Args:
      slave: The number of slave address.

    Returns:
      An I2cSlave or its subclass object.
    """
    if slave not in self._slaves:
      self._slaves[slave] = self._CreateSlave(slave)
    return self._slaves[slave]


class I2cSlave(object):
  """A Class to abstract the behavior of I2C slave."""

  # A subclass of I2cSlave should modify it to the supported slave addresses.
  SLAVE_ADDRESSES = tuple(range(127))

  _REG_SLAVE_ADDR_DIR = 3 * 4
  _REG_SLAVE_OFFSET = 4 * 4
  _REG_TRIGGER = 5 * 4
  _REG_STATUS = 6 * 4
  _REG_LENGTH = 7 * 4
  _REG_TX_BUFFER_0 = 8 * 4
  _REG_TX_BUFFER_1 = 9 * 4
  _REG_RX_BUFFER_0 = 10 * 4
  _REG_RX_BUFFER_1 = 11 * 4

  _BIT_STATUS_BUSY = 1
  _BIT_STATUS_ERROR = 2

  _I2C_WAIT_RETRIES = 3  # The number of retries.
  _I2C_WAIT_DELAY_SECS = 0.001  # 1ms = 100 bits
  _REG_SET_DELAY = 0.001

  def __init__(self, i2c_bus, slave):
    """Constructs a I2cSlave object.

    Args:
      i2c_bus: The I2cBus object.
      slave: The number of slave address.
    """
    self._i2c_bus = i2c_bus
    self._memory = mem.MemoryForController
    self._base_addr = self._i2c_bus.base_addr
    self._slave = slave

  @classmethod
  def IsSlaveSupported(cls, slave):
    """Determines if this class supports the given slave number.

    Args:
      slave: The number of slave address.
    """
    return slave in cls.SLAVE_ADDRESSES

  def _WaitForReady(self):
    """Waits for the I2C ready by polling the status register.

    Raises:
      I2cBusError if I2C timeout or error.
    """
    tries = 0
    while (self._memory.Read(self._base_addr + self._REG_STATUS) &
           self._BIT_STATUS_BUSY):
      tries += 1
      if tries > self._I2C_WAIT_RETRIES:
        raise I2cBusError('I2C busy timeout')
      time.sleep(self._I2C_WAIT_DELAY_SECS)
    if (self._memory.Read(self._base_addr + self._REG_STATUS) &
        self._BIT_STATUS_ERROR):
      raise I2cBusError('I2C access error')

  def Get(self, offset, size=1):
    """Gets the byte value of the given offset address.

    Args:
      offset: The offset address to read.
      size: The total size in byte to get.

    Returns:
      A string of data or an integer value if size=1.
    """
    # Set LSB for read.
    self._memory.Write(self._base_addr + self._REG_SLAVE_ADDR_DIR,
                       self._slave * 2 + 1)
    data = []
    for i in range(0, size, 8):
      size_to_read = min(8, size - i)
      self._memory.Write(self._base_addr + self._REG_SLAVE_OFFSET, offset + i)
      self._memory.Write(self._base_addr + self._REG_LENGTH, size_to_read)
      self._memory.Write(self._base_addr + self._REG_TRIGGER, 1)
      self._WaitForReady()
      word0 = self._memory.Read(self._base_addr + self._REG_RX_BUFFER_0)
      word1 = self._memory.Read(self._base_addr + self._REG_RX_BUFFER_1)
      data.append(struct.pack('>2I', word0, word1)[:size_to_read])

    if size == 1:
      return ord(data[0][0])
    else:
      return ''.join(data)

  def Set(self, data, offset=0):
    """Sets the given I2C content to the given offset address.

    Args:
      data: A byte or a byte-array of content to set.
      offset: The offset which the data starts from this address.
    """
    if not isinstance(data, str):
      data = chr(data)

    # Clear LSB for write.
    self._memory.Write(self._base_addr + self._REG_SLAVE_ADDR_DIR,
                       self._slave * 2)
    self._memory.Write(self._base_addr + self._REG_SLAVE_OFFSET, offset)

    size = len(data)
    for i in range(0, size, 8):
      size_to_write = min(8, size - i)
      data_to_write = data[i:i + size_to_write]
      # Padding
      if size_to_write < 8:
        data_to_write += '\0' * (8 - size_to_write)
      (word0, word1) = struct.unpack('>2I', data_to_write)
      self._memory.Write(self._base_addr + self._REG_TX_BUFFER_0, word0)
      self._memory.Write(self._base_addr + self._REG_TX_BUFFER_1, word1)
      self._memory.Write(self._base_addr + self._REG_LENGTH, size_to_write)
      self._memory.Write(self._base_addr + self._REG_TRIGGER, 1)
      self._WaitForReady()

  def SetMask(self, offset, mask):
    """Sets the mask on the given register offset.

    Args:
      offset: The offset of the register.
      mask: The bitwise mask.
    """
    self.Set(self.Get(offset) | mask, offset)

  def ClearMask(self, offset, mask):
    """Clears the mask on the given register offset.

    Args:
      offset: The offset of the register.
      mask: The bitwise mask.
    """
    self.Set(self.Get(offset) & ~mask, offset)

  def SetAndClear(self, offset, bitmask, delay_secs=None):
    """Sets I2C registers with the bitmask and then clears it.

    Args:
      offset: The offset of the register.
      bitmask: The bitmask to set and clear.
      delay_secs: The time between set and clear. Default: self._REG_SET_DELAY
    """
    byte = self.Get(offset)
    self.Set(byte | bitmask, offset)
    if delay_secs is None:
      delay_secs = self._REG_SET_DELAY
    time.sleep(delay_secs)
    self.Set(byte & ~bitmask, offset)
