# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""This module defines Chameleond APIs."""

from abc import ABCMeta


class ChameleondInterface(object):
  """Abstract class of Chameleond interface."""
  __metaclass__ = ABCMeta

  def __init__(self, *args, **kwargs):
    pass

  def Reset(self):
    """Resets Chameleon board."""
    raise NotImplementedError('Reset')

  def GetDetectedStatus(self):
    """Returns detetcted status of all devices.

    User can use this API to know the capability of the chameleon board.

    Returns:
      A list of a tuple of detected devices' strings detected status.
      e.g. [('HDMI', True), ('MIC', False)]
    """
    raise NotImplementedError('GetDetectedStatus')

  def HasDevice(self, device_id):
    """Returns True if there is a device.

    Returns:
      True if there is a device . False otherwise.
    """
    raise NotImplementedError('HasDevice')

  def GetSupportedPorts(self):
    """Returns all supported ports on the board.

    Not like the ProbePorts() method which only returns the ports which
    are connected, this method returns all supported ports on the board.

    Returns:
      A tuple of port_id, for all supported ports on the board.
    """
    raise NotImplementedError('GetSupportedPorts')

  def GetSupportedInputs(self):
    """Returns all supported input ports on the board.

    Not like the ProbeInputs() method which only returns the input ports which
    are connected, this method returns all supported input ports on the board.

    Returns:
      A tuple of port_id, for all supported input port on the board.
    """
    raise NotImplementedError('GetSupportedInputs')

  def GetSupportedOutputs(self):
    """Returns all supported output ports on the board.

    Not like the ProbeOutputs() method which only returns the output ports which
    are connected, this method returns all supported output ports on the board.

    Returns:
      A tuple of port_id, for all supported output port on the board.
    """
    raise NotImplementedError('GetSupportedOutputs')

  def IsPhysicalPlugged(self, port_id):
    """Returns true if the physical cable is plugged between DUT and Chameleon.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    raise NotImplementedError('IsPhysicalPlugged')

  def ProbePorts(self):
    """Probes all the connected ports on Chameleon board.

    Returns:
      A tuple of port_id, for the ports connected to DUT.
    """
    raise NotImplementedError('ProbePorts')

  def ProbeInputs(self):
    """Probes all the connected input ports on Chameleon board.

    Returns:
      A tuple of port_id, for the input ports connected to DUT.
    """
    raise NotImplementedError('ProbeInputs')

  def ProbeOutputs(self):
    """Probes all the connected output ports on Chameleon board.

    Returns:
      A tuple of port_id, for the output ports connected to DUT.
    """
    raise NotImplementedError('ProbeOutputs')

  def GetConnectorType(self, port_id):
    """Returns the human readable string for the connector type.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      A string, like "HDMI", "DP", "MIC", etc.
    """
    raise NotImplementedError('GetConnectorType')

  def HasAudioSupport(self, port_id):
    """Returns true if the port has audio support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has audio support; otherwise, False.
    """
    raise NotImplementedError('HasAudioSupport')

  def HasVideoSupport(self, port_id):
    """Returns true if the port has video support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has video support; otherwise, False.
    """
    raise NotImplementedError('HasVideoSupport')

  def SetVgaMode(self, port_id, mode):
    """Sets the mode for VGA monitor.

    Args:
      port_id: The ID of the VGA port.
      mode: A string of the mode name, e.g. 'PC_1920x1080x60'. Use 'auto'
            to detect the VGA mode automatically.
    """
    raise NotImplementedError('SetVgaMode')

  def WaitVideoInputStable(self, port_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      port_id: The ID of the video input port.
      timeout: The time period to wait for.

    Returns:
      True if the video input becomes stable within the timeout period;
      otherwise, False.
    """
    raise NotImplementedError('WaitVideoInputStable')

  def CreateEdid(self, edid):
    """Creates an internal record of EDID using the given byte array.

    Args:
      edid: A byte array of EDID data, wrapped in a xmlrpclib.Binary object.

    Returns:
      An edid_id.
    """
    raise NotImplementedError('CreateEdid')

  def DestroyEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    raise NotImplementedError('DestroyEdid')

  def SetDdcState(self, port_id, enabled):
    """Sets the enabled/disabled state of DDC bus on the given video input.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable DDC bus due to a user request; False to
               disable it.
    """
    raise NotImplementedError('SetDdcState')

  def IsDdcEnabled(self, port_id):
    """Checks if the DDC bus is enabled or disabled on the given video input.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the DDC bus is enabled; False if disabled.
    """
    raise NotImplementedError('IsDdcEnabled')

  def ReadEdid(self, port_id):
    """Reads the EDID content of the selected video input on Chameleon.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object,
      or None if the EDID is disabled.
    """
    raise NotImplementedError('ReadEdid')

  def ApplyEdid(self, port_id, edid_id):
    """Applies the EDID to the selected video input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      port_id: The ID of the video input port.
      edid_id: The ID of the EDID.
    """
    raise NotImplementedError('ApplyEdid')

  def IsPlugged(self, port_id):
    """Returns true if the port is emulated as plugged.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the port is emualted as plugged; otherwise, False.
    """
    raise NotImplementedError('IsPlugged')

  def Plug(self, port_id):
    """Emualtes plug, like asserting HPD line to high on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    raise NotImplementedError('Plug')

  def Unplug(self, port_id):
    """Emulates unplug, like deasserting HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    raise NotImplementedError('Unplug')

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
    raise NotImplementedError('FireHpdPulse')

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
    raise NotImplementedError('FireMixedHpdPulses')

  def ScheduleHpdToggle(self, port_id, delay_ms, rising_edge):
    """Schedules one HPD Toggle, with a delay between the toggle.

    Args:
      port_id: The ID of the video input port.
      delay_ms: Delay in milli-second before the toggle takes place.
      rising_edge: Whether the toggle should be a rising edge or a falling edge.
    """
    raise NotImplementedError('ScheduleHpdToggle')

  def SetContentProtection(self, port_id, enabled):
    """Sets the content protection state on the port.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable; False to disable.
    """
    raise NotImplementedError('SetContentProtection')

  def IsContentProtectionEnabled(self, port_id):
    """Returns True if the content protection is enabled on the port.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the content protection is enabled; otherwise, False.
    """
    raise NotImplementedError('IsContentProtectionEnabled')

  def IsVideoInputEncrypted(self, port_id):
    """Returns True if the video input on the port is encrypted.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the video input is encrypted; otherwise, False.
    """
    raise NotImplementedError('IsVideoInputEncrypted')

  def DumpPixels(self, port_id, x=None, y=None, width=None, height=None):
    """Dumps the raw pixel array of the selected area.

    If not given the area, default to capture the whole screen.

    Args:
      port_id: The ID of the video input port.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    raise NotImplementedError('DumpPixels')

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
    raise NotImplementedError('GetMaxFrameLimit')

  def StartCapturingVideo(self, port_id, x=None, y=None, width=None,
                          height=None):
    """Starts video capturing continuously on the given video input.

    This API is an asynchronous call. It returns after the video starts
    capturing. The caller should call StopCapturingVideo to stop it.

    The example of usage:
      chameleon.StartCapturingVideo(hdmi_input)
      time.sleep(2)
      chameleon.StopCapturingVideo()
      for i in xrange(chameleon.GetCapturedFrameCount()):
        frame = chameleon.ReadCapturedFrame(i, *area).data
        CompareFrame(frame, golden_frames[i])

    Args:
      port_id: The ID of the video input port.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
    """
    raise NotImplementedError('StartCapturingVideo')

  def StopCapturingVideo(self, stop_index=None):
    """Stops video capturing which was started previously.

    Args:
      stop_index: Wait the captured frame count reaches this index. If not
                  given, stop immediately. Note that the captured frame of
                  stop_index should not be read.

    Raises:
      DriverError if the capture period is longer than the capture limitation.
    """
    raise NotImplementedError('StopCapturingVideo')

  def CaptureVideo(self, port_id, total_frame, x=None, y=None, width=None,
                   height=None):
    """Captures the video stream on the given video input to the buffer.

    This API is a synchronous call. It returns after all the frames are
    captured. The frames can be read using the ReadCapturedFrame API.

    The example of usage:
      chameleon.CaptureVideo(hdmi_input, total_frame)
      for i in xrange(total_frame):
        frame = chameleon.ReadCapturedFrame(i, *area).data
        CompareFrame(frame, golden_frames[i])

    Args:
      port_id: The ID of the video input port.
      total_frame: The total number of frames to capture, should not larger
                   than value of GetMaxFrameLimit.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
    """
    raise NotImplementedError('CaptureVideo')

  def GetCapturedFrameCount(self):
    """Gets the total count of the captured frames.

    Returns:
      The number of frames captured.
    """
    raise NotImplementedError('GetCapturedFrameCount')

  def GetCapturedResolution(self):
    """Gets the resolution of the captured frame.

    If a cropping area is specified on capturing, returns the cropped
    resolution.

    Returns:
      A (width, height) tuple.
    """
    raise NotImplementedError('GetCapturedResolution')

  def ReadCapturedFrame(self, frame_index):
    """Reads the content of the captured frame from the buffer.

    Args:
      frame_index: The index of the frame to read.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    raise NotImplementedError('ReadCapturedFrame')

  def CacheFrameThumbnail(self, frame_index, ratio=2):
    """Caches the thumbnail of the dumped field to a temp file.

    Args:
      frame_index: The index of the frame to cache.
      ratio: The ratio to scale down the image.

    Returns:
      An ID to identify the cached thumbnail.
    """
    raise NotImplementedError('CacheFrameThumbnail')

  def GetCapturedChecksums(self, start_index=0, stop_index=None):
    """Gets the list of checksums of the captured frames.

    Args:
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of checksums of frames.
    """
    raise NotImplementedError('GetCapturedChecksums')

  def GetCapturedHistograms(self, start_index=0, stop_index=None):
    """Gets the list of histograms of the captured frames.

    Args:
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of checksums of frames.
    """
    raise NotImplementedError('GetCapturedHistograms')

  def ComputePixelChecksum(
      self, port_id, x=None, y=None, width=None, height=None):
    """Computes the checksum of pixels in the selected area.

    If not given the area, default to compute the whole screen.

    Args:
      port_id: The ID of the video input port.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      The checksum of the pixels.
    """
    raise NotImplementedError('ComputePixelChecksum')

  def DetectResolution(self, port_id):
    """Detects the video source resolution.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A (width, height) tuple.
    """
    raise NotImplementedError('DetectResolution')

  def StartCapturingAudio(self, port_id, has_file=True):
    """Starts capturing audio.

    Refer to the docstring of StartPlayingEcho about the restriction of
    capturing and echoing at the same time.

    Args:
      port_id: The ID of the audio input port.
      has_file: True for saving audio data to file. False otherwise.
    """
    raise NotImplementedError('StartCapturingAudio')

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

    Raises:
      DriverError: Input is selected to port other than port_id.
        This happens if user has used API related to input operation on
        other port. The API includes CaptureVideo, StartCapturingVideo,
        DetectResolution, StartCapturingAudio, StartPlayingEcho.
    """
    raise NotImplementedError('StopCapturingAudio')

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
      DriverError: There is no file at the path.
    """
    raise NotImplementedError('StartPlayingAudio')

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
    """
    raise NotImplementedError('StartPlayingEcho')

  def StopPlayingAudio(self, port_id):
    """Stops playing audio from port_id port.

    Args:
      port_id: The ID of the output connector.
    """
    raise NotImplementedError('StopPlayingAudio')

  def AudioBoardConnect(self, bus_number, endpoint):
    """Connects an endpoint to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in audio_board.AudioBusEndpoint.

    Raises:
      DriverError: If the endpoint is a source and there is other source
                   endpoint occupying audio bus.
    """
    raise NotImplementedError('AudioBoardConnect')

  def AudioBoardDisconnect(self, bus_number, endpoint):
    """Disconnects an endpoint to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in audio_board.AudioBusEndpoint.

    Raises:
      DriverError: If the endpoint is not connected to audio bus.
    """
    raise NotImplementedError('AudioBoardDisconnect')

  def AudioBoardGetRoutes(self, bus_number):
    """Gets a list of routes on audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.

    Returns:
      A list of tuples (source, sink) that are routed on audio bus
      where source and sink are endpoints defined in
      audio_board.AudioBusEndpoint.
    """
    raise NotImplementedError('AudioBoardGetRoutes')

  def AudioBoardClearRoutes(self, bus_number):
    """Clears routes on an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
    """
    raise NotImplementedError('AudioBoardClearRoutes')

  def AudioBoardHasJackPlugger(self):
    """If there is jack plugger on audio board.

    Audio board must have the motor cable connected in order to control
    jack plugger of audio box.

    Returns:
      True if there is jack plugger on audio board. False otherwise.
    """
    raise NotImplementedError('AudioBoardHasJackPlugger')

  def AudioBoardAudioJackPlug(self):
    """Plugs audio jack to connect audio board and Cros device."""
    raise NotImplementedError('AudioBoardAudioJackPlug')

  def AudioBoardAudioJackUnplug(self):
    """Unplugs audio jack to disconnect audio board and Cros device."""
    raise NotImplementedError('AudioBoardAudioJackUnplug')

  def AudioBoardResetBluetooth(self):
    """Resets bluetooth module on audio board."""
    raise NotImplementedError('AudioBoardResetBluetooth')

  def AudioBoardDisableBluetooth(self):
    """Disables bluetooth module on audio board."""
    raise NotImplementedError('AudioBoardDisableBluetooth')

  def AudioBoardIsBluetoothEnabled(self):
    """Checks if bluetooth module on audio board is enabled.

    Returns:
      True if bluetooth module is enabled. False otherwise.
    """
    raise NotImplementedError('AudioBoardIsBluetoothEnabled')

  def SetUSBDriverPlaybackConfigs(self, playback_data_format):
    """Updates the corresponding playback configurations."""
    raise NotImplementedError('SetUSBDriverPlaybackConfigs')

  def SetUSBDriverCaptureConfigs(self, capture_data_format):
    """Updates the corresponding capture configurations."""
    raise NotImplementedError('SetUSBDriverCaptureConfigs')

  def GetMacAddress(self):
    """Gets the MAC address of this Chameleon."""
    raise NotImplementedError('GetMacAddress')
