# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""DisplayPort, HDMI, and CRT receiver modules."""

import logging
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c


class RxError(Exception):
  """Exception raised when any error on receiver."""
  pass


class DpRx(i2c.I2cSlave):
  """A class to control ITE IT6506 DisplayPort Receiver."""

  SLAVE_ADDRESSES = (0x58, 0x59)

  _AUDIO_RESET_DELAY = 0.001
  _VIDEO_RESET_DELAY = 0.001

  _REG_INPUT_STATUS = 0x11
  _BIT_VIDEO_STABLE = 1 << 4

  _REG_FUNC_RESET = 0xEA
  _REG_PLL_RESET = 0xB3  # This is at bank 1
  _BIT_RESET_VIDEO = 0x02

  _REG_HACTIVE_H = 0x9C
  _REG_HACTIVE_L = 0x9B
  _REG_VACTIVE_H = 0xA2
  _REG_VACTIVE_L = 0xA1

  def Initialize(self, dual_pixel_mode):
    """Runs the initialization sequence for the chip."""
    logging.info('Initialize DisplayPort RX chip.')
    if dual_pixel_mode:
      self.SetDualPixelMode()
    else:
      self.SetSinglePixelMode()

    # TODO(waihong): Declare constants for the registers and values.
    self._SwitchBank(0)
    self.Set(0x01, 0xe3)  # make interrupt output polarity active low to
                          # match hdmi
    self.Set(0xe0, 0xd2)  # video fifo gain???
    self.Set(0xc5, 0xcc)  # [3:0] CR Wait Time x 100us???
                          # This makes 2560x1600 work
    self._SwitchBank(1)
    self.Set(0xee, 0xa5)  # the driving strength for video
                          # (ITE firmware uses 0xc8)
    self.Set(0x03, 0xb8)  # ?

    # Initialize the audio path.
    self._SwitchBank(1)
    self.Set(0xee, 0xa6) # max driving strength for audio
    self.Set(0x04, 0xb3) # reset audio pll
    self._SwitchBank(0)
    self.Set(0x04, 0xea) # reset audio module
    time.sleep(self._AUDIO_RESET_DELAY)
    self._SwitchBank(1)
    self.Set(0x00, 0xb3)
    self._SwitchBank(0)
    self.Set(0x00, 0xea)

  def SetDualPixelMode(self):
    """Uses dual pixel mode which occupes 2 video paths in FPGA."""
    self._SwitchBank(0)
    self.Set(0x6c, 0xed)  # power up dual pixel mode path
    self.Set(0x06, 0xef)  # tune dual pixel dp timing
    self._SwitchBank(1)
    self.Set(0x11, 0xa2)  # bit 0 reset FIFO
    self.Set(0x10, 0xa2)  # bit 4 enables dual pixel mode
    self._SwitchBank(0)

  def SetSinglePixelMode(self):
    """Uses single pixel mode which occupes 1 video path in FPGA."""
    self._SwitchBank(0)
    self.Set(0xec, 0xed)  # power down double pixel mode path
    self.Set(0x07, 0xef)  # tune single pixel dp timing
    self._SwitchBank(1)
    self.Set(0x00, 0xa2)  # bit 4 disables dual pixel mode
    self._SwitchBank(0)

  def IsCablePowered(self):
    """Returns if the cable is powered or not."""
    return bool(self.Get(0xc8) & (1 << 3))

  def IsVideoInputStable(self):
    """Returns whether the video input is stable."""
    input_status = self.Get(self._REG_INPUT_STATUS)
    return bool(input_status & self._BIT_VIDEO_STABLE)

  def _SwitchBank(self, bank):
    """Switch register bank."""
    assert bank == 0 or bank == 1
    self.Set(0x02 + bank, 0x05)

  def ResetVideoLogic(self):
    """Resets the video logic."""
    logging.info('DpRx: reset video...')
    self._SwitchBank(1)
    self.SetMask(self._REG_PLL_RESET, self._BIT_RESET_VIDEO)
    self._SwitchBank(0)
    self.SetMask(self._REG_FUNC_RESET, self._BIT_RESET_VIDEO)

    time.sleep(self._VIDEO_RESET_DELAY)

    self._SwitchBank(1)
    self.ClearMask(self._REG_PLL_RESET, self._BIT_RESET_VIDEO)
    self._SwitchBank(0)
    self.ClearMask(self._REG_FUNC_RESET, self._BIT_RESET_VIDEO)

  def GetResolution(self):
    """Gets the resolution reported by receiver."""
    hactive_h = self.Get(self._REG_HACTIVE_H)
    hactive_l = self.Get(self._REG_HACTIVE_L)
    vactive_h = self.Get(self._REG_VACTIVE_H)
    vactive_l = self.Get(self._REG_VACTIVE_L)
    width = hactive_h << 8 | hactive_l
    height = vactive_h << 8 | vactive_l
    return (width, height)


class HdmiRx(i2c.I2cSlave):
  """A class to control ITE IT6803 HDMI Receiver."""

  SLAVE_ADDRESSES = (0x48, )

  _REG_P0_INTERRUPT = 0x05
  _BIT_P0_RX_CLK_STABLE_CHG = 1 << 2
  _BIT_P0_RX_CLK_ON_CHG = 1 << 1

  _REG_INTERNAL_STATUS = 0x0a
  _BIT_P0_PWR5V_DET = 1 << 0

  _REG_P0_RESET = 0x11
  _BIT_P0_SWRST = 1 << 0

  _REG_P0_HDCP_CONTROL = 0x2d
  _BIT_P0_HDCP_ENABLE = 1 << 2

  _REG_EDID_SLAVE_ADDR = 0x87
  _BIT_ENABLE_EDID_ACCESS = 1

  _REG_IO_MAP = 0x8c
  _BIT_VDIO3_ENABLE = 1 << 3
  _BIT_SP_OUT_MODE = 1 << 0

  _REG_HDCP_STATUS = 0x93
  _BIT_P0_HDCP_ON = 1 << 0

  _REG_EDID_CONFIG = 0xc0
  _BIT_DISABLE_SHADOW_P0 = 1 << 0

  # Registers for checksum
  _REG_P0_B0_SUM = 0xc4  # Port 0, block 0
  _REG_P0_B1_SUM = 0xc5  # Port 0, block 1

  _REG_VIDEO_MODE = 0x99
  _BIT_VIDEO_STABLE = 1 << 3

  _REG_PIXEL_CLOCK_DIV = 0x9A
  _REG_CLK_CONFIG = 0x54
  _MASK_RCLK_SELECT = 0x03

  _REG_HACTIVE_H = 0x9f
  _REG_HACTIVE_L = 0x9e
  _REG_VACTIVE_H = 0xa4
  _REG_VACTIVE_L = 0xa5

  _DELAY_SOFTWARE_RESET = 0.3

  def __init__(self, i2c_bus, slave):
    """Constructs a HdmiRx object.

    Args:
      i2c_bus: The I2cBus object.
      slave: The number of slave address.
    """
    super(HdmiRx, self).__init__(i2c_bus, slave)
    self._pclk_base = None

  def Initialize(self, dual_pixel_mode):
    """Runs the initialization sequence for the chip."""
    logging.info('Initialize HDMI RX chip.')
    if dual_pixel_mode:
      self.SetDualPixelMode()
    else:
      self.SetSinglePixelMode()

    # TODO(waihong): Declare constants for the registers and values.
    self.Set(0x3f, 0x63)  # enable interrupt IO output
    self.Set(0x33, 0x58)  # set driving strength to max (video)
    self.Set(0x33, 0x59)  # set driving strength to max (audio)

    self.SetColorSpaceConvertion()

    # OCLK_MHz = (MHL14|MHL13|MHL12) * 10 / 10^6 = 43.3 (hardware dependent)
    # RCLK_MHz = OCLK_MHz / (1 << (REG054[1:0] + 1))
    # PCLK_MHz = RCLK_MHz * 255 / pclk_div
    #     where pclk_div is from REG09A and depends on input signal
    # Here we pre-calculate _pclk_base = RCLK_MHz * 255 for PCLK_MHz calculation
    # in GetPixelClock().
    rclk_select = self.Get(self._REG_CLK_CONFIG) & self._MASK_RCLK_SELECT
    rclk = 43.3 / (1 << (rclk_select + 1))
    self._pclk_base = rclk * 255

  def SetDualPixelMode(self):
    """Uses dual pixel mode which occupes 2 video paths in FPGA."""
    self.Set(0x02, 0x05)  # bank 0
    self.Set(0x0f, 0x0d)  # enable PHFCLK
    self.Set(0x03, 0x8b)  # enable dual pixel mode
    self.Set(0x08, 0x8c)  # enable QA IO
    self.Set(0x01, 0x8b)  # dual pixel fifo normal operation
    self.Set(0xb1, 0x50)  # tune hdmi dual pixel timing

  def SetSinglePixelMode(self):
    """Uses single pixel mode which occupes 1 video path in FPGA."""
    self.Set(0x07, 0x0d)  # disable PHFCLK
    self.Set(0x80, 0x8b)  # disable dual pixel mode
    self.Set(0x09, 0x8c)  # enable QA IO, single pixel mode 1
    self.Set(0xb3, 0x50)  # tune hdmi single pixel timing

  def SetColorSpaceConvertion(self):
    """Sets the registers for YUV color space convertion."""
    self.Set(0x01, 0x0f)
    self.Set(0x04, 0x70)
    self.Set(0x00, 0x71)
    self.Set(0xa7, 0x72)
    self.Set(0x4f, 0x73)
    self.Set(0x09, 0x74)
    self.Set(0xba, 0x75)
    self.Set(0x3b, 0x76)
    self.Set(0x4b, 0x77)
    self.Set(0x3e, 0x78)
    self.Set(0x4f, 0x79)
    self.Set(0x09, 0x7a)
    self.Set(0x57, 0x7b)
    self.Set(0x0e, 0x7c)
    self.Set(0x02, 0x7d)
    self.Set(0x00, 0x7e)
    self.Set(0x4f, 0x7f)
    self.Set(0x09, 0x80)
    self.Set(0xfe, 0x81)
    self.Set(0x3f, 0x82)
    self.Set(0xe8, 0x83)
    self.Set(0x10, 0x84)
    self.Set(0x00, 0x0f)
    self.Set(0x01, 0x11) # Port 0 all logic reset
    self.Set(0x00, 0x11)

  def IsCablePowered(self):
    """Returns if the cable is powered or not."""
    return bool(self.Get(self._REG_INTERNAL_STATUS) & self._BIT_P0_PWR5V_DET)

  def SetEdidSlave(self, slave):
    """Sets the slave address for the EDID which is stored in the internal RAM.

    Args:
      slave: The slave address for the EDID.
    """
    old_value = self.Get(self._REG_EDID_SLAVE_ADDR)
    # Bit 7:1 is the slave address; bit 0 is to enable EDID access.
    # Keep the original state of the EDID accessibility.
    new_value = (slave << 1) | (old_value & self._BIT_ENABLE_EDID_ACCESS)
    self.Set(new_value, self._REG_EDID_SLAVE_ADDR)

  def EnableEdidAccess(self):
    """Enables the access of the EDID RAM content."""
    self.SetMask(self._REG_EDID_SLAVE_ADDR, self._BIT_ENABLE_EDID_ACCESS)

  def DisableEdidAccess(self):
    """Disables the access of the EDID RAM content."""
    self.ClearMask(self._REG_EDID_SLAVE_ADDR, self._BIT_ENABLE_EDID_ACCESS)

  def IsEdidEnabled(self):
    """Returns True if the receiver is enabled to respond EDID request."""
    return not self.Get(self._REG_EDID_CONFIG) & self._BIT_DISABLE_SHADOW_P0

  def EnableEdid(self):
    """Enables the receiver to monitor DDC and respond EDID."""
    self.ClearMask(self._REG_EDID_CONFIG, self._BIT_DISABLE_SHADOW_P0)

  def DisableEdid(self):
    """Disables the receiver to monitor DDC and respond EDID."""
    self.SetMask(self._REG_EDID_CONFIG, self._BIT_DISABLE_SHADOW_P0)

  def UpdateEdidChecksum(self, block_num, checksum):
    """Updates the checksum of the EDID block.

    Args:
      block_num: 0 for Block 0; 1 for Block 1.
      checksum: The checksum value.
    """
    if block_num == 0:
      self.Set(checksum, self._REG_P0_B0_SUM)
    elif block_num == 1:
      self.Set(checksum, self._REG_P0_B1_SUM)

  def IsVideoInputStable(self):
    """Returns whether the video input is stable."""
    video_mode = self.Get(self._REG_VIDEO_MODE)
    return bool(video_mode & self._BIT_VIDEO_STABLE)

  def GetPixelClock(self):
    """Returns the pixel clock of the input signal in MHz."""
    pclk_div = self.Get(self._REG_PIXEL_CLOCK_DIV)
    return self._pclk_base / pclk_div

  def IsResetNeeded(self):
    """Returns if the RX needs reset by checking the interrupt values."""
    # TODO(waihong): Handle all the interrupts.
    # Now we only handle 2 interrupts, i.e. clock-stable and clock-on changes,
    # by forcing receiver reset.
    interrupt = self.Get(self._REG_P0_INTERRUPT)
    self._ClearInterrupt()
    return bool(interrupt & (self._BIT_P0_RX_CLK_STABLE_CHG |
                             self._BIT_P0_RX_CLK_ON_CHG))

  def _ClearInterrupt(self):
    """Clears the interrupt."""
    interrupt = self.Get(self._REG_P0_INTERRUPT)
    # W1C register
    self.Set(interrupt, self._REG_P0_INTERRUPT)

  def Reset(self):
    """Resets the receiver."""
    logging.info('Reset the receiver.')
    self.SetAndClear(self._REG_P0_RESET, self._BIT_P0_SWRST,
                     self._DELAY_SOFTWARE_RESET)
    # Some interrupts are triggered on reset. Clear them.
    self._ClearInterrupt()

  def GetResolution(self):
    """Gets the resolution reported from receiver."""
    hactive_h = self.Get(self._REG_HACTIVE_H)
    hactive_l = self.Get(self._REG_HACTIVE_L)
    vactive_h = self.Get(self._REG_VACTIVE_H)
    vactive_l = self.Get(self._REG_VACTIVE_L)
    width = (hactive_h & 0x3f) << 8 | hactive_l
    height = (vactive_h & 0xf0) << 4 | vactive_l
    return (width, height)

  def SetContentProtection(self, enable):
    """Sets the content protection state on the receiver.

    Args:
      enable: True to enable; False to disable.
    """
    if enable:
      self.SetMask(self._REG_P0_HDCP_CONTROL, self._BIT_P0_HDCP_ENABLE)
    else:
      self.ClearMask(self._REG_P0_HDCP_CONTROL, self._BIT_P0_HDCP_ENABLE)

  def IsContentProtectionEnabled(self):
    """Returns True if the content protection is enabled on the receiver.

    Returns:
      True if the content protection is enabled; otherwise, False.
    """
    return bool(self.Get(self._REG_P0_HDCP_CONTROL) & self._BIT_P0_HDCP_ENABLE)

  def IsVideoInputEncrypted(self):
    """Returns True if the video input is encrypted.

    Returns:
      True if the video input is content-protected; otherwise, False.
    """
    return self.IsContentProtectionEnabled() and bool(
        self.Get(self._REG_HDCP_STATUS) & self._BIT_P0_HDCP_ON)


class VgaRx(i2c.I2cSlave):
  """A class to control ITE CAT9883C CRT Receiver."""

  SLAVE_ADDRESSES = (0x4c, )

  _REG_SYNC_DETECT = 0x14
  _BIT_HSYNC_DETECTED = 1 << 7
  _BIT_TV_MODE = 1 << 6
  _BIT_VSYNC_DETECTED = 1 << 4
  _BITS_SYNC_MASK = _BIT_HSYNC_DETECTED | _BIT_VSYNC_DETECTED

  _REG_HSYNC_COUNTER_REFRESH = 0x8f
  _BITS_HSYNC_COUNTER_REFRESH = 0x68

  _REG_HSYNC_COUNTER_H = 0xac
  _REG_HSYNC_COUNTER_L = 0xab

  _VGA_MODES = {
      'PC_576px50': [0x35, 0xf0, 0x68, 0x80, 0x20, 0x10, 0xf0, 0x80,
                     0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                     0x19, 0x00, 0x00],
      'PC_480px60': [0x35, 0x90, 0x28, 0x38, 0x20, 0x10, 0xf0, 0x80,
                     0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                     0x19, 0x00, 0x00],
      'PC_720px60': [0x67, 0x10, 0xa0, 0x38, 0x40, 0x40, 0xf0, 0x80,
                     0x80, 0x80, 0x80, 0x80, 0x80, 0x44, 0x6f, 0xb8,
                     0x19, 0x00, 0x00],
      'PC_1080ix60': [0x89, 0x70, 0xa0, 0x38, 0x40, 0x40, 0xf0, 0x80,
                      0x80, 0x80, 0x80, 0x80, 0x80, 0x44, 0x6f, 0xb8,
                      0x19, 0x00, 0x00],
      'PC_640x480x60': [0x31, 0xf0, 0x30, 0x88, 0x10, 0x10, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_640x480x72': [0x33, 0xf0, 0x70, 0x88, 0x10, 0x10, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_640x480x75': [0x34, 0x70, 0x70, 0x88, 0x10, 0x10, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_640x480x85': [0x33, 0xf0, 0x70, 0x88, 0x10, 0x10, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_800x600x56': [0x3f, 0xf0, 0x70, 0x38, 0x10, 0x20, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_800x600x60': [0x41, 0xf0, 0x60, 0x38, 0x10, 0x20, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_800x600x72': [0x40, 0xf0, 0x70, 0x38, 0x10, 0x20, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_800x600x75': [0x41, 0xf0, 0x70, 0x38, 0x10, 0x20, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_800x600x85': [0x41, 0x70, 0x70, 0x38, 0x10, 0x20, 0xf0, 0x80,
                        0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                        0x19, 0x00, 0x00],
      'PC_1024x768x60': [0x53, 0xf0, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1024x768x70': [0x52, 0xf0, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1024x768x75': [0x51, 0xf0, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1024x768x80': [0x53, 0x70, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1024x768x85': [0x55, 0xf0, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1280x1024x60': [0x69, 0x70, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1280x1024x75': [0x69, 0x70, 0xf0, 0x38, 0x10, 0x40, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1280x1024x85': [0x6b, 0xf0, 0xa8, 0x38, 0x10, 0x40, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1600x1200x60': [0x86, 0xf0, 0xe8, 0x40, 0x10, 0x80, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x42, 0x6e, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1360x768x60': [0x6f, 0xf0, 0x90, 0x10, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1680x1050x60': [0x8b, 0xf0, 0xf0, 0xa8, 0x40, 0x40, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1440x900x60': [0x76, 0xf0, 0xa8, 0x00, 0x20, 0x20, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1280x800x60': [0x68, 0xf0, 0xa8, 0x00, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1280x960x60': [0x70, 0x70, 0xb0, 0x00, 0x10, 0x40, 0xf0, 0x80,
                         0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                         0x19, 0x00, 0x00],
      'PC_1920x1080x60': [0x89, 0x70, 0xf0, 0x80, 0x30, 0x20, 0xf0, 0x80,
                          0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                          0x19, 0x00, 0x00],
      'PC_1920x1200xReduce': [0x81, 0xf0, 0xf0, 0x80, 0x06, 0x10, 0xf0, 0x80,
                              0x80, 0x80, 0x80, 0x80, 0x80, 0x40, 0x6f, 0xb8,
                              0x19, 0x00, 0x00]
  }

  def Initialize(self, unused_dual_pixel_mode):
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

  def _IsTvMode(self):
    """Returns True if the current mode is a TV mode."""
    return bool(self.Get(self._REG_SYNC_DETECT) & self._BIT_TV_MODE)

  def DetectMode(self):
    """Returns the current VGA mode."""
    self.Set(self._BITS_HSYNC_COUNTER_REFRESH, self._REG_HSYNC_COUNTER_REFRESH)
    hsync_counter = (((self.Get(self._REG_HSYNC_COUNTER_H) << 4) & 0xf00) +
                     self.Get(self._REG_HSYNC_COUNTER_L))
    if not self._IsTvMode():
      # For simplification, this detection logic only works on 60Hz reflesh
      # rate.
      if hsync_counter >= 0x1a0 and hsync_counter < 0x240:
        # Original driver is returning mode PC_640x480x60. But it does not
        # work on the resolution 720x480. Changing to PC_480px60 works better.
        mode = 'PC_480px60'
      elif hsync_counter >= 0x240 and hsync_counter < 0x2d0:
        mode = 'PC_800x600x60'
      elif hsync_counter >= 0x2d0 and hsync_counter < 0x310:
        mode = 'PC_720px60'
      elif hsync_counter >= 0x310 and hsync_counter < 0x31d:
        mode = 'PC_1360x768x60'
      elif hsync_counter >= 0x31e and hsync_counter < 0x331:
        mode = 'PC_1024x768x60'
      elif hsync_counter >= 0x332 and hsync_counter < 0x352:
        mode = 'PC_1280x800x60'
      elif hsync_counter >= 0x3a0 and hsync_counter < 0x3a7:
        mode = 'PC_1440x900x60'
      elif hsync_counter >= 0x3c0 and hsync_counter < 0x400:
        mode = 'PC_1280x960x60'
      elif hsync_counter >= 0x420 and hsync_counter < 0x437:
        mode = 'PC_1280x1024x60'
      elif hsync_counter >= 0x440 and hsync_counter < 0x459:
        mode = 'PC_1680x1050x60'
      elif hsync_counter >= 0x459 and hsync_counter < 0x490:
        mode = 'PC_1920x1080x60'
      elif hsync_counter >= 0x4d0 and hsync_counter < 0x4d7:
        mode = 'PC_1920x1200xReduce'
      elif hsync_counter >= 0x4da and hsync_counter < 0x510:
        mode = 'PC_1600x1200x60'
      else:
        raise RxError('Failed to detect the VGA mode, #hsync: %#x' %
                      hsync_counter)
    else:
      raise RxError('Detected TV mode which is not supported yet.')

    logging.info('Detected VGA mode: %s (#hsync: %#x)', mode, hsync_counter)
    return mode

  def SetMode(self, mode):
    """Sets the VGA mode.

    Args:
      mode: A string of the mode name.
    """
    if mode not in self._VGA_MODES:
      raise RxError('Set to an unsupported mode: %s' % mode)

    setting = self._VGA_MODES[mode]
    for index, value in enumerate(setting):
      reg = index + 1
      self.Set(value, reg)

  def IsSyncDetected(self):
    """Returns True if Hsync or Vsync is detected."""
    return bool(self.Get(self._REG_SYNC_DETECT) & self._BITS_SYNC_MASK)
