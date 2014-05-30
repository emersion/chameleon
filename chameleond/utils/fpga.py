# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""FPGA module for controlling the functions of FPGA.

Using the FpgaController can control all its subsystems.
Usage:
  import fpga
  fpga_ctrl = fpga.FpgaController()

  # Control the HPD
  fpga_ctrl.hpd.Plug(input_id)
  fpga_ctrl.hpd.Unplug(input_id)

  # Select the video pass-through.
  fpga_ctrl.vpass.Select(input_id)
"""

import struct

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import ids
from chameleond.utils import mem_native as mem


class FpgaController(object):
  """A class to abstract the all behaviors of FPGA.

  An instance of this class also includes the instances of its subsystems.
  The caller can directly access them via the member variables.
  """

  def __init__(self):
    """Constructs a FpgaController object."""
    self.hpd = HpdController()
    self.vpass = VideoPasser()
    self.vdump0 = VideoDumper(0)
    self.vdump1 = VideoDumper(1)
    self.hdmi_edid = EdidController(EdidController.HDMI_BASE)
    self.vga_edid = EdidController(EdidController.VGA_BASE)


class HpdController(object):
  """A class to abstract the behavior of HPD."""

  _HPD_BASE = 0xff21a000
  _HPD_OFFSETS = {
    ids.DP1: 0x4,
    ids.DP2: 0x8,
    ids.HDMI: 0xc
  }
  _BIT_UNPLUG = 0
  _BIT_PLUG = 1

  def __init__(self):
    """Constructs a HpdController object."""
    self._memory = mem.Memory

  def IsPlugged(self, input_id):
    """Returns if the HPD line is plugged.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.

    Returns:
      True if the HPD line is plugged; otherwise, False.
    """
    return (self._memory.Read(self._HPD_BASE + self._HPD_OFFSETS[input_id]) ==
            self._BIT_PLUG)

  def Plug(self, input_id):
    """Asserts HPD line to high, emulating plug.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    self._memory.Write(self._HPD_BASE + self._HPD_OFFSETS[input_id],
                       self._BIT_PLUG)

  def Unplug(self, input_id):
    """Deasserts HPD line to low, emulating unplug.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    self._memory.Write(self._HPD_BASE + self._HPD_OFFSETS[input_id],
                       self._BIT_UNPLUG)


class VideoPasser(object):
  """A class to abstract the behavior of video pass-through.

  The pass-through video is output to the VGA output on the main board.
  """

  _REG_CTRL = 0xff21d004

  _BIT_DATA_A = 0
  _BIT_DATA_B = 1 << 0
  _BIT_CLK_A = 0
  _BIT_CLK_B = 1 << 1

  _VALUES_CTRL = {
    ids.DP1: _BIT_CLK_A | _BIT_DATA_A,
    ids.DP2: _BIT_CLK_B | _BIT_DATA_B,
    ids.HDMI: _BIT_CLK_B | _BIT_DATA_A,
    ids.VGA: _BIT_CLK_A | _BIT_DATA_A
  }

  def __init__(self):
    """Constructs a VideoPasser object."""
    self._memory = mem.Memory

  def Select(self, input_id):
    """Selects the given input for pass-through.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    self._memory.Write(self._REG_CTRL, self._VALUES_CTRL[input_id])


class VideoDumper(object):
  """A class to control video dumper."""

  _REGS_BASE = (0xff210000,  # Dumper 0
                0xff211000)  # Dumper 1
  # Control register
  _REG_CTRL = 0x0
  _BIT_CLK_NORMAL = 0
  _BIT_CLK_ALT = 1 << 1
  _BIT_STOP = 0
  _BIT_RUN = 1 << 2

  # Register which stores the memory address to dump
  _REG_ADDR = 0x4
  # Registers to get the width and height
  _REG_WIDTH = 0x10
  _REG_HEIGHT = 0x14

  _VALUES_CTRL = {
    ids.DP1: (_BIT_RUN | _BIT_CLK_NORMAL,  # Dumper 0
              _BIT_RUN | _BIT_CLK_ALT),  # Dumper 1
    ids.DP2: (_BIT_RUN | _BIT_CLK_ALT,
              _BIT_RUN | _BIT_CLK_NORMAL),
    ids.HDMI: (_BIT_RUN | _BIT_CLK_ALT,
               _BIT_RUN | _BIT_CLK_NORMAL),
    ids.VGA: (_BIT_RUN | _BIT_CLK_NORMAL,
              _BIT_STOP)
  }

  _DUMP_ADDRESSES = (0xc0000000,  # Dumper 0
                     0xd0000000)  # Dumper 1

  _PIXELDUMP_ARGS = {
    ids.DP1: ['-a', _DUMP_ADDRESSES[0], '-b', _DUMP_ADDRESSES[1]],
    ids.DP2: ['-a', _DUMP_ADDRESSES[1], '-b', _DUMP_ADDRESSES[0]],
    ids.HDMI: ['-a', _DUMP_ADDRESSES[1], '-b', _DUMP_ADDRESSES[0]],
    ids.VGA: ['-a', _DUMP_ADDRESSES[0]],
  }

  def __init__(self, index):
    """Constructs a VideoDumper object.

    Args:
      index: 0 for Dumper A and 1 for Dumper B.
    """
    self._memory = mem.Memory
    self._index = index

  def Select(self, input_id):
    """Selects the given input for dumping.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
    """
    # Set the memory address for dump.
    self._memory.Write(self._REGS_BASE[self._index] + self._REG_ADDR,
                       self._DUMP_ADDRESSES[self._index])
    # Use the proper CLK and run.
    self._memory.Write(self._REGS_BASE[self._index] + self._REG_CTRL,
                       self._VALUES_CTRL[input_id][self._index])

  def GetWidth(self):
    """Gets the width of the video path."""
    return self._memory.Read(self._REGS_BASE[self._index] + self._REG_WIDTH)

  def GetHeight(self):
    """Gets the height of the video path."""
    return self._memory.Read(self._REGS_BASE[self._index] + self._REG_HEIGHT)

  @classmethod
  def GetPixelDumpArgs(cls, input_id):
    """Gets the arguments of pixeldump tool which selects the proper buffers.

    Args:
      input_id: 0 for DP1, 1 for DP2, 2 for HDMI, and 3 for VGA.
    """
    return cls._PIXELDUMP_ARGS[input_id]


class EdidController(object):
  """A class to abstract the behavior of the EDID controller."""

  HDMI_BASE = 0xff217000
  VGA_BASE = 0xff219000
  _REG_CTRL = 0
  _BIT_RESET = 0
  _BIT_OPERATE = 1
  _EDID_MEM = 0x100

  _EDID_SIZE = 256

  def __init__(self, edid_base):
    """Constructs a EdidController object.

    Args:
      edid_base: The base of the memory address which stores the EDID.
    """
    self._memory = mem.Memory
    self._edid_base = edid_base

  def WriteEdid(self, data):
    """Writes the EDID content.

    Args:
      data: The EDID control to write.
    """
    for offset in range(0, len(data), 4):
      value = struct.unpack('>I', data[offset:offset+4])[0]
      self._memory.Write(self._edid_base + self._EDID_MEM + offset, value)
    self._memory.Write(self._edid_base + self._REG_CTRL, self._BIT_OPERATE)

  def ReadEdid(self):
    """Reads the EDID content.

    Returns:
      A byte array of EDID data.
    """
    all_value = ''
    for offset in range(0, self._EDID_SIZE, 4):
      value = self._memory.Read(self._edid_base + self._EDID_MEM + offset)
      all_value += struct.pack('>I', value)
    return all_value
