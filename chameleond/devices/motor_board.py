# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control button motors."""

import collections
import logging
import os
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import chameleon_io as io

"""
Holds bit offsets for motor ports.
Currently all motors use the same I/O expander.
If some motor needs to use another I/O expander, or some ports of a
motor need to use another I/O expander, index needs to be saved in
MotorPorts too.
"""
MotorPorts = collections.namedtuple(
    'MotorPorts', ['step', 'direction', 'enable'])


"""
Motor parameter:
  num_pulse: Number of pulses to drive step motor.
  period_ms: Duration of each pulse in ms.
"""
MotorParams = collections.namedtuple(
    'MotorParams', ['num_pulse', 'period_ms'])


class ButtonFunction(object):
  """Button functions that motor touch/release."""
  CALL = 'Call'
  HANG_UP = 'Hang Up'
  MUTE = 'Mute'
  VOL_UP = 'Vol Up'
  VOL_DOWN = 'Vol Down'


class MotorBoardException(Exception):
  """Errors in MotorBoard."""


class MotorBoardNotExistException(MotorBoardException):
  """Error that motor board does not exist."""


class MotorBoard(object):
  """Controls button motor through motor board.

  A motor has three ports: Step, Direction, Enable.
  There are five motors to control on motor board.
  This class provides the interface to control these ports.
  The ports are controlled through an I/O expander on I2C bus 3 address 0x23.

  =============================================

  I/O expander: address 0x23

  bit offset     15  14  13  12  11  10   9   8

  name          p17 p16 p15 p14 p13 p12 p11 p10

  bit offset      7   6   5   4   3   2   1   0

  name          p07 p06 p05 p04 p03 p02 p01 p00

  =============================================

  Common: Microstep resolution

  Name      name     bit offset

  MS1        p01         1
  MS2        p02         2
  MS3        p03         3

  =============================================

  Motor   Function    port  name   bit offset

  0       Call        step   p04       4
                       dir   p00       0
                    enable   p05       5

  1       Hangup      step   p06       6
                       dir   p00       0
                    enable   p07       7

  2       Mute        step   p10       8
                       dir   p00       0
                    enable   p11       9

  3       Vol Up      step   p12      10
                       dir   p00       0
                    enable   p13      11

  4       Vol Down    step   p14      12
                       dir   p00       0
                    enable   p15      13

  =============================================

  """

  # Mapping from motor function to ports.
  _MOTOR_PORT_MAP = {
      ButtonFunction.CALL: MotorPorts(4, 0, 5),
      ButtonFunction.HANG_UP: MotorPorts(6, 0, 7),
      ButtonFunction.MUTE: MotorPorts(8, 0, 9),
      ButtonFunction.VOL_UP: MotorPorts(10, 0, 11),
      ButtonFunction.VOL_DOWN: MotorPorts(12, 0, 13)}

  # TODO(cychiang) Tune the duration and parameters.
  _MODEL_PARAMS_MAP = {
      'Atrus': {
           ButtonFunction.CALL: MotorParams(500, 10),
           ButtonFunction.HANG_UP: MotorParams(500, 10),
           ButtonFunction.MUTE: MotorParams(500, 10),
           ButtonFunction.VOL_UP: MotorParams(500, 10),
           ButtonFunction.VOL_DOWN: MotorParams(500, 10),
      },
      'Jabra': {
           ButtonFunction.CALL: MotorParams(600, 3),
           ButtonFunction.HANG_UP: MotorParams(600, 3),
           ButtonFunction.MUTE: MotorParams(600, 3),
           ButtonFunction.VOL_UP: MotorParams(600, 3),
           ButtonFunction.VOL_DOWN: MotorParams(600, 3),
      }
  }

  _MODEL_TAG_PATH = '/etc/default/motor_model'

  def __init__(self, i2c_bus):
    """Constructs a MotorBoard.

    Args:
      i2c_bus: The I2cBus object.
    """
    self._i2c_bus = i2c_bus
    self._motor_io = io.IoExpander(self._i2c_bus,
                                   io.IoExpander.SLAVE_ADDRESSES[3])
    self._i2c_bus.AddSlave(self._motor_io)
    self._motors = {}

  def IsDetected(self):
    """Returns if the device can be detected."""
    if self._motor_io.IsDetected():
      return True
    else:
      logging.info('Can not access I2c slave on motor board. '
                   'Assume it is not connected')
      return False

  def InitDevice(self):
    """Runs the initialization sequence for the motor board.

    Raises:
      MotorBoardException: If motor board can not be initialized.
    """
    self._ResetPorts()
    model_name = self._GetModelName()
    logging.info('Init motor board for model: %s', model_name)

    self._CreateMotors(model_name)

    logging.info('MotorBoard initialized')

  def Reset(self):
    """Resets motor boards by releasing button and resetting port directions."""
    for func, motor in self._motors.iteritems():
      logging.info('Reset motor for %s function', func)
      motor.Reset()

  def _GetModelName(self):
    """Gets model name for this motor board.

    Returns:
      A string for model name.

    Raises:
      If model tag path does not exist or it contains unexpected model name.
    """
    if not os.path.exists(self._MODEL_TAG_PATH):
      raise MotorBoardException(
          'Model path does not exist: %s' % self._MODEL_TAG_PATH)
    with open(self._MODEL_TAG_PATH) as f:
      model_name = f.readline().strip()
    if model_name not in self._MODEL_PARAMS_MAP:
      raise MotorBoardException('Model name not expected: %s' % model_name)
    return model_name

  def _ResetPorts(self):
    """Resets all ports on I/O expander to input direction.

    The voltage level of all the ports are determined by their pull-up
    or pull-down circuits.
    """
    self._motor_io.SetDirection(0xffff)

  def _CreateMotors(self, model_name):
    """Creates motors.

    Args:
      model_name: A key in self._MODEL_PARAMS_MAP.
    """
    if model_name not in self._MODEL_PARAMS_MAP:
      raise MotorBoardException('Unexpected model name %s' % model_name)

    model_map = self._MODEL_PARAMS_MAP[model_name]

    for func, params in model_map.iteritems():
      ports = self._MOTOR_PORT_MAP[func]
      self._motors[func] = Motor(self._motor_io, ports, params)

  def _CheckFunction(self, func):
    """Check if a button function is supported on this motor board.

    Args:
      func: Button function for this motor. Defined in ButtonFunction.

    Raises:
      MotorBoardException if func is not supported on this motor board.
    """
    if func not in self._motors:
      raise MotorBoardException('Button function %s not suported' % func)

  def Touch(self, func):
    """Let one of the motor moves to touch a button.

    Args:
      func: Button function for this motor. Defined in ButtonFunction.
    """
    self._CheckFunction(func)
    self._motors[func].Touch()

  def Release(self, func):
    """Let one of the motor release button.

    Args:
      func: Button function for this motor. Defined in ButtonFunction.
    """
    self._CheckFunction(func)
    self._motors[func].Release()


class _MotorState(object):
  """Motor states."""
  RELEASED = 'Released'
  TOUCHED = 'Touched'


class _MotorDirection(object):
  """Motor moving direction."""
  UP = 'Up'
  DOWN = 'Down'


class MotorError(Exception):
  """Error in Motor."""


class Motor(object):
  """Class to control one motor."""
  _MOTOR_PULSE_HIGH = 1
  _MOTOR_PULSE_LOW = 0
  _RESET_NUM_PULSE = 800

  def __init__(self, motor_io, motor_ports, params):
    """Initializes one Motor.

    Args:
      motor_io: A IoExpander object.
      motor_ports: A MotorPorts for port bit offset.
      params: A MotorParams namedtuple.
    """
    self._motor_io = motor_io
    self._ports = motor_ports
    self._params = params
    # TODO(cychiang) See if this assumption is true, or add a mechanism
    # to reset the motor state when init.
    self._state = _MotorState.RELEASED

  def Reset(self):
    """Controls the motor to reset position."""
    self._Enable(True)
    self._SetDirection(_MotorDirection.UP)
    self._Move(self._RESET_NUM_PULSE)
    self._Enable(False)

    self._state = _MotorState.RELEASED

  def Touch(self):
    """Controls the motor to touch the button."""
    if self._state == _MotorState.TOUCHED:
      return

    self._Enable(True)
    self._SetDirection(_MotorDirection.DOWN)
    self._Move()
    self._Enable(False)

    self._state = _MotorState.TOUCHED

  def Release(self):
    """Controls the motor to release the button."""
    if self._state == _MotorState.RELEASED:
      return

    self._Enable(True)
    self._SetDirection(_MotorDirection.UP)
    self._Move()
    self._Enable(False)

    self._state = _MotorState.RELEASED

  def _SetDirection(self, direction):
    """Sets motor movement direction.

    Args:
      direction: A direction defined in _MotorDirection.

    Raises:
      MotorError: Unexpected direction.
    """
    # Up: set port to 0.
    # Down: set port to 1.
    value = None
    if direction == _MotorDirection.UP:
      value = 0
    elif direction == _MotorDirection.DOWN:
      value = 1
    else:
      raise MotorError('Unexpected direction: %s' % direction)

    offset = self._ports.direction
    self._motor_io.SetBit(offset, value)

  def _Enable(self, enable):
    """Enables/Disables motor.

    Note this function does not start motor movement. It just turns on motor
    or let it sleep for power saving.

    Args:
      enable: True to enable; False to disable.
    """
    # TODO(cychiang) Find out whether this port works or not.
    # Enable: set port to 0.
    # Disable: set port to 1.
    value = 0 if enable else 1
    offset = self._ports.enable
    self._motor_io.SetBit(offset, value)

  def _Move(self, num_pulse=None):
    """Moves motor by driving pulses on step port.

    Drives num_pulse pulses with each pulse period_ms duration in ms.

    Args:
      num_pulse: Number of pulse to drive motor. If this is None, use
                 num_pulse in self._params.
    """
    offset = self._ports.step
    half_period_sec = self._params.period_ms / 2 * 0.001
    if num_pulse is None:
      num_pulse = self._params.num_pulse

    for _ in xrange(num_pulse):
      self._motor_io.SetBit(offset, self._MOTOR_PULSE_LOW)
      time.sleep(half_period_sec)
      self._motor_io.SetBit(offset, self._MOTOR_PULSE_HIGH)
      time.sleep(half_period_sec)
