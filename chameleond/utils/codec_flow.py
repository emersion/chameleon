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
    _port_id: The ID of the input/output connector. Check the value in ids.py.
    _fpga: An FpgaController object.
    _audio_codec: A codec.AudioCodec object.
  """
  _CODEC_INPUTS = {
      ids.MIC: codec.CodecInput.MIC,
      ids.LINEIN: codec.CodecInput.LINEIN
  }
  _CODEC_OUTPUTS = {
      ids.LINEOUT: codec.CodecOutput.LINEOUT
  }

  def __init__(self, port_id, codec_i2c_bus, fpga_ctrl):
    """Constructs a CodecFlow object.

    Args:
      port_id: The ID of the input/output connector. Check the value in ids.py.
      codec_i2c_bus: The I2cBus object for codec.
      fpga_ctrl: The FpgaController object.
    """
    self._port_id = port_id
    self._fpga = fpga_ctrl
    self._audio_codec = codec_i2c_bus.GetSlave(
       codec.AudioCodec.SLAVE_ADDRESSES[0])

  def Initialize(self):
    """Initializes codec."""
    logging.info('Initialize CodecFlow #%d.', self._port_id)
    self._audio_codec.Initialize()

  def Select(self):
    """Selects the codec flow to set the proper codec path and FPGA paths."""
    raise NotImplementedError('Select')

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    raise NotImplementedError('GetConnectorType')

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning(
        'IsPhysicalPlugged on CodecFlow is not implemented.'
        ' Always returns True')
    return True

  def IsPlugged(self):
    """Returns true if audio codec is emualted plug."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning('Always return True for IsPlugged on AudioCodecInputFlow.')
    return True

  def Plug(self):
    """Emulates plug on audio codec."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning(
        'Plug on AudioCodecInputFlow is not implemented. Do nothing.')

  def Unplug(self):
    """Emulates unplug on audio codec."""
    # TODO(cychiang): Implement this using audio board interface.
    logging.warning(
        'Unplug on CodecFlow is not implemented. Do nothing.')

  def Do_FSM(self):
    """fpga_tio calls Do_FSM after a flow is selected. Do nothing for codec."""
    pass


class InputCodecFlow(CodecFlow):
  """CodecFlow for input port.

  Properties:
    _audio_capture_manager: An AudioCaptureManager object which controls audio
      data capturing using AudioDumper in FPGAController.
  """
  def __init__(self, *args):
    """Constructs an InputCodecFlow object."""
    super(InputCodecFlow, self).__init__(*args)
    self._audio_capture_manager = audio_utils.AudioCaptureManager(
        self._fpga.adump)

  def Select(self):
    """Selects the codec flow to set the proper codec path and FPGA paths."""
    logging.info('Select InputCodecFlow for input id #%d.', self._port_id)
    self._fpga.asrc.SelectFromInput(self._port_id)
    self._audio_codec.SelectInput(self._CODEC_INPUTS[self._port_id])

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return self._CODEC_INPUTS[self._port_id]

  @property
  def is_capturing_audio(self):
    """InputCodecFlow is capturing audio.

    Returns:
      True if InputCodecFlow is capturing audio.
    """
    return self._audio_capture_manager.is_capturing

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


class OutputCodecFlow(CodecFlow):
  """CodecFlow for output port.

  Properties:
    _audio_stream_manager: An AudioStreamManager object which controls audio
      data streaming using AudioStreamController in FPGAController.
  """
  def __init__(self, *args):
    """Constructs an OutputCodecFlow object."""
    super(OutputCodecFlow, self).__init__(*args)
    self._audio_stream_manager = audio_utils.AudioStreamManager(
        self._fpga.astream)
    self._fpga.aiis.Disable()

  def Select(self):
    """Selects the codec flow to set the proper codec path and FPGA paths."""
    logging.info('Select OutputFlow #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return self._CODEC_OUTPUTS[self._port_id]

  def StartPlayingEcho(self, source_id):
    """Echoes audio data from source_id.

    Echoes audio data received from source id.

    Args:
      source_id: The ID of the input connector. Check the value in ids.py.
    """
    logging.info('Start OutputFlow #%d to echo input source #%d.',
                  self._port_id, source_id)
    self._fpga.asrc.SelectFromInput(source_id)
    self._fpga.aiis.Enable()

  def StartPlayingAudioData(self, audio_data):
    """Starts playing audio_data.

    Currently AudioStreamManager only accepts data format if it is identical
    to audio.AudioDataFormat(
      file_type='raw', sample_format='S32_LE', channel=8, rate=48000)

    Args:
      audio_data: A tuple (data, format).
        data: The audio data to play.
        format: The dict representation of AudioDataFormat. Refer to docstring
          of utils.audio.AudioDataFormat for detail.
    """
    self._fpga.asrc.SelectMemory()
    self._fpga.aiis.Enable()
    self._audio_stream_manager.StartPlayingAudio(audio_data)

  @property
  def is_playing_audio_from_memory(self):
    """OutputCodecFlow is playing audio from memory.

    Returns:
      True if OutputCodecFlow is playing audio from memory.
    """
    return self._audio_stream_manager.is_streaming

  def StopPlayingAudio(self):
    """Stops playing audio for both echo and streaming."""
    self._fpga.aiis.Disable()
    self._audio_stream_manager.StopPlayingAudio()
