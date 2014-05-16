# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Memory module for accessing the memory for IO.

This module uses C library to direct access the memory.

Usage:
  import mem_native
  value = mem_native.Memory.Read(address)
"""

import ctypes
import time


class _Memory(object):
  """A class to abstract the memory access for IO."""

  # Address space for memory-mapped I/O.
  _MMAP_START = 0xff210000
  _MMAP_SIZE = 0x10000
  # mmap end address (exclusive)
  _MMAP_END = _MMAP_START + _MMAP_SIZE

  _REG_SET_DELAY = 0.001

  def __init__(self):
    """Constructs a _Memory object.

    Raises:
      IOError if failed to open /dev/mem.
    """
    libc = ctypes.cdll.LoadLibrary('libc.so.6')
    O_RDWR = 00000002
    O_SYNC = 04000000 | 00010000
    fd = libc.open('/dev/mem', O_RDWR | O_SYNC)
    if fd == -1:
      raise IOError('Failed to open /dev/mem')
    PROT_READ = 0x1
    PROT_WRITE = 0x2
    MAP_SHARED = 0x01
    self._memory = libc.mmap(0, self._MMAP_SIZE, PROT_READ | PROT_WRITE,
                             MAP_SHARED, fd, self._MMAP_START)
    if self._memory == -1:
      raise IOError('Failed to call mmap()')

  def _GetLocalAddress(self, address):
    """Gets the local mmapped address for a given memory address.

    Args:
      address: The memory address.

    Returns:
      A local mmapped address.
    """
    assert self._memory != -1
    assert self._MMAP_START <= address < self._MMAP_END
    return self._memory + (address & 0xffff)

  def Read(self, address):
    """Reads the 32-bit integer from the given memory address.

    Args:
      address: The memory address.

    Returns:
      An integer.
    """
    local_addr = self._GetLocalAddress(address)
    return ctypes.c_uint.from_address(local_addr).value  # pylint: disable=E1101

  def Write(self, address, data):
    """Writes the given 32-bit integer to the given memory address.

    Args:
      address: The memory address.
      data: The 32-bit integer to write.
    """
    local_addr = self._GetLocalAddress(address)
    ctypes.c_uint.from_address(local_addr).value = data  # pylint: disable=E1101

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

  def SetAndClearMask(self, address, mask, delay_secs=_REG_SET_DELAY):
    """Sets and then clears the mask on the given memory address.

    It is a blocking call for at least delay_secs seconds.

    Args:
      address: The memory address.
      mask: The bitwise mask.
      delay_secs: The time between set and clear. Default: _REG_SET_DELAY
    """
    self.SetMask(address, mask)
    time.sleep(delay_secs)
    self.ClearMask(address, mask)


# Singleton
Memory = _Memory()
