# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the interface for usb flows."""

import logging
import tempfile

import chameleon_common #pylint: disable=W0611
from chameleond.utils import audio
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
  """
  def __init__(self, port_id, usb_ctrl):
    """Initializes USBFlow object with two properties.

    Args:
      port_id: port id that represents the type of port used.
      usb_ctrl: a USBController object that USBFlow objects keep reference to.
    """
    self._port_id = port_id
    self._usb_ctrl = usb_ctrl
    self._subprocess = None

  def Initialize(self):
    """Starts and initializes USB audio driver with preset configurations.

    The driver configurations are initially set using USBAudioDriverConfigs
    class.
    """
    self._usb_ctrl.InitializeAudioDriver()
    logging.info('Initialized USB flow #%d.', self._port_id)

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    raise NotImplementedError('GetConnectorType')

  def _GetAlsaUtilCommandArgs(self, data_format):
    """Returns a list of parameter flags paired with corresponding arguments.

    The argument values are taken from data_format.

    Args:
      data_format: The dictionary form of an AudioDataFormat object
        whose values are passed as arguments into the Alsa util command.

    Returns:
      A list containing argument strings
    """
    params_list = ['-D', 'hw:0,0',
                   '-t', data_format['file_type'],
                   '-f', data_format['sample_format'],
                   '-c', data_format['channel'],
                   '-r', data_format['rate']]
    return params_list


class InputUSBFlow(USBFlow):
  """Subclass of USBFlow that handles input audio data.

  Properties:
    _data_format: An AudioDataFormat object encapsulating the data format
                  derived from the USB driver's capture configurations.
    _file_path: The file path that captured data will be saved at.
  """

  _DEFAULT_FILE_TYPE = 'wav'

  def __init__(self, *args):
    """Constructs an InputUSBFlow object."""
    super(InputUSBFlow, self).__init__(*args)
    self._file_path = None
    self._data_format = None

  def StartCapturingAudio(self):
    """Starts recording audio data."""
    data_format = self._GetDataFormat()
    params_list = self._GetAlsaUtilCommandArgs(data_format)
    file_suffix = '.' + data_format['file_type']
    recorded_file = tempfile.NamedTemporaryFile(prefix='recorded',
                                                suffix=file_suffix,
                                                delete=False)
    self._file_path = recorded_file.name
    params_list.append(self._file_path)
    self._subprocess = system_tools.SystemTools.RunInSubprocess('arecord',
                                                                *params_list)
    logging.info('Started capturing audio using arecord %s',
                 ' '.join(params_list))

  def _GetDataFormat(self):
    """Returns capture data format in dictionary form.

    Returns:
      A 4-entry dictionary representing the supported format in AudioDataFormat
      form.
    """
    supported_format = self._usb_ctrl.GetSupportedCaptureDataFormat()
    self._data_format = audio.AudioDataFormat(self._DEFAULT_FILE_TYPE,
                                              supported_format['sample_format'],
                                              supported_format['channel'],
                                              supported_format['rate'])
    data_format_dict = self._data_format.AsDict()
    return data_format_dict

  def StopCapturingAudio(self):
    """Stops recording audio data."""
    logging.info('Stopped capturing audio.')
    raise NotImplementedError('StopCapturingAudio')

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
    if self._usb_ctrl.CheckPlaybackFormat(data_format):
      params_list = self._GetAlsaUtilCommandArgs(data_format)
      params_list.append(path)
      self._subprocess = system_tools.SystemTools.RunInSubprocess('aplay',
                                                                  *params_list)
      logging.info('Started playing audio using aplay %s',
                   ' '.join(params_list))
    else:
      raise USBFlowError('Data format incompatible with driver configurations')

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

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBOut'
