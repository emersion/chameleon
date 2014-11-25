# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Frame manager module which manages the frame dump and monitor logic."""

import logging
from multiprocessing import Process, Value, Array

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common


class FrameManagerError(Exception):
  """Exception raised when any error on FrameManager."""
  pass


class FrameManager(object):
  """An abstraction of the frame management.

  It acts as an intermediate layer between an InputFlow and VideoDumpers.
  It simplifies the logic of handling dual-pixel-mode and single-pixel-mode.
  """

  _HASH_SIZE = 4

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
    self._saved_hashes = None
    self._last_frame = Value('i', -1)
    self._timeout_in_frame = None
    self._process = None

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
    # We can't just stop the video dumpers as some functions, like detecting
    # resolution, need the video dumpers continue to run. So select them again
    # to re-initialize the default setting, i.e. single frame non-loop dumping.
    # TODO(waihong): Simplify the above logic.
    for vdump in self._vdumps:
      vdump.Select(self._input_id, self._is_dual)

  def _StartFrameDump(self):
    """Starts frame dump."""
    for vdump in self._vdumps:
      # TODO(waihong): Wipe off the _input_id argument.
      vdump.Start(self._input_id, self._is_dual)

  def _SetupFrameDump(self, frame_limit, x, y, width, height, loop):
    """Restarts frame dump.

    Args:
      frame_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      loop: True to loop-back and continue dump.
    """
    for vdump in self._vdumps:
      vdump.SetDumpAddressForCapture()
      vdump.SetFrameLimit(frame_limit, loop)
      if None in (x, y):
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
    """Returns the saved list of the frame hashes.

    Args:
      start: The index of the start frame.
      stop: The index of the stop frame (excluded).

    Returns:
      A list of frame hashes.
    """
    # Convert to a list, in which each element is a frame hash.
    return [self._saved_hashes[i : i + self._HASH_SIZE]
            for i in xrange(start * self._HASH_SIZE,
                            stop * self._HASH_SIZE,
                            self._HASH_SIZE)]

  def GetFrameCount(self):
    """Returns the saved number of frame dumped."""
    return self._last_frame.value

  def _ComputeFrameCount(self):
    """Returns the current number of frame dumped."""
    return min(vdump.GetFrameCount() for vdump in self._vdumps)

  def _HasFramesDumpedAtLeast(self, frame_count):
    """Returns true if FPGA dumps at least the given frame count.

    The function assumes that the frame count starts at zero.
    """
    current_frame = self._ComputeFrameCount()
    if current_frame > self._last_frame.value:
      for i in xrange(self._last_frame.value, current_frame):
        hash64 = self._ComputeFrameHash(i)
        for j in xrange(self._HASH_SIZE):
          self._saved_hashes[i * self._HASH_SIZE + j] = hash64[j]
        logging.info(
            'Saved frame hash #%d: %r', i,
            self._saved_hashes[i * self._HASH_SIZE : (i + 1) * self._HASH_SIZE])
      self._last_frame.value = current_frame
    return current_frame >= frame_count

  def _WaitForFrameCount(self, frame_count, timeout):
    """Waits until the given frame_count reached or timeout.

    Args:
      frame_count: A number of frames to wait.
      timeout: Time in second of timeout.
    """
    self._last_frame.value = 0
    # Give the lambda method a better name, for debugging.
    func = lambda: self._HasFramesDumpedAtLeast(frame_count)
    func.__name__ = 'HasFramesDumpedAtLeast%d' % frame_count
    common.WaitForCondition(func, True, self._DELAY_VIDEO_DUMP_PROBE, timeout)

  def _CreateSavedHashes(self, frame_count):
    """Creates the saved hashes, a sharable object of multiple processes."""
    # Store the hashes in a flat array, limitation of the shared variable.
    if self._saved_hashes:
      del self._saved_hashes
    array_size = frame_count * self._HASH_SIZE
    self._saved_hashes = Array('H', array_size)

  def _StartMonitoringFrames(self, hash_buffer_limit):
    """Starts a process to monitor frames."""
    self._StopMonitoringFrames()
    self._CreateSavedHashes(hash_buffer_limit)
    # Keep 5 seconds margin for timeout.
    timeout_in_second = hash_buffer_limit / 60 + 5
    self._timeout_in_frame = hash_buffer_limit
    self._process = Process(target=self._WaitForFrameCount,
                            args=(hash_buffer_limit,
                                  timeout_in_second))
    self._process.start()

  def _StopMonitoringFrames(self):
    """Stops the previous process which monitors frames."""
    if self._process and self._process.is_alive():
      self._process.terminate()
      self._process.join()

  def DumpFramesToLimit(self, frame_buffer_limit, x, y, width, height, timeout):
    """Dumps frames and waits for the given limit being reached or timeout.

    Args:
      frame_buffer_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      timeout: Time in second of timeout.
    """
    self._StopFrameDump()
    self._SetupFrameDump(frame_buffer_limit, x, y, width, height, loop=False)
    self._StartFrameDump()
    self._CreateSavedHashes(frame_buffer_limit)
    self._WaitForFrameCount(frame_buffer_limit, timeout)

  def StartDumpingFrames(self, frame_buffer_limit, x, y, width, height,
                         hash_buffer_limit):
    """Starts dumping frames continuously.

    Args:
      frame_buffer_limit: The size of the buffer which stores the frame.
                          Frames will be dumped to the beginning when full.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      hash_buffer_limit: The maximum number of hashes to monitor. Stop
                         capturing when this limitation is reached.
    """
    self._StopFrameDump()
    self._SetupFrameDump(frame_buffer_limit, x, y, width, height, loop=True)
    self._StartFrameDump()
    self._StartMonitoringFrames(hash_buffer_limit)

  def StopDumpingFrames(self):
    """Stops dumping frames."""
    if self._last_frame.value == -1:
      raise FrameManagerError('Not started capuring video yet.')
    self._StopFrameDump()
    self._StopMonitoringFrames()
