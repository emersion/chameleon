# -*- coding: utf-8 -*-
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Memory module for accessing the memory for IO.

This module uses C library to direct access the memory.

Usage:
  import mem
  # Control IO registers of controllers.
  memory = mem.MemoryForController
  value = memory.Read(address)
"""

import ctypes
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils.common import lazy


class _Memory(object):
  """A class to abstract the memory access for IO."""

  _REG_SET_DELAY = 0.001

  def __init__(self, start_address, size):
    """Constructs a _Memory object.

    Args:
      start_address: the start address of mmap.
      size: the size in bytes of mmap.

    Raises:
      IOError if failed to open /dev/mem.
    """
    self._mmap_start = start_address
    self._mmap_size = size
    # mmap end address (exclusive)
    self._mmap_end = self._mmap_start + self._mmap_size

    libc = ctypes.cdll.LoadLibrary('libc.so.6')
    O_RDWR = 00000002
    O_SYNC = 04000000 | 00010000
    fd = libc.open('/dev/mem', O_RDWR | O_SYNC)
    if fd == -1:
      raise IOError('Failed to open /dev/mem')
    PROT_READ = 0x1
    PROT_WRITE = 0x2
    MAP_SHARED = 0x01
    self._memory = libc.mmap(0, self._mmap_size, PROT_READ | PROT_WRITE,
                             MAP_SHARED, fd, self._mmap_start)
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
    assert self._mmap_start <= address < self._mmap_end
    return self._memory + (address - self._mmap_start)

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

  def ClearAndSetMask(self, address, mask, delay_secs=_REG_SET_DELAY):
    """Clears and then sets the mask on the given memory address.

    It is a blocking call for at least delay_secs seconds.

    Args:
      address: The memory address.
      mask: The bitwise mask.
      delay_secs: The time between clear and set. Default: _REG_SET_DELAY
    """
    self.ClearMask(address, mask)
    time.sleep(delay_secs)
    self.SetMask(address, mask)

  def Fill(self, address, data):
    """Fills memory with data.

    Args:
      address: The memory address.
      data: The data to be filled to memory starting from that address.
    """
    local_addr = self._GetLocalAddress(address)
    end_addr = address + len(data)
    if end_addr >= self._mmap_end:
      raise IOError(
          'Address %r exceeds end of mmap %r' % (end_addr, self._mmap_end))
    ctypes.memmove(local_addr, data, len(data))


# Address space for memory-mapped I/O for controller.
_MMAP_START_CONTROLLER = 0xff210000
_MMAP_SIZE_CONTROLLER = 0x10000

_MMAP_START_DUMPER = 0xc0000000
_MMAP_SIZE_DUMPER = 0x3c000000

_MMAP_START_HPS = 0xfc000000
_MMAP_SIZE_HPS = 0x4000000


# Lazy instantiation of the memory singletons since they are not supported
# on a platform such as chromeos.
MemoryForController = lazy(_Memory)(
    _MMAP_START_CONTROLLER, _MMAP_SIZE_CONTROLLER)
MemoryForDumper = lazy(_Memory)(_MMAP_START_DUMPER, _MMAP_SIZE_DUMPER)
MemoryForHPS = lazy(_Memory)(_MMAP_START_HPS, _MMAP_SIZE_HPS)
