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

  def IsHealthy(self):
    """Returns if the Chameleon is healthy or any repair is needed.

    Returns:
      True if the Chameleon is healthy; otherwise, False, need to repair.
    """
    raise NotImplementedError('IsHealthy')

  def Repair(self):
    """Repairs the Chameleon.

    It can be an asynchronous call, e.g. do the repair after return. An
    approximate time of the repair is returned. The caller should wait that
    time before the next action.

    Returns:
      An approximate repair time in second.
    """
    raise NotImplementedError('Repair')

  def GetSupportedInputs(self):
    """Returns all supported connectors on the board.

    Not like the ProbeInputs() method which only returns the connectors which
    are connected, this method returns all supported connectors on the board.

    Returns:
      A tuple of input_id, for all supported connectors on the board.
    """
    raise NotImplementedError('GetSupportedInputs')

  def IsPhysicalPlugged(self, input_id):
    """Returns if the physical cable is plugged.

    It checks the source power +5V/+3.3V pin.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    raise NotImplementedError('IsPhysicalPlugged')

  def ProbeInputs(self):
    """Probes all the display connectors on Chameleon board.

    Returns:
      A tuple of input_id, for the connectors connected to DUT.
    """
    raise NotImplementedError('ProbeInputs')

  def GetConnectorType(self, input_id):
    """Returns the human readable string for the connector type.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A string, like "VGA", "DVI", "HDMI", or "DP".
    """
    raise NotImplementedError('StrInterface')

  def WaitVideoInputStable(self, input_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      input_id: The ID of the input connector.
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

  def ReadEdid(self, input_id):
    """Reads the EDID content of the selected input on Chameleon.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object.
    """
    raise NotImplementedError('ReadEdid')

  def ApplyEdid(self, input_id, edid_id):
    """Applies the EDID to the selected input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      input_id: The ID of the input connector.
      edid_id: The ID of the EDID.
    """
    raise NotImplementedError('ApplyEdid')

  def IsPlugged(self, input_id):
    """Returns if the HPD line is plugged.

    Args:
      input_id: The ID of the input connector.

    Returns:
      True if the HPD line is plugged; otherwise, False.
    """
    raise NotImplementedError('IsPlugged')

  def Plug(self, input_id):
    """Asserts HPD line to high, emulating plug.

    Args:
      input_id: The ID of the input connector.
    """
    raise NotImplementedError('Plug')

  def Unplug(self, input_id):
    """Deasserts HPD line to low, emulating unplug.

    Args:
      input_id: The ID of the input connector.
    """
    raise NotImplementedError('Unplug')

  def FireHpdPulse(self, input_id, deassert_interval_usec,
                   assert_interval_usec=None, repeat_count=1,
                   end_level=1):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      input_id: The ID of the input connector.
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    raise NotImplementedError('FireHpdPulse')

  def FireMixedHpdPulses(self, input_id, widths):
    """Fires one or more HPD pulses, starting at low, of mixed widths.

    One must specify a list of segment widths in the widths argument where
    widths[0] is the width of the first low segment, widths[1] is that of the
    first high segment, widths[2] is that of the second low segment, ... etc.
    The HPD line stops at low if even number of segment widths are specified;
    otherwise, it stops at high.

    Args:
      input_id: The ID of the input connector.
      widths: list of pulse segment widths in usec.
    """
    raise NotImplementedError('FireMixedHpdPulses')

  def GetPixelFormat(self):
    """Returns the pixel format for the output of DumpPixels.

    Returns:
      A string of the format, like 'rgba', 'bgra', 'rgb', etc.
    """
    raise NotImplementedError('GetPixelFormat')

  def DumpPixels(self, input_id, x=None, y=None, width=None, height=None):
    """Dumps the raw pixel array of the selected area.

    If not given the area, default to capture the whole screen.

    Args:
      input_id: The ID of the input connector.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    raise NotImplementedError('DumpPixels')

  def GetMaxFrameLimit(self, input_id, width, height):
    """Gets the maximal number of frames which are accommodated in the buffer.

    It depends on the size of the internal buffer on the board and the
    size of area to capture (full screen or cropped area).

    Args:
      input_id: The ID of the input connector.
      width: The width of the area to capture.
      height: The height of the area to capture.

    Returns:
      A number of the frame limit.
    """
    raise NotImplementedError('GetMaxFrameLimit')

  def StartCapturingVideo(self, input_id, x=None, y=None, width=None,
                          height=None):
    """Starts video capturing continuously on the given input.

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
      input_id: The ID of the input connector.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
    """
    raise NotImplementedError('StartCapturingVideo')

  def StopCapturingVideo(self):
    """Stops video capturing which was started previously.

    Raises:
      DriverError if the capture period is longer than the capture limitation.
    """
    raise NotImplementedError('StopCapturingVideo')

  def CaptureVideo(self, input_id, total_frame, x=None, y=None, width=None,
                   height=None):
    """Captures the video stream on the given input to the buffer.

    This API is a synchronous call. It returns after all the frames are
    captured. The frames can be read using the ReadCapturedFrame API.

    The example of usage:
      chameleon.CaptureVideo(hdmi_input, total_frame)
      for i in xrange(total_frame):
        frame = chameleon.ReadCapturedFrame(i, *area).data
        CompareFrame(frame, golden_frames[i])

    Args:
      input_id: The ID of the input connector.
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
    """Reads the content of the captured frames from the buffer.

    Args:
      frame_index: The index of the frame to read.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    raise NotImplementedError('ReadCapturedFrame')

  def GetCapturedChecksums(self, start_index, stop_index):
    """Gets the list of checksums of the captured frames.

    Args:
      start_index: The index of the start frame.
      stop_index: The index of the stop frame (excluded).

    Returns:
      The list of checksums of frames.
    """
    raise NotImplementedError('GetCapturedChecksums')

  def ComputePixelChecksum(self, input_id, x=None, y=None, width=None,
        height=None):
    """Computes the checksum of pixels in the selected area.

    If not given the area, default to compute the whole screen.

    Args:
      input_id: The ID of the input connector.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      The checksum of the pixels.
    """
    raise NotImplementedError('ComputePixelChecksum')

  def DetectResolution(self, input_id):
    """Detects the source resolution.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A (width, height) tuple.
    """
    raise NotImplementedError('DetectResolution')

  def StartCapturingAudio(self, input_id):
    """Starts capturing audio.

    Args:
      input_id: The ID of the input connector.
    """
    raise NotImplementedError('StartCapturingAudio')

  def StopCapturingAudio(self, input_id):
    """Stops capturing audio and returns recorded audio raw data.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A tuple (data, format).
      data: The captured audio data wrapped in an xmlrpclib.Binary object.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.
        Currently, the data format supported is
        dict(file_type='raw', sample_format='S32_LE', channel=8, rate=48000)
    """
    raise NotImplementedError('StopCapturingAudio')
