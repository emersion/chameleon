# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Frame manager module which manages the fields and frames."""

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import field_manager


class FrameManagerError(Exception):
  """Exception raised when any error on FrameManager."""
  pass


class FrameManager(object):
  """An abstraction of the frame management.

  It handles the progressive and interlaced modes and calls the proper
  methods in FieldManager.
  """

  def __init__(self, input_id, rx, vdumps):
    """Constructs a FrameManager object.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
      rx: A receiver object.
      vdumps: A list of VideoDumper objects to manage, e.g., a single
              VideoDumper on single-pixel-mode and 2 VideoDumpers on
              dual-pixel-mode.
    """
    self._input_id = input_id
    self._rx = rx
    self._vdumps = vdumps
    self._field_manager = field_manager.FieldManager(input_id, vdumps)
    self._is_interlaced = None

  def ComputeResolution(self):
    """Computes the resolution from FPGA."""
    field_per_frame = 2 if self._rx.IsInterlaced() else 1
    (width, height) = self._field_manager.ComputeResolution()
    return (width, height * field_per_frame)

  def GetMaxFrameLimit(self, width, height):
    """Returns of the maximal number of frames which can be dumped."""
    field_per_frame = 2 if self._rx.IsInterlaced() else 1
    height = height / field_per_frame
    field_limit = self._field_manager.GetMaxFieldLimit(width, height)
    return field_limit / field_per_frame

  def GetFrameHashes(self, start, stop):
    """Returns the saved list of the frame hashes.

    Args:
      start: The index of the start frame.
      stop: The index of the stop frame (excluded).

    Returns:
      A list of frame hashes.
    """
    if self._is_interlaced:
      # TODO(waihong): The FPGA computed hashes are wrong in interlaced mode.
      # Have to change the formula to make the hash consistent in both
      # progressive and interlaced modes.
      raise FrameManagerError('Interlaced mode GetFrameHashes not supported.')
    else:
      return self._field_manager.GetFieldHashes(start, stop)

  def GetHistograms(self, start, stop):
    """Returns the saved list of the histograms.

    Args:
      start: The index of the start field.
      stop: The index of the stop field (excluded).

    Returns:
      A list of histograms.
    """
    return self._field_manager.GetHistograms(start, stop)

  def GetDumpedDimension(self):
    """Gets the dimension of the dumped frames."""
    field_per_frame = 2 if self._is_interlaced else 1
    (width, height) = self._field_manager.GetDumpedDimension()
    return (width, height * field_per_frame)

  def GetFrameCount(self):
    """Returns the saved number of frame dumped."""
    field_per_frame = 2 if self._is_interlaced else 1
    return self._field_manager.GetFieldCount() / field_per_frame

  def ReadDumpedFrame(self, frame_index):
    """Reads the content of the dumped frame from the buffer."""
    if self._is_interlaced:
      # Merge two fields into one frame.
      (width, _) = self._field_manager.GetDumpedDimension()
      PIXEL_LEN = 3
      line_len = width * PIXEL_LEN
      even_field = self._field_manager.ReadDumpedField(frame_index * 2)
      odd_field = self._field_manager.ReadDumpedField(frame_index * 2 + 1)
      return ''.join([''.join([even_field[i:i+line_len],
                               odd_field[i:i+line_len]])
                      for i in xrange(0, len(even_field), line_len)])
    else:
      return self._field_manager.ReadDumpedField(frame_index)

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
    # Cache the flag when start capturing
    self._is_interlaced = self._rx.IsInterlaced()
    field_per_frame = 2 if self._is_interlaced else 1

    # Check alignment for interlaced mode.
    if self._is_interlaced:
      if y is not None:
        if y % 2:
          raise FrameManagerError('Argument y not even in interlaced mode.')
        y = y / field_per_frame
      if height % 2:
        raise FrameManagerError('Argument height not even in interlaced mode.')
      height = height / field_per_frame

    field_buffer_limit = frame_buffer_limit * field_per_frame
    self._field_manager.DumpFieldsToLimit(
        field_buffer_limit, x, y, width, height, timeout)

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
    # Cache the flag when start capturing
    self._is_interlaced = self._rx.IsInterlaced()
    field_per_frame = 2 if self._is_interlaced else 1

    # Check alignment for interlaced mode.
    if self._is_interlaced:
      if y is not None:
        if y % 2:
          raise FrameManagerError('Argument y not even in interlaced mode.')
        y = y / field_per_frame
      if height % 2:
        raise FrameManagerError('Argument height not even in interlaced mode.')
      height = height / field_per_frame

    field_buffer_limit = frame_buffer_limit * field_per_frame
    self._field_manager.StartDumpingFields(
        field_buffer_limit, x, y, width, height, hash_buffer_limit)

  def StopDumpingFrames(self):
    """Stops dumping frames."""
    self._field_manager.StopDumpingFields()
