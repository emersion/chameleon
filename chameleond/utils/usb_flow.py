# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the interface for usb flows."""

import logging
import tempfile

import chameleon_common #pylint: disable=W0611
from chameleond.utils import system_tools

class USBFlowError(Exception):
  """Exception raised when there is any error in USBFlow."""
  pass


class USBFlow(object):
  """An abstraction for the entire USB flow.

  Properties:
    _port_id: The ID of the input/output connector. Check the value in ids.py.
    _usb_ctrl: An USBController object.
    _subprocess: The subprocess spawned for audio events.
    _supported_data_format: An AudioDataFormat object storing data format
                            supported by the USB driver when it's enabled.
  """

  _VALID_AUDIO_FILE_TYPES = ['wav', 'raw']

  def __init__(self, port_id, usb_ctrl):
    """Initializes USBFlow object with two properties.

    Args:
      port_id: port id that represents the type of port used.
      usb_ctrl: a USBController object that USBFlow objects keep reference to.
    """
    self._port_id = port_id
    self._usb_ctrl = usb_ctrl
    self._subprocess = None
    self._supported_data_format = None

  def Initialize(self):
    """Do nothing here."""
    logging.info('Initialized USB flow #%d.', self._port_id)

  def Select(self):
    """Selects the USB flow."""
    raise NotImplementedError('Select')

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    raise NotImplementedError('GetConnectorType')

  def ResetRoute(self):
    """Resets the audio route."""
    logging.warning('ResetRoute for USBFlow is not implemented. Do nothing.')

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    # TODO
    logging.warning(
        'IsPhysicalPlugged on USBFlow is not implemented.'
        ' Always returns True')
    return True

  def IsPlugged(self):
    """Returns a Boolean value reflecting the status of USB audio gadget driver.

    Returns:
      True if USB audio gadget driver is enabled. False otherwise.
    """
    return self._usb_ctrl.DriverIsEnabled()

  def Plug(self):
    """Emulates plug for USB audio gadget.

    The USB audio gadget driver module is enabled.
    """
    self._usb_ctrl.EnableAudioDriver()

  def Unplug(self):
    """Emulates unplug for USB audio gadget.

    The USB audio gadget driver module is disabled.
    """
    self._usb_ctrl.DisableAudioDriver()

  def Do_FSM(self):
    """Do nothing for USBFlow.

    fpga_tio calls Do_FSM after a flow is selected.
    """
    pass

  def _GetAlsaUtilCommandArgs(self, data_format):
    """Returns a list of parameter flags paired with corresponding arguments.

    The argument values are taken from data_format.

    Args:
      data_format: An AudioDataFormat object whose values are passed as
        arguments into the Alsa util command.

    Returns:
      A list containing argument strings
    """
    params_list = ['-D', 'hw:0,0',
                   '-t', data_format.file_type,
                   '-f', data_format.sample_format,
                   '-c', str(data_format.channel),
                   '-r', str(data_format.rate),]
    return params_list

  @property
  def _subprocess_is_running(self):
    """The subprocess spawned for running a command is running.

    Returns:
      True if subprocess has yet to return a result.
      False if there is no subprocess spawned yet, or if the subprocess has
        returned a value.
    """
    if self._subprocess is None:
      return False

    elif self._subprocess.poll() is None:
      return True

    else:
      return False


class InputUSBFlow(USBFlow):
  """Subclass of USBFlow that handles input audio data.

  Properties:
    _file_path: The file path that captured data will be saved at.
  """

  _DEFAULT_FILE_TYPE = 'wav'

  def __init__(self, *args):
    """Constructs an InputUSBFlow object."""
    super(InputUSBFlow, self).__init__(*args)
    self._file_path = None

  def StartCapturingAudio(self):
    """Starts recording audio data."""
    self._supported_data_format = self._usb_ctrl.GetSupportedCaptureDataFormat()
    params_list = self._GetAlsaUtilCommandArgs(self._supported_data_format)
    file_suffix = '.' + self._supported_data_format.file_type
    recorded_file = tempfile.NamedTemporaryFile(prefix='recorded',
                                                suffix=file_suffix,
                                                delete=False)
    self._file_path = recorded_file.name
    params_list.append(self._file_path)
    self._subprocess = system_tools.SystemTools.RunInSubprocess('arecord',
                                                                *params_list)
    logging.info('Started capturing audio using arecord %s',
                 ' '.join(params_list))

  def StopCapturingAudio(self):
    """Stops recording audio data.

    Returns:
      A tuple (path, format).
      path: The path to the captured audio data.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.

    Raises:
      USBFlowError if this is called before StartCapturingAudio() is called.
    """
    if self._subprocess is None:
      raise USBFlowError('Stop capturing audio before start.')

    elif self._subprocess.poll() is None:
      self._subprocess.terminate()
      logging.info('Stopped capturing audio.')

    return (self._file_path, self._supported_data_format.AsDict())

  @property
  def is_capturing_audio(self):
    """InputUSBFlow is capturing audio.

    Returns:
      True if InputUSBFlow is capturing audio.
    """
    return self._subprocess_is_running

  def Select(self):
    """Selects the USB flow.

    This is a dummy method because USBInputFlow is selected by default.
    """
    logging.info('Select InputUSBFlow for input id #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBIn'


class OutputUSBFlow(USBFlow):
  """Subclass of USBFlow that handles output audio data."""

  def __init__(self, *args):
    """Constructs an OutputUSBFlow object."""
    super(OutputUSBFlow, self).__init__(*args)

  def StartPlayingAudio(self, path, data_format):
    """Starts playing audio data from the path.

    Args:
      path: The path to the audio file for playing.
      data_format: The dict representation of AudioDataFormat. Refer to
        docstring of utils.audio.AudioDataFormat for detail.

    Raises:
      USBFlowError if data format of the file at path does not comply with the
        configurations of the USB driver.
    """
    self._supported_data_format = \
        self._usb_ctrl.GetSupportedPlaybackDataFormat()
    if self._InputDataFormatIsCompatible(data_format):
      data_format_object = audio.CreateAudioDataFormatFromDict(data_format)
      params_list = self._GetAlsaUtilCommandArgs(data_format_object)
      params_list.append(path)
      self._subprocess = system_tools.SystemTools.RunInSubprocess('aplay',
                                                                  *params_list)
      logging.info('Started playing audio using aplay %s',
                   ' '.join(params_list))
    else:
      raise USBFlowError('Data format incompatible with driver configurations')

  def _InputDataFormatIsCompatible(self, data_format_dict):
    """Checks whether data_format_dict passed in matches supported data format.

    This method checks the 'file_type' field separately from the other three
    fields in the data_format_dict passed in, because _supported_data_format
    gathered from _usb_ctrl does not keep track of the playback file type.

    This method should be called after _supported_data_format is set to the
    correct supported data format from _usb_ctrl in preparation for playing
    audio.

    Args:
      data_format_dict: A dictionary in the format of an AudioDataFormat object
        that is passed in by the user.

    Returns:
      True if data_format_dict corresponds to supported format from _usb_ctrl
        and file_type is valid. False otherwise.
    """
    supported_format_dict = self._supported_data_format.AsDict()
    for key, value in data_format_dict.iteritems():
      if key == 'file_type':
        if value not in self._VALID_AUDIO_FILE_TYPES:
          return False
      elif value != supported_format_dict[key]:
        return False
    return True

  def StopPlayingAudio(self):
    """Stops playing audio data.

    Raises:
      USBFlowError if this is called before StartPlayingAudio() is called.
    """
    if self._subprocess is None:
      raise USBFlowError('Stop playing audio before Start')

    elif self._subprocess.poll() is None:
      self._subprocess.terminate()
      logging.info('Stopped playing audio.')

  @property
  def is_playing_audio(self):
    """OutputUSBFlow is playing audio.

    Returns:
      True if OutputUSBFlow is playing audio.
    """
    return self._subprocess_is_running

  def Select(self):
    """Selects the USB flow.

    This is a dummy method because USBOutputFlow is selected by default.
    """
    logging.info('Select OutputUSBFlow for input id #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBOut'
