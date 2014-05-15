# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Mem module for accessing the memory for IO."""

import re
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import system_tools


class OutputFormatError(Exception):
  """Exception raised when output messages of the Mem tool did not match."""
  pass


class _Memory(object):
  """A class to abstract the memory access for IO."""

  _REG_SET_DELAY = 0.001

  def __init__(self):
    """Constructs a _Memory object."""
    self._memtool_pattern = re.compile(r'0x[0-9A-F]{8}:  ([0-9A-F]{8})')
    self._tools = system_tools.SystemTools

  def Read(self, address):
    """Reads the 32-bit integer from the given memory address.

    Args:
      address: The memory address.

    Returns:
      An integer.
    """
    message = self._tools.Output('memtool', '-32', '%#x' % address, '1')
    matches = self._memtool_pattern.search(message)
    if matches:
      return int(matches.group(1), 16)
    else:
      raise OutputFormatError('The output format of memtool is not matched.')

  def Write(self, address, data):
    """Writes the given 32-bit integer to the given memory address.

    Args:
      address: The memory address.
      data: The 32-bit integer to write.
    """
    self._tools.Call('memtool', '-32', '%#x=%#x' % (address, data))

  def SetMask(self, address, mask):
    """Sets the mask on the given memory address.

    Args:
      address: The memory address.
      mask: The bitwise mask.
    """
    self.Write(address, self.Read(address) | mask)

  def ClearMask(self, address, mask):
    """Clears the mask on the given memory address.

    Args:
      address: The memory address.
      mask: The bitwise mask.
    """
    self.Write(address, self.Read(address) & ~mask)

  def SetAndClearMask(self, address, mask, delay=None):
    """Sets and then clears the mask on the given memory address.

    Args:
      address: The memory address.
      mask: The bitwise mask.
      delay: The time between set and clear. Default: self._REG_SET_DELAY
    """
    self.SetMask(address, mask)
    if delay is None:
      delay = self._REG_SET_DELAY
    time.sleep(delay)
    self.ClearMask(address, mask)


# Singleton
Memory = _Memory()
