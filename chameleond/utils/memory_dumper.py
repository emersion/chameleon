# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The module provides utils to dump memory from a ring buffer periodically."""

import logging
import multiprocessing

from chameleond.utils import system_tools


class MemoryDumperError(Exception):
  """Exception in MemoryDumper."""
  pass


class MemoryDumper(multiprocessing.Process):
  """Dumping memory from a ring buffer to a file in a subprocess."""
  _DUMP_PERIOD_SECS = 1.0

  def __init__(self, file_path, adump):
    """Initializes a MemoryDumper.

    Args:
      file_path: The file path to dump data to. Note that the data will be
                 appended to the end of the file.
      adump: an AudioDump object for dumper control on FPGA.
    """
    super(MemoryDumper, self).__init__()
    self._last_page_count = None
    self._last_last_page_count = None
    self._current_page_count = None
    self._page_count_in_this_period = None
    self._file_path = file_path
    self._adump = adump
    self._stop_event = multiprocessing.Event()
    self.daemon = True

  def Stop(self):
    """Stops the periodic dumping process."""
    self._stop_event.set()

  def run(self):
    """Runs the periodic dumping process.

    Note that the audio page count should really start from 0, and this
    should not be called too lately, or the page count in the first period
    may be greater than MAX_DUMP_PAGES.
    """
    self._last_page_count = 0
    while True:
      self._stop_event.wait(self._DUMP_PERIOD_SECS)
      if self._stop_event.is_set():
        return
      self._HandleOnePeriod()

  def _HandleOnePeriod(self):
    """Handles the work to be done in a period.

    The work includes:
    1. Gets the page count from dumper.
    2. Checks if there is overflow, that is, too many pages to be dumped.
    3. Append the data from memory dump area to the end of the target file.
    4. Updates the variables for last and last last page count.

    Raises:
      MemoryDumperError if page count in a period is invalid.
    """
    self._current_page_count = self._adump.GetCurrentPageCount()
    self._page_count_in_this_period = (
        self._current_page_count - self._last_page_count)

    logging.info(
        'Current page count: 0x%x. Last page count: 0x%x. '
        'Page count in this period: 0x%x',
        self._current_page_count, self._last_page_count,
        self._page_count_in_this_period)

    # No data received in this period.
    if self._page_count_in_this_period == 0:
      return
    elif self._page_count_in_this_period < 0:
      raise MemoryDumperError('page count in this period: %d is invalid',
                              self._page_count_in_this_period)

    self._CheckOverlap()
    self._DumpPages()
    self._UpdateOnePeriod()

  def _CheckOverlap(self):
    """Checks the buffered data is not overlapped.

    Checks the data written by hardware in this period does not overlap with
    data to be dumped in the last period.

    Period                 0        1        2       3       4
    Write by FPGA:         A        B        C       D       E
    Read by MemoryDumper:           A        B       C       D

    In each period, the sum of data range (e.g. A+B, B+C, C+D, D+E) should be
    less than page limit, that is, the maximum number of pages in ring buffer.
    However, we can only check the data of each period in the next period after
    the data is written by FPGA.
    E.g., in period 2, we can check B+A is less than page limit in ring buffer,
    and makes sure the data written in period 1 (B) did not overlap with data
    read in period 1 (A).

    Raises:
      MemoryDumperError if buffered page count is larger than page limit.
    """
    if self._last_last_page_count is not None:
      # buffered pages is the sum of pages to be read in this period by
      # MemoryDumper and pages to be written in this cycle
      buffered_pages = self._current_page_count - self._last_last_page_count
      logging.info('buffered_pages: 0x%x, max: 0x%x', buffered_pages,
                   self._adump.MAX_DUMP_PAGES)
      if buffered_pages > self._adump.MAX_DUMP_PAGES:
        raise MemoryDumperError(
            'Bufferred pages %s more than page limit %s' % (
                buffered_pages, self._adump.MAX_DUMP_PAGES))

  def _GetProjectedPageIndex(self, page_count):
    """Gets the projected page index from page_count.

    Args:
      page_count: The page count. It will keep increasing and become larger
                  than page limit. We need to wrap it around the
                  end to get the page index to be used to access the memory.

    Returns:
      The projected page index in [0, self._adump.MAX_DUMP_PAGES - 1].
    """
    return page_count % self._adump.MAX_DUMP_PAGES

  def _DumpPages(self):
    """Dumps a logical range of pages for this period.

    Note that if this range wraps around the end of ring buffer, we need to
    dump it in two steps.

    Raises:
      MemoryDumperError if page count in this period is larger than page limit.
    """
    if self._page_count_in_this_period > self._adump.MAX_DUMP_PAGES:
      raise MemoryDumperError(
          'Too many pages %s in this period' % self._page_count_in_this_period)

    start_page_index = self._GetProjectedPageIndex(self._last_page_count)
    end_page_index = self._GetProjectedPageIndex(self._current_page_count)
    if end_page_index < start_page_index:
      self._DumpPagesFromMemoryAppendToFile(
          start_page_index, self._adump.MAX_DUMP_PAGES - start_page_index)
      self._DumpPagesFromMemoryAppendToFile(
          0, end_page_index)
    else:
      self._DumpPagesFromMemoryAppendToFile(
          start_page_index, self._page_count_in_this_period)

  def _DumpPagesFromMemoryAppendToFile(self, start_page_index, page_count):
    """Dumps a physical range of pages and appends the data to a file.

    Args:
      start_page_index: The start page index. The page index is between 0 and
                        page limit - 1.
      page_count: The number of pages.

    Raises:
      MemoryDumperError if the range to dump is invalid.
      MemoryDumperError if pixeldump returns error.
    """
    logging.info('Dump from page index 0x%x with count 0x%x',
                 start_page_index, page_count)
    if start_page_index + page_count > self._adump.MAX_DUMP_PAGES:
      raise MemoryDumperError(
          'Wrong page range, start: 0x%x, count: 0x%x' % (
              start_page_index, page_count))

    start_address = (self._adump.start_address +
                     start_page_index * self._adump.PAGE_SIZE)

    command = ['pixeldump', '-a', start_address, '-', self._adump.PAGE_SIZE,
               page_count, 1]
    logging.info('Dump: %s', command)
    p = system_tools.SystemTools.RunInSubprocess(*command)

    (return_code, out, err) = system_tools.SystemTools.GetSubprocessOutput(p)
    if return_code:
      logging.error('Dump return %d, error: %s', return_code, err)
      raise MemoryDumperError(err)

    with open(self._file_path, 'a') as f:
      f.write(out)

  def _UpdateOnePeriod(self):
    """Updates the variables for page count."""
    self._last_last_page_count = self._last_page_count
    self._last_page_count = self._current_page_count
