# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""I2C module for controlling I2C buses and I2C slaves."""

import array
import logging
import re
import subprocess
import time


class OutputFormatError(Exception):
  """Exception raised when output messages of the I2C tools did not match."""
  pass


class I2cBusError(Exception):
  """Exception raise when any unexpected behavior happened on I2C access."""
  pass


def Retry(retry_count, initial_delay):
  """Returns the decoration which calls the function with retries.

  Args:
    retry_count: Number of retries.
    initial_delay: The delay time in second, which is doubled on failure.
  """
  def RetryDecorator(func):
    def Retrying(self, *args, **kwargs):
      count = retry_count
      delay = initial_delay
      while count >= 0:
        try:
          return func(self, *args, **kwargs)
        except subprocess.CalledProcessError as e:
          logging.info("I2C error({0}): {1}".format(e.returncode, str(e.cmd)))
          count = count - 1
          if count >= 0:
            self.Reset()
            delay = delay * 2
            time.sleep(delay)
            logging.info("  retrying... (%d retrys left)", count)
          else:
            raise I2cBusError(e)
    return Retrying
  return RetryDecorator


class I2cBus(object):
  """A Class to abstract the behavior of I2C bus."""

  def __init__(self, tools, bus):
    """Constructs a I2cBus object.

    Args:
      tools: The SystemTools object.
      bus: The bus number.
    """
    self.tools = tools
    self.bus = bus
    self._resetter = None

  def RegisterResetter(self, resetter):
    """Registers the Reset function of the I2C bus.

    Args:
      resetter: The Reset function.
    """
    self._resetter = resetter

  def Reset(self):
    """Resets the I2C bus."""
    if self._resetter:
      self._resetter()

  def CreateSlave(self, slave):
    """Creates the I2C slave object of the given slave address.

    Args:
      slave: The number of slave address.

    Returns:
      An I2cSlave object.
    """
    return I2cSlave(self, slave)


class I2cSlave(object):
  """A Class to abstract the behavior of I2C slave."""

  _REG_SET_DELAY = 0.001

  _RETRY_COUNT = 3
  _RETRY_INITIAL_DELAY = 1.0

  def __init__(self, i2c_bus, slave):
    """Constructs a I2cSlave object.

    Args:
      i2c_bus: The I2cBus object.
      slave: The number of slave address.
    """
    self._i2c_bus = i2c_bus
    self._tools = self._i2c_bus.tools
    self._bus = self._i2c_bus.bus
    self._slave = slave
    self._i2cget_pattern = re.compile(r'0x[0-9a-f]{2}')
    self._i2cdump_pattern = re.compile(r'[0-9a-f]0:' + ' ([0-9a-f]{2})' * 16)

  def Reset(self):
    """Resets the I2C slave."""
    # Reset the whole I2C bus.
    self._i2c_bus.Reset()

  @Retry(_RETRY_COUNT, _RETRY_INITIAL_DELAY)
  def Dump(self):
    """Dumps all I2C content.

    Returns:
      A byte-array of the I2C content.
    """
    message = self._tools.Output('i2cdump', '-f', '-y', self._bus, self._slave)
    matches = self._i2cdump_pattern.findall(message)
    return array.array(
        'B', [int(s, 16) for match in matches for s in match]).tostring()

  @Retry(_RETRY_COUNT, _RETRY_INITIAL_DELAY)
  def Get(self, offset):
    """Gets the byte value of the given offset address.

    Args:
      offset: The offset address to read.

    Returns:
      An integer of the byte value.
    """
    message = self._tools.Output('i2cget', '-f', '-y', self._bus, self._slave,
                                 offset)
    matches = self._i2cget_pattern.match(message)
    if matches:
      return int(matches.group(0), 0)
    else:
      raise OutputFormatError('The output format of i2cget is not matched.')

  @Retry(_RETRY_COUNT, _RETRY_INITIAL_DELAY)
  def Set(self, data, offset=0):
    """Sets the given I2C content to the given offset address.

    Args:
      data: A byte or a byte-array of content to set.
      offset: The offset which the data starts from this address.
    """
    if isinstance(data, str):
      for index in xrange(0, len(data), 8):
        data_args = [ord(d) for d in data[index:index+8]] + ['i']
        self._tools.Call('i2cset', '-f', '-y', self._bus, self._slave,
                         offset + index, *data_args)
    elif isinstance(data, int) and 0 <= data <= 0xff:
      self._tools.Call('i2cset', '-f', '-y', self._bus, self._slave,
                       offset, data)
    else:
      raise OutputFormatError('The argument data is not a valid type.')

  def SetAndClear(self, offset, bitmask, delay=None):
    """Sets I2C registers with the bitmask and then clears it.

    Args:
      offset: The offset of the register.
      bitmask: The bitmask to set and clear.
      delay: The time between set and clear. Default: self._REG_SET_DELAY
    """
    byte = self.Get(offset)
    self.Set(byte | bitmask, offset)
    if delay is None:
      delay = self._REG_SET_DELAY
    time.sleep(delay)
    self.Set(byte & ~bitmask, offset)
