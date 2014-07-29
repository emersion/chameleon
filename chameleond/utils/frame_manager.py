# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Frame manager module which manages the frame dump and monitor logic."""

import logging

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common


class FrameManager(object):
  """An abstraction of the frame management.

  It acts as an intermediate layer between an InputFlow and VideoDumpers.
  It simplifies the logic of handling dual-pixel-mode and single-pixel-mode.
  """

  # Delay in second to check the frame count, using 120-fps.
  _DELAY_VIDEO_DUMP_PROBE = 1.0 / 120

  def __init__(self, input_id, vdumps):
    """Constructs a FrameManager object.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
      vdumps: A list of VideoDumper objects to manage, e.g., a single
              VideoDumper on single-pixel-mode and 2 VideoDumpers on
              dual-pixel-mode.
    """
    self._input_id = input_id
    self._vdumps = vdumps
    self._is_dual = len(vdumps) == 2
    self._saved_hashes = []
    self._last_frame = 0

  def ComputeResolution(self):
    """Computes the resolution from FPGA."""
    if self._is_dual:
      resolutions = [(vdump.GetWidth(), vdump.GetHeight())
                     for vdump in self._vdumps]
      if resolutions[0] != resolutions[1]:
        logging.warn('Different resolutions between paths: %dx%d != %dx%d',
                     *(resolutions[0] + resolutions[1]))
      return (resolutions[0][0] + resolutions[1][0], resolutions[0][1])
    else:
      return (self._vdumps[0].GetWidth(), self._vdumps[0].GetHeight())

  def _StopFrameDump(self):
    """Stops frame dump."""
    for vdump in self._vdumps:
      vdump.Stop()

  def _StartFrameDump(self):
    """Starts frame dump."""
    for vdump in self._vdumps:
      # TODO(waihong): Wipe off the _input_id argument.
      vdump.Start(self._input_id, self._is_dual)

  def _SetupFrameDump(self, frame_limit, x, y, width, height, loop):
    """Restarts frame dump.

    Args:
      frame_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
      loop: True to loop-back and continue dump.
    """
    for vdump in self._vdumps:
      vdump.SetFrameLimit(frame_limit, loop)
      if None in (x, y, width, height):
        vdump.DisableCrop()
      else:
        if self._is_dual:
          vdump.EnableCrop(x / 2, y, width / 2, height)
        else:
          vdump.EnableCrop(x, y, width, height)

  def _ComputeFrameHash(self, index):
    """Computes the frame hash of the given frame index, from FPGA.

    Returns:
      A list of hash16 values, i.e. a single frame hash.
    """
    hashes = [vdump.GetFrameHash(index, self._is_dual)
              for vdump in self._vdumps]
    if self._is_dual:
      # [Odd MSB, Even MSB, Odd LSB, Odd LSB]
      return [hashes[1][0], hashes[0][0], hashes[1][1], hashes[0][1]]
    else:
      return hashes[0]

  def GetFrameHashes(self, start, stop):
    """Returns the list of the frame hashes.

    Args:
      start: The index of the start frame.
      stop: The index of the stop frame (excluded).

    Returns:
      A list of frame hashes.
    """
    return self._saved_hashes[start:stop]

  def _GetFrameCount(self):
    """Returns the current number of frame dumped."""
    return min(vdump.GetFrameCount() for vdump in self._vdumps)

  def _HasFramesDumpedAtLeast(self, frame_count):
    """Returns true if FPGA dumps at least the given frame count.

    The function assumes that the frame count starts at zero.
    """
    current_frame = self._GetFrameCount()
    if current_frame > self._last_frame:
      for i in xrange(self._last_frame, current_frame):
        self._saved_hashes.append(self._ComputeFrameHash(i))
        logging.info('Saved frame hash #%d: %r', i, self._saved_hashes[i])
      self._last_frame = current_frame
    return current_frame >= frame_count

  def _WaitForFrameCount(self, frame_count, timeout):
    """Waits until the given frame_count reached or timeout.

    Args:
      frame_count: A number of frames to wait.
      timeout: Time in second of timeout.
    """
    self._saved_hashes = []
    self._last_frame = 0
    common.WaitForCondition(
        lambda: self._HasFramesDumpedAtLeast(frame_count),
        True, self._DELAY_VIDEO_DUMP_PROBE, timeout)

  def DumpFramesToLimit(self, frame_limit, x, y, width, height, timeout):
    """Dumps frames and waits for the given limit being reached or timeout.

    Args:
      frame_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
      timeout: Time in second of timeout.
    """
    self._StopFrameDump()
    self._SetupFrameDump(frame_limit, x, y, width, height, loop=False)
    self._StartFrameDump()
    self._WaitForFrameCount(frame_limit, timeout)
