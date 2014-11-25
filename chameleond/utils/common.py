# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Common utilities."""

import logging
import time


class TimeoutError(Exception):
  """Exception raised on timeout."""
  pass


def WaitForCondition(func, value, delay, timeout):
  """Waits for the given function matches the given value.

  Args:
    func: The function to be tested.
    value: The value to fit the condition.
    delay: The time of delay for each try.
    timeout: The timeout in second to break the check.

  Raises:
    TimeoutError on timeout.
  """
  end_time = start_time = time.time()
  while end_time - start_time < timeout:
    if func() == value:
      break
    logging.info('Waiting for condition %s == %s', func.__name__, str(value))
    time.sleep(delay)
    end_time = time.time()
  else:
    message = ('Timeout on waiting for condition %s == %s' %
               (func.__name__, str(value)))
    logging.warn(message)
    raise TimeoutError(message)
