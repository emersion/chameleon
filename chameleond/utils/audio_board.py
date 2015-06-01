# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module provides interface to control audio board."""

import logging
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c
from chameleond.utils import io


class _AudioBoardIOController(object):
  """Controls I/O expanders on audio board.

  There are three I/O expanders on i2c bus 3,
  address 0x20, 0x21, 0x22. Each I/O expander has 16 bits.
  Some of the bits are set as output to control compoments on audio board.
  Some of the bits are set as input to read status.
  Other bits are left untouched.
  This class provides the interface to control output or read input on certain
  bit of certian I/O expander.
  """
  def __init__(self, i2c_bus):
    """Constructs an _AudioBoardIOController.

    Args:
      i2c_bus: The I2cBus object.
    """
    self._io_expanders = [
        io.IoExpander(i2c_bus, io.IoExpander.SLAVE_ADDRESSES[0]),
        io.IoExpander(i2c_bus, io.IoExpander.SLAVE_ADDRESSES[1]),
        io.IoExpander(i2c_bus, io.IoExpander.SLAVE_ADDRESSES[2])]

    for io_expander in self._io_expanders:
      i2c_bus.AddSlave(io_expander)

    self._ResetDirections()
    logging.info('_AudioBoardIOController initialized')

  def _ResetDirections(self):
    """Resets all ports to be input."""
    for expander in self._io_expanders:
      expander.SetDirection(0xffff)

  def SetBit(self, index, offset, value):
    """Sets a bit as output and sets its value to 1 or 0.

    Args:
      index: The index number of I/O expander.
      offset: The bit offset 0x0 to 0xf.
      value: 1 or 0.
    """
    logging.info('Set I/O expander #%d, bit offset 0x%x to %d',
                 index, offset, value)
    self._io_expanders[index].SetBit(offset, value)

  def ReadBit(self, index, offset):
    """Sets a bit as input and reads its value.

    Args:
      index: The index number of I/O expander.
      offset: The bit offset 0x0 to 0xf.

    Returns:
      1 or 0.
    """
    return self._io_expanders[index].ReadBit(offset)

  def ReadOutputBit(self, index, offset):
    """Reads current value of an output bit.

    Args:
      index: The index number of I/O expander.
      offset: The bit offset 0x0 to 0xf.

    Returns:
      1 or 0.
    """
    return self._io_expanders[index].ReadOutputBit(offset)


class _AudioBoardSwitchController(object):
  """Controls switches on audio board.

  There are 18 switches for audio board controlling.
  The switches are controlled through _AudioBoardIOController,
  This class provides the interface to toggle switches on/off.
  Here is the table of bit location of each switch:

  ===============================

  I/O expander 0: address 0x20

  bit     15 14 13 12 11 10  9  8
  -------------------------------
  switch  16 15 14 13 12 11 10  9

  bit      7  6  5  4  3  2  1  0
  -------------------------------
  switch   8  7        4  3  2  1

  ===============================

  I/O expander 1: address 0x21

  bit      7  6  5  4  3  2  1  0
  -------------------------------
  switch                       17

  ===============================

  I/O expander 2: address 0x22

  bit      7  6  5  4  3  2  1  0
  -------------------------------
  switch        25          19 18

  ===============================
  """
  # The mapping from switch number to expander index and bit offset.
  # E.g., switch 8 is controlled by the first I/O expander at bit offset 7.
  _SWITCH_EXPANDER_BIT_MAP = {
      1: (0, 0),
      2: (0, 1),
      3: (0, 2),
      4: (0, 3),
      7: (0, 6),
      8: (0, 7),
      9: (0, 8),
      10: (0, 9),
      11: (0, 10),
      12: (0, 11),
      13: (0, 12),
      14: (0, 13),
      15: (0, 14),
      16: (0, 15),
      17: (1, 0),
      18: (2, 0),
      19: (2, 1),
      25: (2, 5)}

  def __init__(self, io_controller):
    """Constructs an _AudioBoardSwitchController.

    Args:
      io_controller: An _AudioBoardIOController object.
    """
    self._io_controller = io_controller
    self._ResetSwitches()

    logging.info('_AudioBoardSwitchController initialized')

  def _ResetSwitches(self):
    """Turns off all switches."""
    for number in self._SWITCH_EXPANDER_BIT_MAP.iterkeys():
      self.EnableSwitch(number, False)

  def EnableSwitch(self, number, enabled):
    """Enables/disables a switch.

    Args:
      number: The switch number.
      enabled: True to enable switch. False otherwise.
    """
    logging.info('Set switch %d to %s', number, enabled)
    index, offset = self._SWITCH_EXPANDER_BIT_MAP[number]
    self._io_controller.SetBit(index, offset, 1 if enabled else 0)


class _JackPluggerException(Exception):
  """Error in _JackPlugger."""
  pass


class _JackPlugger(object):
  """Controls jack plugger.

  There is a motor in the audio box which can plug/unplug 3.5mm 4-ring
  audio cable to/from audio jack of Cros deivce.
  This motor is controlled by audio board using 4 pins.
  The pins are controlled by the I/O expander on i2c bus 3,
  address 0x21, which is the I/O expander with index 1 in
  _AudioBoardIOController.
  This class provides the interface to plug/unplug 3.5mm 4-ring
  audio cable to/from audio jack.

  Here is the table of bit location.

  =================================

  I/O expander 1: address 0x21

  bit      11     10      9      8
  ---------------------------------
  pin   stat1  stat0   cmd1   cmd0

  =================================

  The usages of 4 pins are defined as followes.

  cmd0, cmd1 to set motor action.

  cmd0   cmd1         action
  --------------------------
     0      1         plug
     1      0         unplug

  stat0, stat1 to read current status reported from the motor.

  stat0 stat1         status
  --------------------------
     0      1         plug
     1      0         unplug

  """
  # The I/O expander index is 1.
  _INDEX = 1
  # The mapping from register name to bit offset.
  _BIT_MAP = {
      'cmd0':  8,
      'cmd1':  9,
      'stat0': 10,
      'stat1': 11}

  _SLEEP_AFTER_COMMAND_SECONDS = 2

  def __init__(self, io_controller):
    """Constructs an _JackPlugger.

    Args:
      io_controller: An _AudioBoardIOController object.
    """
    self._io_controller = io_controller
    self.Reset()

    logging.info('_JackPlugger initialized')

  def Reset(self):
    """Unplugs the jack and checks status."""
    self.SetPlugStateAndCheck(False)

  def _SetPlugState(self, plug):
    """Sets plugger state.

    Args:
      plug: True to plug. False otherwise.
    """
    if plug:
      values = (0, 1)
    else:
      values = (1, 0)

    self._io_controller.SetBit(self._INDEX, self._BIT_MAP['cmd0'], values[0])
    self._io_controller.SetBit(self._INDEX, self._BIT_MAP['cmd1'], values[1])

  def _GetPlugState(self):
    """Gets plugger current state.

    Returns:
      Plugger status. True if plugged, False otherwise.

    Raises:
      _JackPluggerException if motor status can not be queried.
    """
    value0 = self._io_controller.ReadBit(self._INDEX, self._BIT_MAP['stat0'])
    value1 = self._io_controller.ReadBit(self._INDEX, self._BIT_MAP['stat1'])

    logging.info('Read motor status %r, %r', value0, value1)
    if (value0, value1) == (0, 1):
      return True
    elif (value0, value1) == (1, 0):
      return False
    else:
      raise _JackPluggerException('Can not get motor status')

  def SetPlugStateAndCheck(self, plug):
    """Plugs/unplugs audio jack and checks motor status.

    Args:
      plug: True to plug. False otherwise.

    Raises:
      _JackPluggerException if motor status does not meet the condition.
    """
    logging.info('Set plugger state to %s', 'Plug' if plug else 'Unplug')
    self._SetPlugState(plug)
    time.sleep(self._SLEEP_AFTER_COMMAND_SECONDS)
    if self._GetPlugState() != plug:
      raise _JackPluggerException(
          'The motor plug status is not %s' % 'Plug' if plug else 'Unplug')


class _BluetoothController(object):
  """Controls bluetooth module on audio board.

  There is a bluetooth module on audio board.
  The pins are controlled by the I/O expander on i2c bus 3,
  address 0x21, which is the I/O expander with index 1 in
  _AudioBoardIOController.
  This class provides the interface to control bluetooth module.

  Here is the table of bit location.

  ==================================================

  I/O expander 1: address 0x21

  bit           7           6           5          4
  --------------------------------------------------
  pin       reset volume down   volume up    forward

  bit           3           2           1          0
  --------------------------------------------------
  pin    backward   play/stop

  ==================================================

  """
  # The I/O expander index is 1.
  _INDEX = 1
  # The mapping from register name to bit offset.
  # TODO(cychiang) implement play/forward/backward/volume functions.
  _BIT_MAP = {'reset': 7}

  def __init__(self, io_controller):
    """Constructs an _BluetoothController.

    Args:
      io_controller: An _AudioBoardIOController object.
    """
    self._io_controller = io_controller
    self.Reset()

    logging.info('_BluetoothController initialized')

  def _SetResetPin(self, value):
    """Sets reset pin value.

    Args:
      value: 0 or 1.
    """
    self._io_controller.SetBit(self._INDEX, self._BIT_MAP['reset'], value)

  def Disable(self):
    """Disables bluetooth module by holding the reset bit.

    This bluetooth module does not support disconnect command from module side.
    Once bluetooth module is disabled, bluetooth adapter will notice this
    bluetooth module is lost after a timeout. On Cros, this timeout duration is
    60 seconds.
    """
    self._SetResetPin(0)

  def Reset(self):
    """Resets bluetooth module.

    After reset, it takes about 20 seconds for bluetooth module to become
    available for connection. Connection attempt results in "Device or resource
    busy" error during this time window.
    """
    self._SetResetPin(0)
    self._SetResetPin(1)

  def IsEnabled(self):
    """Checks if bluetooth module is enabled.

    Bluetooth module is enabled when reset pin is not hold to 0.

    Returns:
      True if bluetooth module is enabled. False otherwise.
    """
    return (self._io_controller.ReadOutputBit(
        self._INDEX, self._BIT_MAP['reset']) == 1)


class AudioBusEndpointException(Exception):
  """Exception in AudioBusEndpoint."""
  pass


class AudioBusEndpoint(object):
  """Endpoints on audio bus.

  There are four terminals on audio bus. Each terminal has two endpoints of two
  roles, that is, one source and one sink. The role of the
  endpoint is determined from the point of view of audio signal on the audio
  bus. For example, headphone is seen as an output port on Cros device, but
  it is a source endpoint for audio signal on the audio bus.

  Endpoints can be connected to audio bus independently. But in usual cases,
  an audio bus should have no more than one source at a time.

  The following table lists the role of each endpoint.

  Terminal               Endpoint               role
  ---------------------------------------------------------------
  Cros device            Heaphone               source
  Cros device            External Microphone    sink
  Peripheral device      Microphone             source
  Peripheral device      Speaker                sink
  Chameleon FPGA         LineOut                source
  Chameleon FPGA         LineIn                 sink
  Bluetooth module       Output port            source
  Bluetooth module       Input port             sink

                         Peripheral device
                          o  o       o  o

         o                     bus 1                          o
  Cros   o <================================================> o   Chameleon
  device o <================================================> o   FPGA
         o                     bus 2                          o

                          o  o       o  o
                         Bluetooth module

  Each source/sink endpoint has two switches to control the connection
  on audio bus 1 and audio bus 2. So in total there are 16 switches for 8
  endpoints.
  """
  CROS_HEADPHONE = 'Cros device headphone'
  CROS_EXTERNAL_MICROPHONE = 'Cros device external microphone'
  PERIPHERAL_MICROPHONE = 'Peripheral microphone'
  PERIPHERAL_SPEAKER = 'Peripheral speaker'
  FPGA_LINEOUT = 'Chameleon FPGA line-out'
  FPGA_LINEIN = 'Chameleon FPGA line-in'
  BLUETOOTH_OUTPUT = 'Bluetooth module output'
  BLUETOOTH_INPUT = 'Bluetooth module input'


AUDIO_BUS_SOURCES = [AudioBusEndpoint.CROS_HEADPHONE,
                     AudioBusEndpoint.PERIPHERAL_MICROPHONE,
                     AudioBusEndpoint.FPGA_LINEOUT,
                     AudioBusEndpoint.BLUETOOTH_OUTPUT]

AUDIO_BUS_SINKS = [AudioBusEndpoint.CROS_EXTERNAL_MICROPHONE,
                   AudioBusEndpoint.PERIPHERAL_SPEAKER,
                   AudioBusEndpoint.FPGA_LINEIN,
                   AudioBusEndpoint.BLUETOOTH_INPUT]

AUDIO_BUS_ENDPOINTS = AUDIO_BUS_SOURCES + AUDIO_BUS_SINKS


def IsSource(endpoint):
  """Checks if an endpoint is a signal source.

  Args:
    endpoint: An endpoint defined in AudioBusEndpoint.

  Returns:
    True if the endpoint is a source. False if it is a sink.

  Raises:
    AudioBusEndpointException if endpoint is not valid.
  """
  if endpoint in AUDIO_BUS_SOURCES:
    return True
  elif endpoint in AUDIO_BUS_SINKS:
    return False
  else:
    raise AudioBusEndpointException('%s is not a valid endpoint' % endpoint)


class _AudioBusException(Exception):
  """Exception in _AudioBus."""
  pass


class _AudioBus(object):
  """Abstracts an audio bus.

  An audio bus adds or removes endpoints by toggling the switches which connects
  the corresponding endpoints to audio bus.
  The following table contains 16 switches of different endpoints of two buses.

  endpoint                        bus1    bus2
  ---------------------------------------------
  CROS_HEADPHONE                  sw1     sw2
  PERIPHERAL_MICROPHONE           sw9     sw10
  FPGA_LINEOUT                    sw11    sw12
  BLUETOOTH_OUTPUT                sw15    sw16

  CROS_EXTERNAL_MICROPHONE        sw3     sw4
  PERIPHERAL_SPEAKER              sw7     sw8
  FPGA_LINEIN                     sw13    sw14
  BLUETOOTH_INPUT                 sw17    sw18
  """
  # Contains the mapping from bus and endpoint to switch number.
  # E.g. The switch number of Cros device headphone on bus 1 is looked up
  # by
  # _SWITCH_MAP[1][AudioBusEndpoint.CROS_HEADPHONE] = 1
  _SWITCH_MAP = {
      1: {
          AudioBusEndpoint.CROS_HEADPHONE: 1,
          AudioBusEndpoint.PERIPHERAL_MICROPHONE: 9,
          AudioBusEndpoint.FPGA_LINEOUT: 11,
          AudioBusEndpoint.BLUETOOTH_OUTPUT: 15,
          AudioBusEndpoint.CROS_EXTERNAL_MICROPHONE: 3,
          AudioBusEndpoint.PERIPHERAL_SPEAKER: 7,
          AudioBusEndpoint.FPGA_LINEIN: 13,
          AudioBusEndpoint.BLUETOOTH_INPUT: 17,
      },
      2: {
          AudioBusEndpoint.CROS_HEADPHONE: 2,
          AudioBusEndpoint.PERIPHERAL_MICROPHONE: 10,
          AudioBusEndpoint.FPGA_LINEOUT: 12,
          AudioBusEndpoint.BLUETOOTH_OUTPUT: 16,
          AudioBusEndpoint.CROS_EXTERNAL_MICROPHONE: 4,
          AudioBusEndpoint.PERIPHERAL_SPEAKER: 8,
          AudioBusEndpoint.FPGA_LINEIN: 14,
          AudioBusEndpoint.BLUETOOTH_INPUT: 18,
      }
  }

  def __init__(self, switch_controller, bus_number):
    """Constructs an audio bus.

    Args:
      switch_controller: An _AudioBoardSwitchController object.
      bus_number: 1 or 2 for bus number.
    """
    self._switch_controller = switch_controller
    self._bus_number = bus_number
    self._sources = set()
    self._sinks = set()
    self.Reset()
    logging.info('Audio bus %d initialized', self._bus_number)

  def Reset(self):
    """Disconnects all endpoints from audio bus."""
    for endpoint in AUDIO_BUS_ENDPOINTS:
      self.Disconnect(endpoint)

  def Connect(self, endpoint):
    """Connects an endpoint to audio bus.

    Args:
      endpoint: An endpoint defined in AudioBusEndpoint.
    """

    is_source = IsSource(endpoint)
    logging.info('Connect %s as signal %s to audio bus %d', endpoint,
                 'source' if is_source else 'sink', self._bus_number)

    if is_source:
      self._sources.add(endpoint)
    else:
      self._sinks.add(endpoint)

    switch_number = self._SWITCH_MAP[self._bus_number][endpoint]
    self._switch_controller.EnableSwitch(switch_number, True)

  def Disconnect(self, endpoint):
    """Disconnects an endpoint from audio bus.

    Args:
      endpoint: An endpoint defined in AudioBusEndpoint.

    Raises:
      _AudioBusException: If endpoint is not valid.
    """
    is_source = IsSource(endpoint)
    logging.info('Disconnect %s as signal %s from audio bus %d', endpoint,
                 'source' if is_source else 'sink', self._bus_number)

    if is_source:
      self._sources.discard(endpoint)
    else:
      self._sinks.discard(endpoint)

    switch_number = self._SWITCH_MAP[self._bus_number][endpoint]
    self._switch_controller.EnableSwitch(switch_number, False)

  def GetSources(self):
    """Gets the current source endpoints.

    Returns:
      A list of current source endpoints connected to audio bus.
    """
    return list(self._sources)

  def GetSinks(self):
    """Gets the current source sinks.

    Returns:
      A list of current sink endpoints connected to audio bus.
    """
    return list(self._sinks)


class AudioBoardException(Exception):
  """Errors in AudioBoard."""


class AudioBoard(object):
  """A class to control audio board.

  The audio functions includes:
  1. Audio source/sink routing on audio bus 1 and 2.
  2. TODO (cychiang) Audio jack mode switching between LRGM and LRMG.
  3. Audio jack plug/unplug control if audio board is connected to motor
     in audio box.
  4. TODO (cychiang) Audio button function switching.
  5. TODO (cychiang) Audio button press control.

  """
  def __init__(self, i2c_bus):
    """Runs the initialization sequence for the audio board.

    Args:
      i2c_bus: The I2cBus object.

    Raises:
      AudioBoardException: If audio board can not be initialized.
    """
    try:
      io_controller = _AudioBoardIOController(i2c_bus)
      self._switch_controller = _AudioBoardSwitchController(io_controller)
      self._audio_buses = {
          1: _AudioBus(self._switch_controller, 1),
          2: _AudioBus(self._switch_controller, 2)}
    except i2c.I2cBusError:
      logging.error('Can not access I2c bus at %#x on audio board.',
                    i2c_bus.base_addr)
      raise AudioBoardException('Can not initialize audio board')
    try:
      self._jack_plugger = _JackPlugger(io_controller)
    except _JackPluggerException:
      logging.error('Can not access jack plugger.')
      self._jack_plugger = None

    self._bluetooth_ctrl = _BluetoothController(io_controller)

    logging.info('Audio board initialized')

  def Reset(self):
    """Resets audio buses."""
    for bus in self._audio_buses.values():
      bus.Reset()
    if self.HasJackPlugger():
      self._jack_plugger.Reset()

  def SetConnection(self, bus_number, endpoint, enabled):
    """Connects or disconnects an endpoint on an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in AudioBusEndpoint.
      enabled: True to connect, False to disconnect.
    """
    is_source = IsSource(endpoint)
    logging.info('%s connection of %s as signal %s to audio bus %s',
                 'Enable' if enabled else 'Disable', endpoint,
                 'source' if is_source else 'sink', bus_number)
    if enabled:
      self._audio_buses[bus_number].Connect(endpoint)
    else:
      self._audio_buses[bus_number].Disconnect(endpoint)

  def IsConnected(self, bus_number, endpoint):
    """Checks if an endpoint is connected to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in AudioBusEndpoint.

    Returns:
      True if the endpoint is connected to the audio bus. False otherwise.
    """
    audio_bus = self._audio_buses[bus_number]
    if IsSource(endpoint):
      return endpoint in audio_bus.GetSources()
    else:
      return endpoint in audio_bus.GetSinks()

  def GetConnections(self, bus_number):
    """Gets current sources and sinks on an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.

    Returns:
      A tuple (sources, sinks) where sources is a list of current source
      endpoints connected to audio bus, and sinks is a list of current
      endpoints connected to audio bus.
    """
    audio_bus = self._audio_buses[bus_number]
    return audio_bus.GetSources(), audio_bus.GetSinks()

  def ResetConnections(self, bus_number):
    """Resets connections on audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
    """
    self._audio_buses[bus_number].Reset()

  def HasJackPlugger(self):
    """If this audio board has jack plugger.

    Returns:
      True if this audio board has jack plugger. False otherwise.
    """
    return self._jack_plugger is not None

  def SetJackPlugger(self, enabled):
    """Sets jack plugger status.

    Args:
      enabled: True to plug, False otherwise.

    Raises:
      AudioBoardException if there is no jack plugger on this audio board.
    """
    if not self.HasJackPlugger():
      raise AudioBoardException('There is no jack plugger on this audio board.')
    self._jack_plugger.SetPlugStateAndCheck(enabled)

  def ResetBluetooth(self):
    """Resets bluetooth module."""
    self._bluetooth_ctrl.Reset()

  def DisableBluetooth(self):
    """Disables bluetooth module."""
    self._bluetooth_ctrl.Disable()

  def IsBluetoothEnabled(self):
    """Checks if bluetooth is enabled.

    Returns:
      True if bluetooth module is enabled. False otherwise.
    """
    return self._bluetooth_ctrl.IsEnabled()
