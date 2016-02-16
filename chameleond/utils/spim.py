# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""SPI master module for controlling Cyclone V HPS peripherals.

Before using, please make sure the correspondent SPIM pins are connected to
desired peripheral in SocKit IO pinmux setting.

For now, only HPS LCM module is connected to SPIM1 as TX-only SPI.
"""

import logging

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common
from chameleond.utils import mem


class SpimError(Exception):
  """Exception raise when any unexpected behavior happened on SPIM."""
  pass


class Spim(object):
  """A Class to abstract the behavior of SPIM."""

  # Register base addresses for SPI master 0, 1.
  _BASE_ADDRESSES = (0xfff00000, 0xfff01000)

  _RESET_ADDRESS = 0xffd05014
  _RESET_BITMASKS = (0x00040000, 0x00080000)

  _CTLR0_OFFSET = 0x00
  _SPIENR_OFFSET = 0x08
  _SER_OFFSET = 0x10
  _BAUDR_OFFSET = 0x14
  _SR_OFFSET = 0x28
  _DR_OFFSET = 0x60

  _TXFIFO_EMPTY_BITMASK = 0x4
  _SPIM_BUSY_BITMASK = 0x1

  _WAIT_DELAY = 1.0 / 3125000
  _WAIT_TIMEOUT = 2.0

  def __init__(self, master, baudrate_divider=64, tx_only=False):
    """Constructs a Spim object.

    Args:
      master: The master index.
      baudrate_divider: The spi_m_ck divider value of the data transfer
          frequency. This value will write into BAUDR register.
      tx_only: True if SPIM is TX-only.
    """
    if master != 1:
      raise SpimError('SPIM %d is not supported...' % master)
    self._master = master
    self._base_addr = self._BASE_ADDRESSES[master]
    self._memory = mem.MemoryForHPS
    self._tx_only = tx_only
    self.HardwareReset()
    self.Initialize(baudrate_divider)

  def HardwareReset(self):
    """Triggers hardware reset signal."""
    logging.info('HW Reset SPIM %d...', self._master)
    # Enable SPIM interface
    self._memory.ClearMask(self._RESET_ADDRESS,
                           self._RESET_BITMASKS[self._master])

  def Initialize(self, baudrate_divider):
    """Initializes hardware settings.

    Args:
      baudrate_divider: This value will write into BAUDR register.
    """
    logging.info('Initializing SPIM %d...', self._master)
    # Disable SPIM (spim_spienr.spi_en = 0)
    self._memory.ClearMask(self._base_addr + self._SPIENR_OFFSET, 0x1)
    # Write control register 0 (spim_ctrlr0.tmod)
    tmod = 0x1 if self._tx_only else 0x0
    self._memory.ClearMask(self._base_addr + self._CTLR0_OFFSET, 0x3 << 8)
    self._memory.SetMask(self._base_addr + self._CTLR0_OFFSET, tmod << 8)
    # Write baudrate select register (spim_baudr.sckdv)
    self._memory.ClearMask(self._base_addr + self._BAUDR_OFFSET, 0xffff)
    self._memory.SetMask(self._base_addr + self._BAUDR_OFFSET, baudrate_divider)
    # Write slave enable register to enable the target slave (spim_ser.ser = 1)
    self._memory.ClearMask(self._base_addr + self._SER_OFFSET, 0xf)
    self._memory.SetMask(self._base_addr + self._SER_OFFSET, 0x1)

    # Enable SPIM (spim_spienr.spi_en = 1)
    self._memory.SetMask(self._base_addr + self._SPIENR_OFFSET, 0x1)
    logging.info('SPIM %d Init Done...', self._master)

  def WriteData(self, data):
    """Writes TX data.

    Args:
      data: TX data.
    """
    if data > 0xffff:
      raise SpimError('Write data is over 16-bit long!! Input = 0x%x' % data)
    common.WaitForCondition(
        self._IsTxFifoEmpty, True, self._WAIT_DELAY, self._WAIT_TIMEOUT)
    self._memory.Write(self._base_addr + self._DR_OFFSET, data & 0xffff)
    common.WaitForCondition(
        self._IsTxFifoEmpty, True, self._WAIT_DELAY, self._WAIT_TIMEOUT)
    common.WaitForCondition(
        self._IsSpimBusy, False, self._WAIT_DELAY, self._WAIT_TIMEOUT)

  def _IsTxFifoEmpty(self):
    """Gets TX FIFO condition empty or not empty.

    Returns:
      True if TX FIFO is empty; False if TX FIFO is not empty.
    """
    return bool(self._memory.Read(self._base_addr + self._SR_OFFSET) &
                self._TXFIFO_EMPTY_BITMASK)

  def _IsSpimBusy(self):
    """Gets SPIM condition busy or idle.

    Returns:
      True if SPIM is busy; False if SPIM is idle.
    """
    return bool(self._memory.Read(self._base_addr + self._SR_OFFSET) &
                self._SPIM_BUSY_BITMASK)
