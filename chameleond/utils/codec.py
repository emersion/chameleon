# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Audio codec modules."""

import logging
import time

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import i2c_fpga


class CodecInput(object):
  """Available audio codec input options."""
  NONE = 'None'
  MIC = 'Mic'
  LINEIN = 'LineIn'


class AudioCodecException(Exception):
  """Exception raised when any error in AudioCodec."""
  pass


class AudioCodec(i2c_fpga.I2cSlave):
  """A class to control SSM2603 audio codec on chameleon."""

  SLAVE_ADDRESSES = (0x1a,)

  def Initialize(self):
    """Runs the initialization sequence for the chip."""
    if self._Enabled():
      logging.info('Already enabled')
      return
    logging.info('Initialize audio codec chip.')
    self.Set(0x17, 0x0c) # power on clock, crystal, dac
    self.Set(0x12, 0x08) # select dac, no line-in bypass
    self.Set(0x00, 0x0a) # dac no mute
    self.Set(0x00, 0x10) # SR=0000, 48k, MCLK/256
    time.sleep(0.073)           # 10.1uF on VMID, 73ms needed
    self.Set(0x01, 0x12) # activate digital core
    self.Set(0x07, 0x0c) # power on output
    logging.info('Wait for audio codec chip to turn on...')
    while not self._Enabled():
      time.sleep(0.1)
    logging.info('Audio codec chip turned on')
    self._SelectInputNone()

  def _Enabled(self):
    """Checks if codec is already enabled."""
    return (self.Get(0x0c) & 0x80) == 0

  def SelectInput(self, input_path):
    """Selects an input path.

    By selecting an input path, codec will start recording data from that path
    and output to CODEC input of AudioSourceController.

    Args:
      input_path: NONE, MIC, or LINEIN in CodecInput

    Raises:
      AudioCodecException if input_path is not valid.
    """
    if not self._Enabled():
      raise AudioCodecException('Codec is not initialized')
    if input_path == CodecInput.NONE:
      self._SelectInputNone()
    elif input_path == CodecInput.MIC:
      self._SelectInputMic()
    elif input_path == CodecInput.LINEIN:
      self._SelectInputLineIn()
    else:
      raise AudioCodecException('%s is not a valid input' % input_path)

  def _SelectInputNone(self):
    """Disables recording from MIC nor LINEIN."""
    logging.info('Select input to NONE on codec chip.')
    self.Set(0x97, 0x00)  # mute left linein
    self.Set(0x97, 0x02)  # mute right linein
    self.Set(0x12, 0x08)  # select linein
    self.Set(0x07, 0x0c)  # disable adc/mic/linein

  def _SelectInputMic(self):
    """Starts recording from MIC."""
    logging.info('Select input to MIC on codec chip.')
    self.Set(0x97, 0x00) # mute left linein
    self.Set(0x97, 0x02) # mute right linein
    self.Set(0x14, 0x08) # select mic
    self.Set(0x01, 0x0c) # enable adc and mic

  def _SelectInputLineIn(self):
    """Starts recording from LINEIN."""
    logging.info('Select input to LINEIN on codec chip.')
    self.Set(0x17, 0x00) # enable left linein
    self.Set(0x17, 0x02) # enable right linein
    self.Set(0x12, 0x08) # select linein
    self.Set(0x02, 0x0c) # enable adc and linein
