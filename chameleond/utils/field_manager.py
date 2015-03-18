# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Field manager module which manages the field dump and monitor logic."""

import logging
from multiprocessing import Process, Value, Array

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common
from chameleond.utils import fpga


class FieldManagerError(Exception):
  """Exception raised when any error on FieldManager."""
  pass


class FieldManager(object):
  """An abstraction of the field management.

  It acts as an intermediate layer between an InputFlow and VideoDumpers.
  It simplifies the logic of handling dual-pixel-mode and single-pixel-mode.
  """

  _HASH_SIZE = 4

  # Delay in second to check the field count, using 120-fps.
  _DELAY_VIDEO_DUMP_PROBE = 1.0 / 120

  def __init__(self, input_id, vdumps):
    """Constructs a FieldManager object.

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
    self._last_field = Value('i', -1)
    self._timeout_in_field = None
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

  def GetMaxFieldLimit(self, width, height):
    """Returns of the maximal number of fields which can be dumped."""
    if self._is_dual:
      width = width / 2
    return fpga.VideoDumper.GetMaxFieldLimit(width, height)

  def _StopFieldDump(self):
    """Stops field dump."""
    for vdump in self._vdumps:
      vdump.Stop()
    # We can't just stop the video dumpers as some functions, like detecting
    # resolution, need the video dumpers continue to run. So select them again
    # to re-initialize the default setting, i.e. single field non-loop dumping.
    # TODO(waihong): Simplify the above logic.
    for vdump in self._vdumps:
      vdump.Select(self._input_id, self._is_dual)

  def _StartFieldDump(self):
    """Starts field dump."""
    for vdump in self._vdumps:
      # TODO(waihong): Wipe off the _input_id argument.
      vdump.Start(self._input_id, self._is_dual)

  def _SetupFieldDump(self, field_limit, x, y, width, height, loop):
    """Restarts field dump.

    Args:
      field_limit: The limitation of field to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      loop: True to loop-back and continue dump.
    """
    for vdump in self._vdumps:
      vdump.SetDumpAddressForCapture()
      vdump.SetFieldLimit(field_limit, loop)
      if None in (x, y):
        vdump.DisableCrop()
      else:
        if self._is_dual:
          vdump.EnableCrop(x / 2, y, width / 2, height)
        else:
          vdump.EnableCrop(x, y, width, height)

  def _ComputeFieldHash(self, index):
    """Computes the field hash of the given field index, from FPGA.

    Returns:
      A list of hash16 values, i.e. a single field hash.
    """
    hashes = [vdump.GetFieldHash(index, self._is_dual)
              for vdump in self._vdumps]
    if self._is_dual:
      # [Odd MSB, Even MSB, Odd LSB, Odd LSB]
      return [hashes[1][0], hashes[0][0], hashes[1][1], hashes[0][1]]
    else:
      return hashes[0]

  def GetFieldHashes(self, start, stop):
    """Returns the saved list of the field hashes.

    Args:
      start: The index of the start field.
      stop: The index of the stop field (excluded).

    Returns:
      A list of field hashes.
    """
    # Convert to a list, in which each element is a field hash.
    return [self._saved_hashes[i : i + self._HASH_SIZE]
            for i in xrange(start * self._HASH_SIZE,
                            stop * self._HASH_SIZE,
                            self._HASH_SIZE)]

  def GetFieldCount(self):
    """Returns the saved number of field dumped."""
    return self._last_field.value

  def _ComputeFieldCount(self):
    """Returns the current number of field dumped."""
    return min(vdump.GetFieldCount() for vdump in self._vdumps)

  def _HasFieldsDumpedAtLeast(self, field_count):
    """Returns true if FPGA dumps at least the given field count.

    The function assumes that the field count starts at zero.
    """
    current_field = self._ComputeFieldCount()
    if current_field > self._last_field.value:
      for i in xrange(self._last_field.value, current_field):
        hash64 = self._ComputeFieldHash(i)
        for j in xrange(self._HASH_SIZE):
          self._saved_hashes[i * self._HASH_SIZE + j] = hash64[j]
        logging.info(
            'Saved field hash #%d: %r', i,
            self._saved_hashes[i * self._HASH_SIZE : (i + 1) * self._HASH_SIZE])
      self._last_field.value = current_field
    return current_field >= field_count

  def _WaitForFieldCount(self, field_count, timeout):
    """Waits until the given field_count reached or timeout.

    Args:
      field_count: A number of fields to wait.
      timeout: Time in second of timeout.
    """
    self._last_field.value = 0
    # Give the lambda method a better name, for debugging.
    func = lambda: self._HasFieldsDumpedAtLeast(field_count)
    func.__name__ = 'HasFieldsDumpedAtLeast%d' % field_count
    common.WaitForCondition(func, True, self._DELAY_VIDEO_DUMP_PROBE, timeout)

  def _CreateSavedHashes(self, field_count):
    """Creates the saved hashes, a sharable object of multiple processes."""
    # Store the hashes in a flat array, limitation of the shared variable.
    if self._saved_hashes:
      del self._saved_hashes
    array_size = field_count * self._HASH_SIZE
    self._saved_hashes = Array('H', array_size)

  def _StartMonitoringFields(self, hash_buffer_limit):
    """Starts a process to monitor fields."""
    self._StopMonitoringFields()
    self._CreateSavedHashes(hash_buffer_limit)
    # Keep 5 seconds margin for timeout.
    timeout_in_second = hash_buffer_limit / 60 + 5
    self._timeout_in_field = hash_buffer_limit
    self._process = Process(target=self._WaitForFieldCount,
                            args=(hash_buffer_limit,
                                  timeout_in_second))
    self._process.start()

  def _StopMonitoringFields(self):
    """Stops the previous process which monitors fields."""
    if self._process and self._process.is_alive():
      self._process.terminate()
      self._process.join()

  def DumpFieldsToLimit(self, field_buffer_limit, x, y, width, height, timeout):
    """Dumps fields and waits for the given limit being reached or timeout.

    Args:
      field_buffer_limit: The limitation of field to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      timeout: Time in second of timeout.
    """
    self._StopFieldDump()
    self._SetupFieldDump(field_buffer_limit, x, y, width, height, loop=False)
    self._StartFieldDump()
    self._CreateSavedHashes(field_buffer_limit)
    self._WaitForFieldCount(field_buffer_limit, timeout)

  def StartDumpingFields(self, field_buffer_limit, x, y, width, height,
                         hash_buffer_limit):
    """Starts dumping fields continuously.

    Args:
      field_buffer_limit: The size of the buffer which stores the field.
                          Fields will be dumped to the beginning when full.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      hash_buffer_limit: The maximum number of hashes to monitor. Stop
                         capturing when this limitation is reached.
    """
    self._StopFieldDump()
    self._SetupFieldDump(field_buffer_limit, x, y, width, height, loop=True)
    self._StartFieldDump()
    self._StartMonitoringFields(hash_buffer_limit)

  def StopDumpingFields(self):
    """Stops dumping fields."""
    if self._last_field.value == -1:
      raise FieldManagerError('Not started capuring video yet.')
    self._StopFieldDump()
    self._StopMonitoringFields()
