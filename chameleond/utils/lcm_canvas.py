# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The canvas object of LCM display.

It is the temporary memory for storing the bitmap of black-and-white LCM
display, by the format of 2-D byte array.

Based on NT7534 SPI data write protocol, display area is divided into pages per
8 pixels in height. Display data is transfered by unit of a byte (8-pixel),
and each represents a 8(height)x1(width) pixel values in the same page.

For example, let's say a pixel[64][128] array. It will have 64/8=8 pages in
total. For each page it has 128 bytes data, each byte counts as a column. In
canvas, the whole bitmap will be stored in byte[8][128] array.
"""

import array

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import lcm_font


class LcmCanvasError(Exception):
  """Exception raise when any unexpected behavior happened on LCM canvas."""
  pass


class LcmCanvas(object):
  """A Class for LCM canvas."""

  _PAGE_HEIGHT = 8

  def __init__(self, height, width, boot_screen=None):
    """Constructs a LcmCanvas object.

    Args:
      height: The display height in pixels.
      width: The display width in pixels.
      boot_screen: The bitmap file for boot screen; None for blank screen only.
    """
    if height % self._PAGE_HEIGHT != 0:
      raise LcmCanvasError('Canvas height must be the multiple of %d...' %
                           self._PAGE_HEIGHT)
    self._height = height
    # Total pages of LcdCanvas.
    self.pages = height / self._PAGE_HEIGHT
    # Total columns of LcdCanvas.
    self.columns = width
    # The maximum lengths of printing characters in a line of LcdCanvas.
    self.max_char_length = self.columns / lcm_font.FONT_WIDTH
    # The maximum lines for printing characters of LcdCanvas.
    self.max_char_lines = height / lcm_font.FONT_HEIGHT

    # Create an 2-D byte array of bitmap.
    self.bitmap = []
    for _ in xrange(self.pages):
      self.bitmap.append(array.array('c', [chr(0x00)] * self.columns))
    if boot_screen:
      self.DrawFromFile(boot_screen)

  def Clear(self, byte=0x00):
    """Clears the bitmap with default byte.

    Args:
      byte: The defaulkt byte.
    """
    for page in xrange(self.pages):
      for column in xrange(self.columns):
        self.SetByte(byte, page, column)

  def DrawChar(self, char, line, column, highlight, underline):
    """Draws a character to bitmap.

    Args:
      char: The character.
      line: The line number of location.
      column: The column number of location.
      highlight: Whether character is highlighted.
      underline: Whether character is underlined.
    """
    page = line * lcm_font.FONT_PAGES
    if highlight:
      font = lcm_font.GetHighlightFont(char)
    elif underline:
      font = lcm_font.GetUnderlineFont(char)
    else:
      font = lcm_font.GetFont(char)
    for y in xrange(lcm_font.FONT_HEIGHT / self._PAGE_HEIGHT):
      for x in xrange(lcm_font.FONT_WIDTH):
        font_index = y * lcm_font.FONT_WIDTH + x
        self.SetByte(font[font_index], page + y, column + x)

  def DrawFromFile(self, bitmap_file):
    """Draws the bitmap from given bitmap file.

    Args:
      bitmap_file: The bitmap file.
    """
    with open(bitmap_file) as f:
      bitmap_in = f.read()
    for page in xrange(self.pages):
      for column in xrange(self.columns):
        self.SetByte(ord(bitmap_in[page * self.columns + column]), page, column)

  def SetByte(self, byte, page, column):
    """Sets a byte to bitmap.

    Args:
      byte: The byte.
      page: The page number of location.
      column: The column number of location.
    """
    try:
      self.bitmap[page][column] = chr(byte)
    except IndexError:
      raise LcmCanvasError('Request index out of range: page=%d column=%d' %
                           (page, column))

  def SetPixel(self, pixel, y, x):
    """Sets a pixel to bitmap.

    Args:
      pixel: 1 for filled pixel; 0 for blank pixel.
      y: The y-direction location in pixels.
      x: The x-direction location in pixels.
    """
    page = y / self._PAGE_HEIGHT
    bitmask = 0x1 << (y % self._PAGE_HEIGHT)
    try:
      byte = ord(self.bitmap[page][x])
      if pixel:
        self.bitmap[page][x] = chr(byte | bitmask)
      else:
        self.bitmap[page][x] = chr(byte & ~bitmask)
    except IndexError:
      raise LcmCanvasError('Request index out of range: page=%d column=%d' %
                           (page, x))
