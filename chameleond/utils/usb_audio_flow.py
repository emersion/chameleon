# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the interface for usb audio flows."""

import logging
import tempfile

import chameleon_common #pylint: disable=W0611
from chameleond.utils import audio
from chameleond.utils import system_tools

class USBAudioFlowError(Exception):
  """Exception raised when there is any error in USBAudioFlow."""
  pass


class USBAudioFlow(object):
  """An abstraction for the entire USB Audio flow.

  Properties:
    _port_id: The ID of the input/output connector. Check the value in ids.py.
    _usb_ctrl: An USBAudioController object.
    _subprocess: The subprocess spawned for audio events.
    _supported_data_format: An AudioDataFormat object storing data format
                            supported by the USB driver when it's enabled.
  """

  _VALID_AUDIO_FILE_TYPES = ['wav', 'raw']

  def __init__(self, port_id, usb_ctrl):
    """Initializes USBAudioFlow object with two properties.

    Args:
      port_id: port id that represents the type of port used.
      usb_ctrl: a USBAudioController object that USBAudioFlow objects keep
          reference to.
    """
    self._port_id = port_id
    self._usb_ctrl = usb_ctrl
    self._subprocess = None
    self._supported_data_format = None

  def Initialize(self):
    """Enables USB port controller.

    Enables USB port device mode controller so USB host on the other side will
    not get confused when trying to enumerate this USB device.
    """
    self._usb_ctrl.EnableUSBOTGDriver()
    logging.info('Initialized USB Audio flow #%d.', self._port_id)

  def Select(self):
    """Selects the USB Audio flow."""
    raise NotImplementedError('Select')

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    raise NotImplementedError('GetConnectorType')

  def ResetRoute(self):
    """Resets the audio route."""
    logging.warning(
        'ResetRoute for USBAudioFlow is not implemented. Do nothing.')

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    # TODO
    logging.warning(
        'IsPhysicalPlugged on USBAudioFlow is not implemented.'
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

    Enables audio gadget driver.
    """
    self._usb_ctrl.EnableDriver()

  def Unplug(self):
    """Emulates unplug for USB audio gadget.

    Disables audio gadget driver.
    """
    self._usb_ctrl.DisableDriver()

  def DoFSM(self):
    """Do nothing for USBAudioFlow.

    fpga_tio calls DoFSM after a flow is selected.
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


class InputUSBAudioFlow(USBAudioFlow):
  """Subclass of USBAudioFlow that handles input audio data.

  Properties:
    _file_path: The file path that captured data will be saved at.
    _captured_file_type: The file type that captured data will be saved in.
  """

  _DEFAULT_FILE_TYPE = 'raw'

  def __init__(self, *args):
    """Constructs an InputUSBAudioFlow object."""
    super(InputUSBAudioFlow, self).__init__(*args)
    self._file_path = None
    self._captured_file_type = self._DEFAULT_FILE_TYPE

  def SetDriverCaptureConfigs(self, capture_data_format):
    """Sets USB driver capture configurations in AudioDataFormat form.

    The 'file_type' field in the capture_data_format is not relevant to USB
    driver configurations, but is used by InputUSBFlow as _captured_file_type
    for saving captured data. This field is checked against a list of valid file
    types accepted by USBAudioFlow. If file_type is not valid, an exception is
    raised.

    Capture configs can still be set even when the flow is plugged in. See
    docstring of USBAudioController.SetDriverCaptureConfigs for more details.

    Args:
      capture_data_format: The dict form of an AudioDataFormat object.

    Raises:
      USBAudioFlowError if this InputUSBAudioFlow is still capturing audio when
        this method is called, or if file_type specified in capture_data_format
        is not valid.
    """
    if self.is_capturing_audio:
      error_message = ('Driver configs should remain unchanged while USB Audio'
                       'Flow is capturing audio.')
      raise USBAudioFlowError(error_message)
    capture_configs = audio.CreateAudioDataFormatFromDict(capture_data_format)
    if capture_configs.file_type not in self._VALID_AUDIO_FILE_TYPES:
      error_message = 'file_type passed in is not valid.'
      raise USBAudioFlowError(error_message)
    self._captured_file_type = capture_configs.file_type
    self._usb_ctrl.SetDriverCaptureConfigs(capture_configs)

  def StartCapturingAudio(self):
    """Starts recording audio data."""
    self._supported_data_format = self._usb_ctrl.GetSupportedCaptureDataFormat()
    self._supported_data_format.file_type = self._captured_file_type
    params_list = self._GetAlsaUtilCommandArgs(self._supported_data_format)
    file_suffix = '.' + self._captured_file_type
    recorded_file = tempfile.NamedTemporaryFile(prefix='audio_',
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
      USBAudioFlowError if this is called before StartCapturingAudio() is
        called.
    """
    if self._subprocess is None:
      raise USBAudioFlowError('Stop capturing audio before start.')

    elif self._subprocess.poll() is None:
      self._subprocess.terminate()
      logging.info('Stopped capturing audio.')

    return (self._file_path, self._supported_data_format.AsDict())

  @property
  def is_capturing_audio(self):
    """InputUSBAudioFlow is capturing audio.

    Returns:
      True if InputUSBAudioFlow is capturing audio.
    """
    return self._subprocess_is_running

  def Select(self):
    """Selects the USB Audio flow.

    This is a dummy method because InputUSBAudioFlow is selected by default.
    """
    logging.info('Select InputUSBAudioFlow for input id #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBIn'


class OutputUSBAudioFlow(USBAudioFlow):
  """Subclass of USBAudioFlow that handles output audio data."""

  def __init__(self, *args):
    """Constructs an OutputUSBAudioFlow object."""
    super(OutputUSBAudioFlow, self).__init__(*args)

  def SetDriverPlaybackConfigs(self, playback_data_format):
    """Sets USB driver playback configurations in AudioDataFormat form.

    Playback configs can still be set even when the flow is plugged in. See
    docstring of USBAudioController.SetDriverPlaybackConfigs for more details.

    The 'file_type' field in the playback_data_format passed in is ignored. Only
    the 'file_type' in the playback file data format passed into
    StartPlayingAudio() is checked before starting playback.

    Args:
      playback_data_format: The dict form of an AudioDataFormat object.

    Raises:
      USBAudioFlowError if this InputUSBAudioFlow is still capturing audio when
        this method is called.
    """
    if self.is_playing_audio:
      error_message = ('Driver configs should remain unchanged while USB Audio'
                       'Flow is playing audio.')
      raise USBAudioFlowError(error_message)
    playback_configs = audio.CreateAudioDataFormatFromDict(playback_data_format)
    self._usb_ctrl.SetDriverPlaybackConfigs(playback_configs)

  def StartPlayingAudio(self, path, data_format):
    """Starts playing audio data from the path.

    Args:
      path: The path to the audio file for playing.
      data_format: The dict representation of AudioDataFormat. Refer to
        docstring of utils.audio.AudioDataFormat for detail.

    Raises:
      USBAudioFlowError if data format of the file at path does not comply with
        the configurations of the USB driver.
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
      raise USBAudioFlowError(
          'Data format incompatible with driver configurations')

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
      USBAudioFlowError if this is called before StartPlayingAudio() is called.
    """
    if self._subprocess is None:
      raise USBAudioFlowError('Stop playing audio before Start')

    elif self._subprocess.poll() is None:
      self._subprocess.terminate()
      logging.info('Stopped playing audio.')

  @property
  def is_playing_audio(self):
    """OutputUSBAudioFlow is playing audio.

    Returns:
      True if OutputUSBAudioFlow is playing audio.
    """
    return self._subprocess_is_running

  def Select(self):
    """Selects the USB Audio flow.

    This is a dummy method because OutputUSBAudioFlow is selected by default.
    """
    logging.info('Select OutputUSBAudioFlow for input id #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBOut'
