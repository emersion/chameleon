# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""DisplayPort, HDMI, and CRT receiver modules."""

import logging
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c_fpga


class DpRx(i2c_fpga.I2cSlave):
  """A class to control ITE IT6506 DisplayPort Receiver."""

  SLAVE_ADDRESSES = (0x58, 0x59)

  _AUDIO_RESET_DELAY = 0.001

  def Initialize(self):
    """Runs the initialization sequence for the chip."""
    logging.info('Initialize DisplayPort RX chip.')
    # Use the dual pixel mode by default.
    self.SetDualPixelMode()

    # TODO(waihong): Declare constants for the registers and values.
    self.Set(0x02, 0x05)  # bank 0
    self.Set(0x05, 0xef)  # inverse clock with 1ns adjustment
    self.Set(0xe0, 0xd2)  # video fifo gain???
    self.Set(0xc5, 0xcc)  # [3:0] CR Wait Time x 100us???
                          # This makes 2560x1600 work
    self.Set(0x03, 0x05)  # bank 1
    self.Set(0xee, 0xa5)  # max driving strength for video
    self.Set(0x03, 0xb8)  # ?

    # Initialize the audio path.
    self.Set(0x03, 0x05)
    self.Set(0xee, 0xa6) # max driving strength for audio
    self.Set(0x04, 0xb3) # reset audio pll
    self.Set(0x02, 0x05)
    self.Set(0x04, 0xea) # reset audio module
    time.sleep(self._AUDIO_RESET_DELAY)
    self.Set(0x03, 0x05)
    self.Set(0x00, 0xb3)
    self.Set(0x02, 0x05)
    self.Set(0x00, 0xea)

  def SetDualPixelMode(self):
    """Uses dual pixel mode which occupes 2 video paths in FPGA."""
    self.Set(0x02, 0x05)  # bank 0
    self.Set(0x6c, 0xed)  # power up dual pixel mode path
    self.Set(0x03, 0x05)  # bank 1
    self.Set(0x11, 0xa2)  # bit 0 reset FIFO
    self.Set(0x10, 0xa2)  # bit 4 enables dual pixel mode

  def SetSinglePixelMode(self):
    """Uses single pixel mode which occupes 1 video path in FPGA."""
    self.Set(0x02, 0x05)  # bank 0
    self.Set(0xec, 0xed)  # power down double pixel mode path
    self.Set(0x03, 0x05)  # bank 1
    self.Set(0x00, 0xa2)  # bit 4 disables dual pixel mode

  def IsCablePowered(self):
    """Returns if the cable is powered or not."""
    return bool(self.Get(0xc8) & (1 << 3))


class HdmiRx(i2c_fpga.I2cSlave):
  """A class to control ITE IT6803 HDMI Receiver."""

  SLAVE_ADDRESSES = (0x48, )

  _REG_INTERNAL_STATUS = 0x0a
  _BIT_P0_PWR5V_DET = 1

  def Initialize(self):
    """Runs the initialization sequence for the chip."""
    logging.info('Initialize HDMI RX chip.')
    # Use the dual pixel mode by default.
    self.SetDualPixelMode()

    # TODO(waihong): Declare constants for the registers and values.
    self.Set(0x33, 0x58)  # set driving strength to max (video)
    self.Set(0x33, 0x59)  # set driving strength to max (audio)

  def SetDualPixelMode(self):
    """Uses dual pixel mode which occupes 2 video paths in FPGA."""
    self.Set(0x02, 0x05)  # bank 0
    self.Set(0x0f, 0x0d)  # enable PHFCLK
    self.Set(0x01, 0x8b)  # enable dual pixel mode
    self.Set(0x08, 0x8c)  # enable QA IO

  def SetSinglePixelMode(self):
    """Uses single pixel mode which occupes 1 video path in FPGA."""
    self.Set(0x07, 0x0d)  # disable PHFCLK
    self.Set(0x80, 0x8b)  # disable dual pixel mode
    self.Set(0x09, 0x8c)  # enable QA IO, single pixel mode 1

  def IsCablePowered(self):
    """Returns if the cable is powered or not."""
    return bool(self.Get(self._REG_INTERNAL_STATUS) & self._BIT_P0_PWR5V_DET)


class VgaRx(i2c_fpga.I2cSlave):
  """A class to control ITE CAT9883C CRT Receiver."""

  SLAVE_ADDRESSES = (0x4c, )

  def Initialize(self):
    """Runs the initialization sequence for the chip."""
    logging.info('Initialize CRT RX chip.')
    # TODO(waihong): Declare constants for the registers and values.
    self.Set(0x69, 0x01)
    self.Set(0xd0, 0x02)
    self.Set(0x88, 0x03)
    self.Set(0xf0, 0x07)
    self.Set(0x68, 0x8f)
    self.Set(0x29, 0x86)
    self.Set(0x80, 0x8d)
    self.Set(0x00, 0x84)
    self.Set(0x69, 0x87)
    self.Set(0x30, 0x91)
    self.Set(0x22, 0x96)
    self.Set(0x19, 0x98)
    self.Set(0x0C, 0x84)
    self.Set(0x08, 0x99)
    self.Set(0x0f, 0x86)  # Tweak: max driving strength

    # TODO(waihong): Configure the proper mode setting.
