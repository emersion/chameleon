# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Codec flow module which abstracts the entire flow for codec input/output."""

import logging

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import audio_utils
from chameleond.utils import codec
from chameleond.utils import ids


class CodecFlowError(Exception):
  """Exception raised when any error on CodecFlow."""
  pass


class CodecFlow(object):
  """An abstraction of the entire flow for audio codec.

  It provides the basic interfaces of Chameleond driver for a specific
  input/output using codec. Using this abstraction, each flow can have its
  own behavior. No need to share the same Chameleond driver code.

  Codec connection includes
    input: LINEIN, MIC
    output: LINEOUT.

  Properties:
      _input_id: The ID of the input connector. Check the value in ids.py.
      _fpga: A FpgaController object.
      _audio_codec: A codec.AudioCodec object.
      _audio_capture_manager: A AudioCaptureManager object which controls audio
        data capturing using AudioDumper in FPGAController.
  """
  _CONNECTOR_TYPE = 'Codec Unknown Input/Output'
  _CODEC_INPUTS = {
      ids.MIC: codec.CodecInput.MIC,
      ids.LINEIN: codec.CodecInput.LINEIN
  }
  def __init__(self, input_id, codec_i2c_bus, fpga_ctrl):
    """Constructs an CodecInputFlow object.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
      codec_i2c_bus: The I2cBus object for codec.
      fpga_ctrl: The FpgaController object.
    """
    self._input_id = input_id
    self._fpga = fpga_ctrl
    self._audio_codec = codec_i2c_bus.GetSlave(
       codec.AudioCodec.SLAVE_ADDRESSES[0])
    self._audio_capture_manager = audio_utils.AudioCaptureManager(
        self._fpga.adump)

  def Initialize(self):
    """Initializes codec."""
    logging.info('Initialize InputFlow #%d.', self._input_id)
    self._audio_codec.Initialize()

  def Select(self):
    """Selects the codec flow to set the proper codec path and FPGA paths."""
    logging.info('Select InputFlow #%d.', self._input_id)
    self._fpga.asrc.Select(self._input_id)
    self._audio_codec.SelectInput(self._CODEC_INPUTS[self._input_id])
    # TODO(cychiang): Handle output case for ids.LINEOUT

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning(
        'IsPhysicalPlugged on AudioCodecInputFlow is not implemented.'
        ' Always returns True')
    return True

  def Unplug(self):
    """Emulates unplug on audio codec."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning(
        'Unplug on AudioCodecInputFlow is not implemented. Do nothing.')

  def Do_FSM(self):
    """fpga_tio calls Do_FSM after a flow is selected. Do nothing for codec."""
    pass

  def StartCapturingAudio(self):
    """Starts capturing audio."""
    self._audio_capture_manager.StartCapturingAudio()

  def StopCapturingAudio(self):
    """Stops capturing audio.

    Returns:
      A tuple (data, format).
      data: The captured audio data.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.

    Raises:
      AudioCaptureManagerError: If captured time or page exceeds the limit.
      AudioCaptureManagerError: If there is no captured data.
    """
    return self._audio_capture_manager.StopCapturingAudio()
