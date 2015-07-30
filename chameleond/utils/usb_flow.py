# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module specifies the interface for usb flows."""

import logging

class USBFlow(object):
  """An abstraction for the entire USB flow.

  Properties:
    _port_id: The ID of the input/output connector. Check the value in ids.py.
    _usb_ctrl: An USBController object.
  """
  def __init__(self, port_id, usb_ctrl):
    """Initializes USBFlow object with two properties.

    Args:
      port_id: port id that represents the type of port used.
      usb_ctrl: a USBController object that USBFlow objects keep reference to.
    """
    self._port_id = port_id
    self._usb_ctrl = usb_ctrl

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


class InputUSBFlow(USBFlow):
  """Subclass of USBFlow that handles input audio data."""

  def __init__(self, *args):
    """Constructs an InputUSBFlow object."""
    super(InputUSBFlow, self).__init__(*args)

  def StartCapturingAudio(self):
    """Starts recording audio data."""
    logging.info('Started capturing audio.')
    raise NotImplementedError('StartCapturingAudio')

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
    """
    logging.info('Started playing audio.')
    raise NotImplementedError('StartPlayingAudio')

  def StopPlayingAudio(self):
    """Stops playing audio data."""
    logging.info('Stopped playing audio.')
    raise NotImplementedError('StopPlayingAudio')

  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return 'USBOut'
