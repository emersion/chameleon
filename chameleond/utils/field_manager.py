# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Field manager module which manages the field dump and monitor logic."""

import logging
import tempfile
from multiprocessing import Process, Value, Array

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common
from chameleond.utils import fpga
from chameleond.utils import system_tools


class FieldManagerError(Exception):
  """Exception raised when any error on FieldManager."""
  pass


class FieldManager(object):
  """An abstraction of the field management.

  It acts as an intermediate layer between an InputFlow and VideoDumpers.
  It simplifies the logic of handling dual-pixel-mode and single-pixel-mode.
  """

  _HASH_SIZE = 4

  # TODO: Make the grid and sample numbers user-configurable.
  _GRID_NUM = 3
  _GRID_SAMPLE_NUM = 10

  _HISTOGRAM_SIZE = _GRID_NUM * _GRID_NUM * 3 * 4  # RGB * 4 buckets

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
    self._saved_histograms = None
    self._last_field = Value('i', -1)
    self._timeout_in_field = None
    self._process = None
    self._dimension = (0, 0)

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

  def GetDumpedDimension(self):
    """Gets the dimension of the dumped fields."""
    return self._dimension

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
    # Check the alignment for a cropped dimension.
    if self._is_dual:
      alignment = 16
    else:
      alignment = 8
    if x is not None and x % alignment:
      raise FieldManagerError('Arguments x not aligned to %d-byte.' % alignment)
    if width % alignment:
      raise FieldManagerError('Arguments width not aligned to %d-byte.' %
                              alignment)

    # Save the dimension of fields.
    self._dimension = (width, height)

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

  def _ComputeHistograms(self, start, stop):
    """Computes the histograms of the dumped fields from the buffer.

    Args:
      start: The index of the start field.
      stop: The index of the stop field (excluded).

    Returns:
      A list of normalized histograms.
    """
    if stop <= start:
      return []

    (width, height) = self._dimension
    if self._is_dual:
      width = width / 2

    # Modify the memory offset to match the field.
    PAGE_SIZE = 4096
    PIXEL_LEN = 3
    field_size = width * height * PIXEL_LEN
    field_size = ((field_size - 1) / PAGE_SIZE + 1) * PAGE_SIZE
    offset_args = ['-g', self._GRID_NUM, '-s', self._GRID_SAMPLE_NUM]
    # The histogram is computed by sampled pixels. Getting one band is enough
    # even if it is in dual pixel mode.
    offset_addr = fpga.VideoDumper.GetPixelDumpArgs(self._input_id, False)[1]

    max_limit = fpga.VideoDumper.GetMaxFieldLimit(width, height)
    for i in xrange(start, stop):
      offset_args += ['-a', offset_addr + field_size * (i % max_limit)]

    result = system_tools.SystemTools.Output(
        'histogram', width, height, *offset_args)
    # Normalize the histogram by dividing the maximum.
    return [[float(v) / self._GRID_SAMPLE_NUM / self._GRID_SAMPLE_NUM
             for v in l.split()]
            for l in result.splitlines()]

  def GetHistograms(self, start, stop):
    """Returns the saved list of the histograms.

    Args:
      start: The index of the start field.
      stop: The index of the stop field (excluded).

    Returns:
      A list of histograms.
    """
    return [self._saved_histograms[i : i + self._HISTOGRAM_SIZE]
            for i in xrange(start * self._HISTOGRAM_SIZE,
                            stop * self._HISTOGRAM_SIZE,
                            self._HISTOGRAM_SIZE)]

  def ReadDumpedField(self, field_index):
    """Reads the content of the dumped field from the buffer."""
    (width, height) = self._dimension
    if self._is_dual:
      width = width / 2

    # Modify the memory offset to match the field.
    PAGE_SIZE = 4096
    PIXEL_LEN = 3
    field_size = width * height * PIXEL_LEN
    field_size = ((field_size - 1) / PAGE_SIZE + 1) * PAGE_SIZE
    offset = field_size * field_index
    offset_args = []
    for arg in fpga.VideoDumper.GetPixelDumpArgs(self._input_id, self._is_dual):
      if isinstance(arg, (int, long)):
        offset_args.append(arg + offset)
      else:
        offset_args.append(arg)
    logging.info('pixeldump args %r', offset_args)

    with tempfile.NamedTemporaryFile() as f:
      system_tools.SystemTools.Call(
          'pixeldump', f.name, width, height, PIXEL_LEN, *offset_args)
      return f.read()

  def _HasFieldsDumpedAtLeast(self, field_count):
    """Returns true if FPGA dumps at least the given field count.

    The function assumes that the field count starts at zero.
    """
    current_field = self._ComputeFieldCount()
    if current_field > self._last_field.value:
      start = self._last_field.value
      stop = current_field
      for i in xrange(start, stop):
        hash64 = self._ComputeFieldHash(i)
        for j in xrange(self._HASH_SIZE):
          self._saved_hashes[i * self._HASH_SIZE + j] = hash64[j]
        logging.debug(
            'Saved field hash #%d: %r', i,
            self._saved_hashes[i * self._HASH_SIZE : (i + 1) * self._HASH_SIZE])

      histograms = self._ComputeHistograms(start, stop)
      for i, h in enumerate(histograms):
        self._saved_histograms[
            (start + i) * self._HISTOGRAM_SIZE :
            (start + i + 1) * self._HISTOGRAM_SIZE] = h
        logging.debug('Saved histogram #%d: %s', start + i,
                      ', '.join(['%.02f' % v for v in h]))

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
      del self._saved_histograms
    array_size = field_count * self._HASH_SIZE
    self._saved_hashes = Array('H', array_size)
    array_size = field_count * self._HISTOGRAM_SIZE
    self._saved_histograms = Array('f', array_size)

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
