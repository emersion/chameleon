# -*- coding: utf-8 -*-
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
    logging.debug('Waiting for condition %s == %s', func.__name__, str(value))
    time.sleep(delay)
    end_time = time.time()
  else:
    message = ('Timeout on waiting for condition %s == %s' %
               (func.__name__, str(value)))
    logging.warn(message)
    raise TimeoutError(message)


def lazy(original_class):
  """lazy instantiation of the original_class.

  The original_class would be instantiated when any method or
  data member is accessed at the first time.

  Usage:
    Assume that the orignal instantiation is as follows:

      o = original_class(*args, **kwargs)

    To use lazy instantiation, it would be something like

      o = lazy(original_class)(*args, **kwargs)

  Note:
  - The following assignment statement would not instantiate the object.

    oo = o

  - However, the following statement would instantiate the object.

    print o

    since it invokes o.__str__()

  Args:
    original_class: the original class to be instantiated in the lazy way.
  """

  class LazyInstantiation(object):
    """The lazy wrapper class."""

    def __init__(self, *args, **kargs):
      self._args = args
      self._kargs = kargs
      self._class = original_class
      self._obj = None
      self._loaded = False

    def _load(self):
      self._obj = self._class(*self._args, **self._kargs)
      self._loaded = True

    def __getattr__(self, name):
      if not self._loaded:
        logging.info('Load %s to access %s.', self._class.__name__, name)
        self._load()
      return getattr(self._obj, name)

  return LazyInstantiation
