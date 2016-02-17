# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""LCM display module controller.

The NT7534 (128x64 digital LCM) on SocKit is controlled by HPS SPI interface
from SPIM1.

Before using, please make sure the corresponent GPIO pins are enabled in SocKit
IO pinmux setting. Such as LCM_RST_n(GPIO48), LCM_D_C(GPIO62), and
LCM_BK(GPIO40).
"""

import logging
import os
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import lcm_canvas
from chameleond.utils import lcm_font
from chameleond.utils import mem
from chameleond.utils import spim


class LcmDisplayError(Exception):
  """Exception raise when any unexpected behavior happened on LCM display."""
  pass


class LcmDisplay(object):
  """A Class for LCM display controller."""

  _GPIO1_ADDRESS = 0xff709000
  _GPIO2_ADDRESS = 0xff70a000

  _DR_OFFSET = 0x00
  _DDR_OFFSET = 0x04

  # Locate in GPIO1 bank
  _RST_N_BITMASK = 0x00080000
  _BK_BITMASK = 0x00000800
  # Locate in GPIO2 bank
  _D_C_BITMASK = 0x00000010

  _WIDTH = 128
  _HEIGHT = 64

  _RESET_PULSE = 1.0 / 16

  _BOOTSCREEN_BITMAP = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                    'lcm_chameleon.bitmap')

  # LCM instructions
  _INST_SET_DISPLAY_ADDR = 0xae
  _INST_SET_LINE_ADDR = 0x40
  _INST_SET_PAGE_ADDR = 0xb0
  _INST_SET_COL_L_ADDR = 0x00
  _INST_SET_COL_H_ADDR = 0x10
  _INST_SET_COM_SEL_ADDR = 0xc0
  _INST_SET_POWER_CON_ADDR = 0x28

  def __init__(self):
    """Constructs a LCM display object."""
    self._memory = mem.MemoryForHPS
    self._data_in = False
    self.HardwareReset()
    self._spim = spim.Spim(1, tx_only=True)
    # LcmCanvas is an intermediate bitmap buffer of LcmDisplay, modify LcmCanvas
    # will not change the display screen until you call RefreshDisplay().
    self._canvas = lcm_canvas.LcmCanvas(
        self._HEIGHT, self._WIDTH, self._BOOTSCREEN_BITMAP)
    self.SetBacklight(True)
    self.Initialize()

  def HardwareReset(self):
    """Resets LCM display hardware module."""
    logging.info('HW Reset LCM display...')
    # Trigger LCM reset signal
    self._memory.SetMask(self._GPIO1_ADDRESS + self._DDR_OFFSET,
                         self._RST_N_BITMASK)
    self._memory.ClearAndSetMask(self._GPIO1_ADDRESS + self._DR_OFFSET,
                                 self._RST_N_BITMASK,
                                 self._RESET_PULSE)
    time.sleep(self._RESET_PULSE)
    # Turn on LCM backlight
    self.SetBacklight(False)
    # Set LCM-A0 (data in) pin as default
    self._SetDataIn(is_data=False)
    time.sleep(self._RESET_PULSE)

  def Initialize(self):
    """Initiates LCM display settings."""
    logging.info('Initializing LCM display...')
    self._SetCommonOutputModeSelect(is_normal=True)
    self._SetPowerControl(0x7)
    self._SetStartLineAddress(0)
    self._SetPageAddress(0)
    self._SetColumnAddress(0)
    self._SetDisplay(enable=True)
    # Show up boot screen
    self.RefreshDisplay()
    logging.info('LCM display Init Done...')

  def SetBacklight(self, enable=True):
    """Sets backlight on or off.

    Args:
      enable: True for setting backlight on; otherwise False.
    """
    self._memory.SetMask(self._GPIO1_ADDRESS + self._DDR_OFFSET,
                         self._BK_BITMASK)
    if enable:
      self._memory.SetMask(self._GPIO1_ADDRESS + self._DR_OFFSET,
                           self._BK_BITMASK)
    else:
      self._memory.ClearMask(self._GPIO1_ADDRESS + self._DR_OFFSET,
                             self._BK_BITMASK)

  def CanvasClear(self):
    """Clears the canvas."""
    self._canvas.Clear()

  def CanvasPrintLine(self, string, line, highlight=False, underline=False):
    """Prints string on a line on the canvas.

    String will be cropped to fit the maximum length of display line.

    Args:
      string: The input string.
      line: The line index.
      highlight: Whether line is shown with highlight.
      underline: Whether line is shown with underline.
    """
    for i in xrange(self._canvas.max_char_length):
      if i < len(string):
        self._canvas.DrawChar(
            string[i], line, i * lcm_font.FONT_WIDTH, highlight, underline)
      else:
        self._canvas.DrawChar(
            ' ', line, i * lcm_font.FONT_WIDTH, False, False)

  def CanvasPrintMenuItem(self, string, is_leaf, line):
    """Prints menu item on a line on the canvas.

    Args:
      string: The input string of menu item.
      is_leaf: Whether the item is a leaf node of menu.
      line: The line index.
    """
    # The format of menu item: first 2 spaces for the room of putting cursor. If
    # item is not a leaf node, print a right arrow in the tail.
    # Ex: string = 'Video' -> format_string = '  Video        >'
    format_string = ' ' * 2 + string + ' ' * (self._canvas.max_char_length - 2)
    if not is_leaf:
      format_string = (format_string[:self._canvas.max_char_length - 2] +
                       lcm_font.ARROW_RIGHT)
    self.CanvasPrintLine(format_string, line)

  def CanvasPrintCursor(self, line, column):
    """Prints cursor on the canvas.

    Args:
      line: The line index.
      column: The column index.
    """
    for i in xrange(len(lcm_font.CURSOR)):
      char = lcm_font.CURSOR[i]
      self._canvas.DrawChar(
          char, line, column + i * lcm_font.FONT_WIDTH, False, False)

  def GetMaxCharLines(self):
    """Get the maximum lines for printing characters."""
    return self._canvas.max_char_lines

  def GetMaxCharLength(self):
    """Get the maximum lengths of printing characters in a line."""
    return self._canvas.max_char_length

  def RefreshDisplay(self):
    """Refreshes and outputs canvas image to LCM display.

    To be noted, calling canvas-related functions will only draw on the canvas
    object, after then you need to call RefreshDisplay to output them on LCM
    display.
    """
    bitmap = self._canvas.bitmap
    for page in xrange(self._canvas.pages):
      self._SetPageAddress(page)
      self._SetColumnAddress(0)
      for data in iter(bitmap[page]):
        self._WriteData(data)

  def _SetDataIn(self, is_data=True):
    """Sets LCM_A0 (data in) pin to indicate input data type.

    Args:
      is_data: True for data input; False for command input.
    """
    self._memory.SetMask(self._GPIO2_ADDRESS + self._DDR_OFFSET,
                         self._D_C_BITMASK)
    if is_data:
      self._memory.SetMask(self._GPIO2_ADDRESS + self._DR_OFFSET,
                           self._D_C_BITMASK)
    else:  # is command
      self._memory.ClearMask(self._GPIO2_ADDRESS + self._DR_OFFSET,
                             self._D_C_BITMASK)
    # Save the status of LCM-A0 (data in) to reduce redundant GPIO settings.
    self._data_in = is_data

  def _SetDisplay(self, enable):
    """Sets display on/off by SPI instruction command.

    Args:
      enable: True for display on; otherwise False.
    """
    command = self._INST_SET_DISPLAY_ADDR | enable
    self._WriteCommand(command)

  def _SetStartLineAddress(self, line):
    """Sets start line address by SPI instrucion command.

    Args:
      line: The start line index.
    """
    command = self._INST_SET_LINE_ADDR | (line & 0x3f)
    self._WriteCommand(command)

  def _SetPageAddress(self, page):
    """Sets page address for data by SPI instrucion command.

    Args:
      page: The start page index.
    """
    command = self._INST_SET_PAGE_ADDR | (page & 0x0f)
    self._WriteCommand(command)

  def _SetColumnAddress(self, column):
    """Sets column address for data by SPI instrucion command.

    Args:
      column: The start column index.
    """
    command = self._INST_SET_COL_L_ADDR | (column & 0x0f)  # lower 4-bit
    self._WriteCommand(command)
    command = self._INST_SET_COL_H_ADDR | ((column >> 4) & 0x0f)  # upper 4-bit
    self._WriteCommand(command)

  def _SetCommonOutputModeSelect(self, is_normal):
    """Sets LCM scan direction by SPI instrucion command.

    Args:
      is_normal: True for pixel data arranges from top-left to bottom-right;
          False for the reversed direction.
    """
    command = self._INST_SET_COM_SEL_ADDR | (is_normal << 3)
    self._WriteCommand(command)

  def _SetPowerControl(self, power):
    """Sets power control mask by SPI instruction command.

    Args:
      power: The 3-bit long power mask.
    """
    command = self._INST_SET_POWER_CON_ADDR | (power & 0x07)
    self._WriteCommand(command)

  def _WriteCommand(self, command):
    """Writes a command byte through SPI interface.

    Args:
      command: The command byte pattern.
    """
    self._WriteData(command, is_data=False)

  def _WriteData(self, data, is_data=True):
    """Writes a data byte through SPI interface.

    Args:
      data: The data byte pattern.
      is_data: True for writing data; False for writing command.
    """
    if isinstance(data, str):
      data = ord(data)
    try:
      if self._data_in != is_data:
        self._SetDataIn(is_data)
      self._spim.WriteData(data)
    except Exception as e:
      raise LcmDisplayError('Write %s 0x%2x failed: %s' %
                            ('data' if is_data else 'command', data, e))
