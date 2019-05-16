# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A manager for all flow based chameleon devices."""

import functools
import logging
import os
import xmlrpclib

from chameleond.utils import ids


class FlowManagerError(Exception):
  """Exception raised when any error on Flow manager."""
  pass


def _FlowMethod(func):
  """Decorator that checks the if port_id exists on board."""
  @functools.wraps(func)
  def wrapper(instance, port_id, *args, **kwargs):
    if port_id not in instance.flows:
      raise FlowManagerError('Not a exist port_id %d' % port_id)
    return func(instance, port_id, *args, **kwargs)
  return wrapper


def _AudioMethod(input_only=False, output_only=False):
  """Decorator that checks the port_id argument is an audio port.

  Args:
    input_only: True to check if port is an input port.
    output_only: True to check if port is an output port.
  """
  def _ActualDecorator(func):
    @functools.wraps(func)
    def wrapper(instance, port_id, *args, **kwargs):
      if not ids.IsAudioPort(port_id):
        raise FlowManagerError(
            'Not a valid port_id for audio operation: %d' % port_id)
      if input_only and not ids.IsInputPort(port_id):
        raise FlowManagerError(
            'Not a valid port_id for input operation: %d' % port_id)
      elif output_only and not ids.IsOutputPort(port_id):
        raise FlowManagerError(
            'Not a valid port_id for output operation: %d' % port_id)
      return func(instance, port_id, *args, **kwargs)
    return wrapper
  return _ActualDecorator


def _VideoMethod(func):
  """Decorator that checks the port_id argument is a video port."""
  @functools.wraps(func)
  def wrapper(instance, port_id, *args, **kwargs):
    if not ids.IsVideoPort(port_id):
      raise FlowManagerError('Not a valid port_id for video operation: %d' %
                             port_id)
    return func(instance, port_id, *args, **kwargs)
  return wrapper


def _USBHIDMethod(func):
  """Decorator that checks the port_id argument is a USB HID port."""
  @functools.wraps(func)
  def wrapper(instance, port_id, *args, **kwargs):
    if not ids.IsUSBHIDPort(port_id):
      raise FlowManagerError('Not a valid port_id for HID operation: %d' %
                             port_id)
    return func(instance, port_id, *args, **kwargs)
  return wrapper


class FlowManager(object):
  """A manager for flow based chameleon devices.

  It is used for backward compatible of flow based APIs.
  """
  def __init__(self, flows_table):
    """Constructs a FlowManager object.

    Args:
      flows_table: The table of flow based chameleon devices. It's a dict with
          port_id and device object as value. The parent class of the
          it must be a Flow. User can't change the content of
          flows_table at runtime.
          e.g.
          {
              ids.DP1: dp1_object,
              ids.DP2: dp2_object
          }
    """
    self.flows = flows_table
    self._selected_input = None
    self._selected_output = None
    # Reserve index 0 as the default EDID.
    self._all_edids = [self._ReadDefaultEdid()]

  def _RetrievePortsInFlowTable(self, ports):
    """Retrieve intersection of ports and keys of flow table.

    The ports in flow table sholud be detected on board. This API returns the
    intersection of ports and detected ports.

    Args:
      ports: A list of port_id.

    Returns:
      A list of port_id which can be detected on board.
    """
    return list(set(ports) & set(self.flows.keys()))

  @_FlowMethod
  def SelectInput(self, port_id):
    """Selects the input on Chameleon.

    Args:
      port_id: The ID of the input port.
    """
    if port_id != self._selected_input:
      self.flows[port_id].Select()
      self._selected_input = port_id
    self.flows[port_id].DoFSM()

  @_FlowMethod
  def SelectOutput(self, port_id):
    """Selects the output on Chameleon.

    Args:
      port_id: The ID of the output port.
    """
    if port_id != self._selected_output:
      self.flows[port_id].Select()
      self._selected_output = port_id
    self.flows[port_id].DoFSM()

  def Reset(self):
    """Reset all detected chameleon devices."""
    logging.info('Apply the default EDID and enable DDC on all video inputs')
    self._selected_input = None
    self._selected_output = None
    for port_id in self.GetSupportedInputs():
      if self.HasVideoSupport(port_id):
        self.ApplyEdid(port_id, ids.EDID_ID_DEFAULT)
        self.SetDdcState(port_id, enabled=True)
    for port_id in self.GetSupportedPorts():
      if self.HasAudioSupport(port_id):
        # Stops all audio capturing.
        if ids.IsInputPort(port_id) and self.flows[port_id].is_capturing_audio:
          try:
            self.flows[port_id].StopCapturingAudio()
          except Exception as e:
            logging.error('Failed to stop capturing audio: %s', str(e))

        self.flows[port_id].ResetRoute()

    # Set all ports unplugged on initialization.
    for port_id in self.GetSupportedPorts():
      self.Unplug(port_id)

  def GetSupportedPorts(self):
    """Returns all supported ports on the board.

    Not like the ProbePorts() method which only returns the ports which
    are connected, this method returns all supported ports on the board.

    Returns:
      A tuple of port_id, for all supported ports on the board.
    """
    return self.flows.keys()

  def GetSupportedInputs(self):
    """Returns all supported input ports on the board.

    Not like the ProbeInputs() method which only returns the input ports which
    are connected, this method returns all supported input ports on the board.

    Returns:
      A tuple of port_id, for all supported input port on the board.
    """
    return self._RetrievePortsInFlowTable(ids.INPUT_PORTS)

  def GetSupportedOutputs(self):
    """Returns all supported output ports on the board.

    Not like the ProbeOutputs() method which only returns the output ports which
    are connected, this method returns all supported output ports on the board.

    Returns:
      A tuple of port_id, for all supported output port on the board.
    """
    return self._RetrievePortsInFlowTable(ids.OUTPUT_PORTS)

  def IsPhysicalPlugged(self, port_id):
    """Returns true if the physical cable is plugged between DUT and Chameleon.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    return self.flows[port_id].IsPhysicalPlugged()

  def ProbePorts(self):
    """Probes all the connected ports on Chameleon board.

    Returns:
      A tuple of port_id, for the ports connected to DUT.
    """
    return tuple(port_id for port_id in self.GetSupportedPorts()
                 if self.IsPhysicalPlugged(port_id))

  def ProbeInputs(self):
    """Probes all the connected input ports on Chameleon board.

    Returns:
      A tuple of port_id, for the input ports connected to DUT.
    """
    return tuple(port_id for port_id in self.GetSupportedInputs()
                 if self.IsPhysicalPlugged(port_id))

  def ProbeOutputs(self):
    """Probes all the connected output ports on Chameleon board.

    Returns:
      A tuple of port_id, for the output ports connected to DUT.
    """
    return tuple(port_id for port_id in self.GetSupportedOutputs()
                 if self.IsPhysicalPlugged(port_id))

  def GetConnectorType(self, port_id):
    """Returns the human readable string for the connector type.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      A string, like "HDMI", "DP", "MIC", etc.
    """
    return self.flows[port_id].GetConnectorType()

  @_FlowMethod
  def HasAudioSupport(self, port_id):
    """Returns true if the port has audio support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has audio support; otherwise, False.
    """
    return ids.IsAudioPort(port_id)

  @_FlowMethod
  def HasVideoSupport(self, port_id):
    """Returns true if the port has video support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has video support; otherwise, False.
    """
    return ids.IsVideoPort(port_id)

  @_FlowMethod
  @_VideoMethod
  def SetVgaMode(self, port_id, mode):
    """Sets the mode for VGA monitor.

    Args:
      port_id: The ID of the VGA port.
      mode: A string of the mode name, e.g. 'PC_1920x1080x60'. Use 'auto'
            to detect the VGA mode automatically.
    """
    if port_id == ids.VGA:
      logging.info('Set VGA port #%d to mode: %s', port_id, mode)
      self.flows[port_id].SetVgaMode(mode)
    else:
      raise FlowManagerError('SetVgaMode only works on VGA port.')

  @_FlowMethod
  @_VideoMethod
  def WaitVideoInputStable(self, port_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      port_id: The ID of the video input port.
      timeout: The time period to wait for.

    Returns:
      True if the video input becomes stable within the timeout period;
      otherwise, False.
    """
    self.SelectInput(port_id)
    return self.flows[port_id].WaitVideoInputStable(timeout)

  def _ReadDefaultEdid(self):
    """Reads the default EDID from file.

    Returns:
      A byte array of EDID data.
    """
    driver_dir = os.path.dirname(os.path.realpath(__file__))
    edid_path = os.path.join(driver_dir, '..', 'data', 'default_edid.bin')
    return open(edid_path).read()

  def CreateEdid(self, edid):
    """Creates an internal record of EDID using the given byte array.

    Args:
      edid: A byte array of EDID data, wrapped in a xmlrpclib.Binary object.

    Returns:
      An edid_id.
    """
    if None in self._all_edids:
      last = self._all_edids.index(None)
      self._all_edids[last] = edid.data
    else:
      last = len(self._all_edids)
      self._all_edids.append(edid.data)
    return last

  def DestroyEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    if edid_id > ids.EDID_ID_DEFAULT:
      self._all_edids[edid_id] = None
    else:
      raise FlowManagerError('Not a valid edid_id.')

  @_FlowMethod
  @_VideoMethod
  def SetDdcState(self, port_id, enabled):
    """Sets the enabled/disabled state of DDC bus on the given video input.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable DDC bus due to an user request; False to
               disable it.
    """
    logging.info('Set DDC bus on port #%d to enabled %r', port_id, enabled)
    self.flows[port_id].SetDdcState(enabled)

  @_FlowMethod
  @_VideoMethod
  def IsDdcEnabled(self, port_id):
    """Checks if the DDC bus is enabled or disabled on the given video input.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the DDC bus is enabled; False if disabled.
    """
    return self.flows[port_id].IsDdcEnabled()

  @_FlowMethod
  @_VideoMethod
  def ReadEdid(self, port_id):
    """Reads the EDID content of the selected video input on Chameleon.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object,
      or None if the EDID is disabled.
    """
    if self.flows[port_id].IsEdidEnabled():
      return xmlrpclib.Binary(self.flows[port_id].ReadEdid())
    else:
      logging.debug('Read EDID on port #%d which is disabled.', port_id)
      return None

  @_FlowMethod
  @_VideoMethod
  def ApplyEdid(self, port_id, edid_id):
    """Applies the EDID to the selected video input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      port_id: The ID of the video input port.
      edid_id: The ID of the EDID.
    """
    if edid_id == ids.EDID_ID_DISABLE:
      logging.info('Disable EDID on port #%d', port_id)
      self.flows[port_id].SetEdidState(False)
    elif edid_id >= ids.EDID_ID_DEFAULT:
      logging.info('Apply EDID #%d to port #%d', edid_id, port_id)
      self.flows[port_id].WriteEdid(self._all_edids[edid_id])
      self.flows[port_id].SetEdidState(True)
    else:
      raise FlowManagerError('Not a valid edid_id.')

  @_FlowMethod
  def IsPlugged(self, port_id):
    """Returns true if the port is emulated as plugged.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the port is emualted as plugged; otherwise, False.
    """
    return self.flows[port_id].IsPlugged()

  @_FlowMethod
  def Plug(self, port_id):
    """Emualtes plug, like asserting HPD line to high on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    logging.info('Plug port #%d', port_id)
    return self.flows[port_id].Plug()

  @_FlowMethod
  def Unplug(self, port_id):
    """Emulates unplug, like deasserting HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    logging.info('Unplug port #%d', port_id)
    return self.flows[port_id].Unplug()

  @_FlowMethod
  def UnplugHPD(self, port_id):
    """Only deassert HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    logging.info('UnplugHPD port #%d', port_id)
    return self.flows[port_id].UnplugHPD()

  @_FlowMethod
  @_VideoMethod
  def FireHpdPulse(self, port_id, deassert_interval_usec,
                   assert_interval_usec=None, repeat_count=1,
                   end_level=1):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      port_id: The ID of the video input port.
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    if assert_interval_usec is None:
      # Fall back to use the same value as deassertion if not given.
      assert_interval_usec = deassert_interval_usec

    logging.info('Fire HPD pulse on port #%d, ending with %s',
                 port_id, 'high' if end_level else 'low')
    return self.flows[port_id].FireHpdPulse(
        deassert_interval_usec, assert_interval_usec, repeat_count, end_level)

  @_FlowMethod
  @_VideoMethod
  def FireMixedHpdPulses(self, port_id, widths_msec):
    """Fires one or more HPD pulses, starting at low, of mixed widths.

    One must specify a list of segment widths in the widths_msec argument where
    widths_msec[0] is the width of the first low segment, widths_msec[1] is that
    of the first high segment, widths_msec[2] is that of the second low segment,
    etc.
    The HPD line stops at low if even number of segment widths are specified;
    otherwise, it stops at high.

    The method is equivalent to a series of calls to Unplug() and Plug()
    separated by specified pulse widths.

    Args:
      port_id: The ID of the video input port.
      widths_msec: list of pulse segment widths in milli-second.
    """
    logging.info('Fire mixed HPD pulse on port #%d, ending with %s',
                 port_id, 'high' if len(widths_msec) % 2 else 'low')
    return self.flows[port_id].FireMixedHpdPulses(widths_msec)

  @_FlowMethod
  @_VideoMethod
  def ScheduleHpdToggle(self, port_id, delay_ms, rising_edge):
    """Schedules one HPD Toggle, with a delay between the toggle.

    Args:
      port_id: The ID of the video input port.
      delay_ms: Delay in milli-second before the toggle takes place.
      rising_edge: Whether the toggle should be a rising edge or a falling edge.
    """
    logging.info('Schedule HPD %s toggle on port #%d, in %d ms',
                 'rising' if rising_edge  else 'falling', port_id, delay_ms)
    return self.flows[port_id].ScheduleHpdToggle(port_id, delay_ms, rising_edge)

  @_FlowMethod
  @_VideoMethod
  def SetContentProtection(self, port_id, enabled):
    """Sets the content protection state on the port.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable; False to disable.
    """
    logging.info('Set content protection on port #%d: %r', port_id, enabled)
    self.flows[port_id].SetContentProtection(enabled)

  @_FlowMethod
  @_VideoMethod
  def IsContentProtectionEnabled(self, port_id):
    """Returns True if the content protection is enabled on the port.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the content protection is enabled; otherwise, False.
    """
    return self.flows[port_id].IsContentProtectionEnabled()

  @_FlowMethod
  @_VideoMethod
  def IsVideoInputEncrypted(self, port_id):
    """Returns True if the video input on the port is encrypted.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the video input is encrypted; otherwise, False.
    """
    return self.flows[port_id].IsVideoInputEncrypted()

  @_FlowMethod
  @_VideoMethod
  def GetMaxFrameLimit(self, port_id, width, height):
    """Gets the maximal number of frames which are accommodated in the buffer.

    It depends on the size of the internal buffer on the board and the
    size of area to capture (full screen or cropped area).

    Args:
      port_id: The ID of the video input port.
      width: The width of the area to capture.
      height: The height of the area to capture.

    Returns:
      A number of the frame limit.
    """
    # This result is related to the video flow status, e.g.
    # single/dual pixel mode, progressive/interlaced mode.
    # Need to select the input flow first.
    self.SelectInput(port_id)
    return self.flows[port_id].GetMaxFrameLimit(width, height)

  @_FlowMethod
  @_VideoMethod
  def StartDumpingFrames(self, port_id, frame_buffer_limit, x, y, width, height,
                         hash_buffer_limit):
    """Starts dumping frames continuously.

    Args:
      port_id: The ID of the video input port.
      frame_buffer_limit: The size of the buffer which stores the frame.
                          Frames will be dumped to the beginning when full.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      hash_buffer_limit: The maximum number of hashes to monitor. Stop
                         capturing when this limitation is reached.
    """
    self.flows[port_id].StartDumpingFrames(
        frame_buffer_limit, x, y, width, height, hash_buffer_limit)

  @_FlowMethod
  @_VideoMethod
  def StopDumpingFrames(self, port_id):
    """Stops dumping frames."""
    self.flows[port_id].StopDumpingFrames()

  @_FlowMethod
  def DumpFramesToLimit(self, port_id, frame_buffer_limit, x, y, width, height,
                        timeout):
    """Dumps frames and waits for the given limit being reached or timeout.

    Args:
      port_id: The ID of the video input port.
      frame_buffer_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      timeout: Time in second of timeout.
    """
    self.flows[port_id].DumpFramesToLimit(
        frame_buffer_limit, x, y, width, height, timeout)

  @_FlowMethod
  def GetDumpedFrameCount(self, port_id):
    """Gets the number of frames which is dumped."""
    return self.flows[port_id].GetDumpedFrameCount()

  @_FlowMethod
  def GetCapturedResolution(self, port_id):
    """Gets the resolution of the captured frame."""
    return self.flows[port_id].GetCapturedResolution()

  @_FlowMethod
  @_VideoMethod
  def DetectResolution(self, port_id):
    """Detects the video source resolution.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A (width, height) tuple.
    """
    self.SelectInput(port_id)
    resolution = self.flows[port_id].GetResolution()
    logging.info('Detected resolution on port #%d: %dx%d', port_id, *resolution)
    return resolution

  @_FlowMethod
  @_VideoMethod
  def GetVideoParams(self, port_id):
    """Gets video parameters.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A dict containing video parameters. Fields are omitted if unknown.
    """
    return self.flows[port_id].GetVideoParams()

  @_FlowMethod
  def ReadCapturedFrame(self, port_id, frame_index):
    """Reads the content of the captured frame from the buffer."""
    return self.flows[port_id].ReadCapturedFrame(frame_index)

  @_FlowMethod
  def CacheFrameThumbnail(self, port_id, frame_index, ratio):
    """Caches the thumbnail of the dumped field to a temp file.

    Args:
      port_id: The ID of the video input port.
      frame_index: The index of the frame to cache.
      ratio: The ratio to scale down the image.

    Returns:
      An ID to identify the cached thumbnail.
    """
    return self.flows[port_id].CacheFrameThumbnail(frame_index, ratio)

  @_FlowMethod
  @_VideoMethod
  def TriggerLinkFailure(self, port_id):
    """Trigger a link failure on the port.

    Args:
      port_id: The ID of the input port.
    """
    self.flows[port_id].TriggerLinkFailure()

  @_FlowMethod
  @_AudioMethod()
  def GetAudioChannelMapping(self, port_id):
    """Obtains the channel mapping for an audio port.

    Args:
      port_id: The ID of the audio port.

    Returns:
      An array of integers. There is one element per Chameleon channel.
      For audio input ports, each element indicates which input channel the
      capture channel is mapped to. For audio output ports, each element
      indicates which output channel the playback channel is mapped to. As a
      special case, -1 means the channel isn't mapped.

    Raises:
      FlowManagerError: no audio capture in progress
    """
    if self._selected_input != port_id:
      raise FlowManagerError(
          'The input is selected to %r not %r' % (self._selected_input, port_id))
    if ids.IsOutputPort(port_id):
      raise FlowManagerError(
          'Output ports don\'t support GetAudioChannelMapping yet')
    return self.flows[port_id].GetAudioChannelMapping()

  @_FlowMethod
  @_AudioMethod(input_only=True)
  def GetAudioFormat(self, port_id):
    """Gets the format currently used by audio capture.

    Args:
      port_id: The ID of the audio input port.

    Returns:
      An audio.AudioDataFormat object.

    Raises:
      FlowManagerError: no audio capture in progress
    """
    if self._selected_input != port_id:
      raise FlowManagerError(
          'The input is selected to %r not %r' % (self._selected_input, port_id))
    return self.flows[port_id].GetAudioFormat()

  @_FlowMethod
  @_AudioMethod(input_only=True)
  def StartCapturingAudio(self, port_id, has_file=True):
    """Starts capturing audio.

    Refer to the docstring of StartPlayingEcho about the restriction of
    capturing and echoing at the same time.

    Args:
      port_id: The ID of the audio input port.
      has_file: True for saving audio data to file. False otherwise.
    """
    self.SelectInput(port_id)
    logging.info('Start capturing audio from port #%d', port_id)
    self.flows[port_id].StartCapturingAudio(has_file)

  @_FlowMethod
  @_AudioMethod(input_only=True)
  def StopCapturingAudio(self, port_id):
    """Stops capturing audio and returns recorded data path and format.

    Args:
      port_id: The ID of the audio input port.

    Returns:
      A tuple (path, format).
      path: The path to the captured audio data.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.
        Currently, the data format supported is
        dict(file_type='raw', sample_format='S32_LE', channel=8, rate=48000)
      If we assign parameter has_file=False in StartCapturingAudio, we will get
      both empty string in path and format.

    Raises:
      FlowManagerError: Input is selected to port other than port_id.
        This happens if user has used API related to input operation on
        other port. The API includes CaptureVideo, StartCapturingVideo,
        DetectResolution, StartCapturingAudio, StartPlayingEcho.
    """
    if self._selected_input != port_id:
      raise FlowManagerError(
          'The input is selected to %r not %r' % (self._selected_input, port_id))
    path, data_format = self.flows[port_id].StopCapturingAudio()
    logging.info('Stopped capturing audio from port #%d', port_id)
    # If there is no path, set it to empty string. Because XMLRPC doesn't
    # support None as return value.
    if path is None and data_format is None:
      return '', ''
    return path, data_format

  @_FlowMethod
  @_AudioMethod(output_only=True)
  def StartPlayingAudio(self, port_id, path, data_format):
    """Playing audio data from an output port.

    Play audio data at given path using given format from port_id port.

    Args:
      port_id: The ID of the output connector.
      path: The path to the audio data to play.
      data_format: The dict representation of AudioDataFormat.
        Refer to docstring of utils.audio.AudioDataFormat for detail.
        Currently Chameleon only accepts data format if it meets
        dict(file_type='raw', sample_format='S32_LE', channel=8, rate=48000)
        Chameleon user should do the format conversion to minimize work load
        on Chameleon board.

    Raises:
      FlowManagerError: There is no file at the path.
    """
    if not os.path.exists(path):
      raise FlowManagerError('File path %r does not exist' % path)
    self.SelectOutput(port_id)
    logging.info('Start playing audio from port #%d', port_id)
    self.flows[port_id].StartPlayingAudio(path, data_format)

  @_FlowMethod
  @_AudioMethod(output_only=True)
  def StartPlayingEcho(self, port_id, input_id):
    """Echoes audio data received from input_id and plays to port_id.

    Echoes audio data received from input_id and plays to port_id.

    Chameleon does not support echoing from HDMI and capturing from LineIn/Mic
    at the same time. The echoing/capturing needs to be stop first before
    another action starts.

    For example, user can call

    StartPlayingEcho(3, 7) --> StopPlayingAudio(3) --> StartCapturingAudio(6)

    or

    StartCapturingAudio(6) --> StopCapturingAudio(6) --> StartPlayingEcho(3, 7)

    but user can not call

    StartPlayingEcho(3, 7) --> StartCapturingAudio(6)

    or

    StartCapturingAudio(6) --> StartPlayingEcho(3, 7)

    Exception is raised when conflicting actions are performed.

    Args:
      port_id: The ID of the output connector. Check the value in ids.py.
      input_id: The ID of the input connector. Check the value in ids.py.

    Raises:
      FlowManagerError: input_id is not valid for audio operation.
    """
    if not ids.IsAudioPort(input_id) or not ids.IsInputPort(input_id):
      raise FlowManagerError(
          'Not a valid input_id for audio operation: %d' % input_id)
    self.SelectInput(input_id)
    self.SelectOutput(port_id)
    logging.info('Start playing echo from port #%d using source from port#%d',
                 port_id, input_id)
    self.flows[port_id].StartPlayingEcho(input_id)

  @_FlowMethod
  @_AudioMethod(output_only=True)
  def StopPlayingAudio(self, port_id):
    """Stops playing audio from port_id port.

    Args:
      port_id: The ID of the output connector.

    Raises:
      FlowManagerError: Output is selected to port other than port_id.
        This happens if user has used API related to output operation on other
        port. The API includes StartPlayingAudio, StartPlayingEcho.
    """
    if self._selected_output != port_id:
      raise FlowManagerError(
          'The output is selected to %r not %r' % (self._selected_output, port_id))
    logging.info('Stop playing audio from port #%d', port_id)
    self.flows[port_id].StopPlayingAudio()

  def SetUSBDriverPlaybackConfigs(self, playback_data_format):
    """Updates the corresponding playback configurations to argument values.

    This provides flexibility for simulating the USB gadget driver using other
    configurations different from the default values.

    Args:
      playback_data_format: The dict form of an AudioDataFormat object. The
        'file_type' field will be ignored since for playback, there is no need
        for setting file type before playing audio. It is specified by the audio
        file passed in for playback. Other fields are used to set USB driver
        configurations.

    Raises:
      FlowManagerError if any of the USB Flows is playing or capturing audio.
    """
    if (self.flows[ids.USB_AUDIO_IN].is_capturing_audio or
        self.flows[ids.USB_AUDIO_OUT].is_playing_audio):
      error_message = ('Configuration changes not allowed when USB audio '
                       'driver is still performing playback/capture in one of '
                       'the flows.')
      raise FlowManagerError(error_message)
    self.flows[ids.USB_AUDIO_OUT].SetDriverPlaybackConfigs(
        playback_data_format)

  def SetUSBDriverCaptureConfigs(self, capture_data_format):
    """Updates the corresponding capture configurations to argument values.

    This provides flexibility for simulating the USB gadget driver using other
    configurations different from the default values.

    Args:
      capture_data_format: The dict form of an AudioDataFormat object. The
        'file_type' field will be saved by InputUSBAudioFlow as the file type
        for captured data. Other fields are used to set USB driver
        configurations.

    Raises:
      FlowManagerError if any of the USB audio Flows is playing or capturing
      audio.
    """
    if (self.flows[ids.USB_AUDIO_IN].is_capturing_audio or
        self.flows[ids.USB_AUDIO_OUT].is_playing_audio):
      error_message = ('Configuration changes not allowed when USB audio '
                       'driver is still performing playback/capture in one of '
                       'the flows.')
      raise FlowManagerError(error_message)
    self.flows[ids.USB_AUDIO_IN].SetDriverCaptureConfigs(capture_data_format)

  @_FlowMethod
  @_USBHIDMethod
  def SendHIDEvent(self, port_id, event_type, *args, **kwargs):
    """Sends HID event with event_type and arguments for HID port #port_id.

    Args:
      port_id: The ID of the HID port.
      event_type: Supported event type of string for HID port #port_id.

    Returns:
      Returns as event function if applicable.
    """
    return self.flows[port_id].Send(event_type, *args, **kwargs)
