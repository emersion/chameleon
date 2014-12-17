# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for FPGA customized platform with the TIO card."""

import functools
import logging
import os
import tempfile
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.interface import ChameleondInterface

from chameleond.utils import codec_flow
from chameleond.utils import fpga
from chameleond.utils import i2c
from chameleond.utils import ids
from chameleond.utils import input_flow
from chameleond.utils import system_tools


class DriverError(Exception):
  """Exception raised when any error on FPGA driver."""
  pass


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
        raise DriverError(
            'Not a valid port_id for audio operation: %d' % port_id)
      if input_only and not ids.IsInputPort(port_id):
        raise DriverError(
            'Not a valid port_id for input operation: %d' % port_id)
      elif output_only and not ids.IsOutputPort(port_id):
        raise DriverError(
            'Not a valid port_id for output operation: %d' % port_id)
      return func(instance, port_id, *args, **kwargs)
    return wrapper
  return _ActualDecorator


def _VideoMethod(func):
  """Decorator that checks the port_id argument is a video port."""
  @functools.wraps(func)
  def wrapper(instance, port_id, *args, **kwargs):
    if not ids.IsVideoPort(port_id):
      raise DriverError('Not a valid port_id for video operation: %d' % port_id)
    return func(instance, port_id, *args, **kwargs)
  return wrapper


class ChameleondDriver(ChameleondInterface):
  """Chameleond Driver for FPGA customized platform."""

  _I2C_BUS_MAIN = 0
  _I2C_BUS_AUDIO = 1

  _PIXEL_LEN = 3

  # Time to wait for video frame dump to start before a timeout error is raised
  _TIMEOUT_FRAME_DUMP_PROBE = 60.0

  # The frame index which is used for the regular DumpPixels API.
  _DEFAULT_FRAME_INDEX = 0
  _DEFAULT_FRAME_LIMIT = _DEFAULT_FRAME_INDEX + 1

  # Limit the period of async capture to 3min (in 60fps).
  _MAX_CAPTURED_FRAME_COUNT = 3 * 60 * 60

  def __init__(self, *args, **kwargs):
    super(ChameleondDriver, self).__init__(*args, **kwargs)
    self._selected_input = None
    self._selected_output = None
    self._captured_params = {}
    # Reserve index 0 as the default EDID.
    self._all_edids = [self._ReadDefaultEdid()]

    self._tools = system_tools.SystemTools
    main_bus = i2c.I2cBus(self._I2C_BUS_MAIN)
    audio_bus = i2c.I2cBus(self._I2C_BUS_AUDIO)
    fpga_ctrl = fpga.FpgaController()
    self._flows = {
      ids.DP1: input_flow.DpInputFlow(ids.DP1, main_bus, fpga_ctrl),
      ids.DP2: input_flow.DpInputFlow(ids.DP2, main_bus, fpga_ctrl),
      ids.HDMI: input_flow.HdmiInputFlow(ids.HDMI, main_bus, fpga_ctrl),
      ids.VGA: input_flow.VgaInputFlow(ids.VGA, main_bus, fpga_ctrl),
      ids.MIC: codec_flow.InputCodecFlow(ids.MIC, audio_bus, fpga_ctrl),
      ids.LINEIN: codec_flow.InputCodecFlow(ids.LINEIN, audio_bus, fpga_ctrl),
      ids.LINEOUT: codec_flow.OutputCodecFlow(ids.LINEOUT, audio_bus, fpga_ctrl)
    }

    for flow in self._flows.itervalues():
      if flow:
        flow.Initialize()

    self.Reset()

    # Set all ports unplugged on initialization.
    for port_id in self.ProbePorts():
      self.Unplug(port_id)

  def Reset(self):
    """Resets Chameleon board."""
    logging.info('Execute the reset process')
    # TODO(waihong): Add other reset routines.
    self._ApplyDefaultEdid()

  def GetSupportedPorts(self):
    """Returns all supported ports on the board.

    Not like the ProbePorts() method which only returns the ports which
    are connected, this method returns all supported ports on the board.

    Returns:
      A tuple of port_id, for all supported ports on the board.
    """
    return self._flows.keys()

  def GetSupportedInputs(self):
    """Returns all supported input ports on the board.

    Not like the ProbeInputs() method which only returns the input ports which
    are connected, this method returns all supported input ports on the board.

    Returns:
      A tuple of port_id, for all supported input port on the board.
    """
    return ids.INPUT_PORTS

  def GetSupportedOutputs(self):
    """Returns all supported output ports on the board.

    Not like the ProbeOutputs() method which only returns the output ports which
    are connected, this method returns all supported output ports on the board.

    Returns:
      A tuple of port_id, for all supported output port on the board.
    """
    return ids.OUTPUT_PORTS

  def IsPhysicalPlugged(self, port_id):
    """Returns true if the physical cable is plugged between DUT and Chameleon.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    return self._flows[port_id].IsPhysicalPlugged()

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
    return self._flows[port_id].GetConnectorType()

  def HasAudioSupport(self, port_id):
    """Returns true if the port has audio support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has audio support; otherwise, False.
    """
    return ids.IsAudioPort(port_id)

  def HasVideoSupport(self, port_id):
    """Returns true if the port has video support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has video support; otherwise, False.
    """
    return ids.IsVideoPort(port_id)

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
      self._flows[port_id].SetVgaMode(mode)
    else:
      raise DriverError('SetVgaMode only works on VGA port.')

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
    return self._flows[port_id].WaitVideoInputStable(timeout)

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
      raise DriverError('Not a valid edid_id.')

  @_VideoMethod
  def ReadEdid(self, port_id):
    """Reads the EDID content of the selected video input on Chameleon.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object,
      or None if the EDID is disabled.
    """
    if self._flows[port_id].IsEdidEnabled():
      return xmlrpclib.Binary(self._flows[port_id].ReadEdid())
    else:
      logging.debug('Read EDID on port #%d which is disabled.', port_id)
      return None

  def _ApplyDefaultEdid(self):
    """Applies the default EDID to all video inputs."""
    logging.info('Apply the default EDID to all video inputs')
    for port_id in self.GetSupportedInputs():
      if self.HasVideoSupport(port_id):
        self.ApplyEdid(port_id, ids.EDID_ID_DEFAULT)

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
      self._flows[port_id].SetEdidState(False)
    elif edid_id >= ids.EDID_ID_DEFAULT:
      logging.info('Apply EDID #%d to port #%d', edid_id, port_id)
      self._flows[port_id].WriteEdid(self._all_edids[edid_id])
      self._flows[port_id].SetEdidState(True)
    else:
      raise DriverError('Not a valid edid_id.')

  def IsPlugged(self, port_id):
    """Returns true if the port is emulated as plugged.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the port is emualted as plugged; otherwise, False.
    """
    return self._flows[port_id].IsPlugged()

  def Plug(self, port_id):
    """Emualtes plug, like asserting HPD line to high on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    logging.info('Plug port #%d', port_id)
    return self._flows[port_id].Plug()

  def Unplug(self, port_id):
    """Emulates unplug, like deasserting HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    logging.info('Unplug port #%d', port_id)
    return self._flows[port_id].Unplug()

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
    return self._flows[port_id].FireHpdPulse(deassert_interval_usec,
        assert_interval_usec, repeat_count, end_level)

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
    return self._flows[port_id].FireMixedHpdPulses(widths_msec)

  def _SelectInput(self, port_id):
    """Selects the input on Chameleon.

    Args:
      port_id: The ID of the input port.
    """
    if port_id != self._selected_input:
      self._flows[port_id].Select()
      self._selected_input = port_id
    self._flows[port_id].Do_FSM()

  def _SelectOutput(self, port_id):
    """Selects the output on Chameleon.

    Args:
      port_id: The ID of the output port.
    """
    if port_id != self._selected_output:
      self._flows[port_id].Select()
      self._selected_output = port_id
    self._flows[port_id].Do_FSM()

  @_VideoMethod
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
    x, y, width, height = self._AutoFillArea(port_id, x, y, width, height)
    self.CaptureVideo(port_id, self._DEFAULT_FRAME_LIMIT, x, y, width, height)
    return self.ReadCapturedFrame(self._DEFAULT_FRAME_INDEX)

  def _AutoFillArea(self, port_id, x, y, width, height):
    """Verifies the area argument correctness and fills the default values.

    It keeps x=None and y=None if all of the x, y, width, and height are None.
    That hints FPGA to use a full-screen capture, not a cropped-sccren capture.

    Args:
      port_id: The ID of the video input port.
      x: The X position of the top-left corner.
      y: The Y position of the top-left corner.
      width: The width of the area.
      height: The height of the area.

    Returns:
      A tuple of (x, y, width, height)

    Raises:
      DriverError if the area is not specified correctly.
    """
    if (x, y, width, height) == (None, ) * 4:
      return (None, None) + self.DetectResolution(port_id)
    elif (x, y) == (None, ) * 2 or None not in (x, y, width, height):
      return (x, y, width, height)
    else:
      raise DriverError('Some of area arguments are not specified.')

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
    return self._flows[port_id].GetMaxFrameLimit(width, height)

  def _PrepareCapturingVideo(self, port_id, x, y, width, height):
    """Prepares capturing video on the given video input.

    Args:
      port_id: The ID of the video input port.
      x: The X position of the top-left corner of crop.
      y: The Y position of the top-left corner of crop.
      width: The width of the area of crop.
      height: The height of the area of crop.
    """
    self._SelectInput(port_id)
    if not self.IsPlugged(port_id):
      raise DriverError('HPD is unplugged. No signal is expected.')

    is_dual_pixel_mode = self._flows[port_id].IsDualPixelMode()
    # Check the alignment for a cropped-screen capture.
    if None not in (x, y):
      if is_dual_pixel_mode:
        if x % 16 or width % 16:
          raise DriverError('Arguments x and width not aligned to 16-byte.')
      else:
        if x % 8 or width % 8:
          raise DriverError('Arguments x and width not aligned to 8-byte.')

    self._captured_params = {
      'port_id': port_id,
      'resolution': (width, height),
      'is_dual_pixel': is_dual_pixel_mode,
      'pixeldump_args': self._flows[port_id].GetPixelDumpArgs(),
    }

  @_VideoMethod
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
    x, y, width, height = self._AutoFillArea(port_id, x, y, width, height)
    self._PrepareCapturingVideo(port_id, x, y, width, height)

    max_frame_limit = self.GetMaxFrameLimit(port_id, width, height)
    logging.info('Start capturing video from port #%d', port_id)
    self._flows[port_id].StartDumpingFrames(
        max_frame_limit, x, y, width, height, self._MAX_CAPTURED_FRAME_COUNT)

  def StopCapturingVideo(self):
    """Stops video capturing which was started previously.

    Raises:
      DriverError if the capture period is longer than the capture limitation.
    """
    port_id = self._captured_params['port_id']
    self._flows[port_id].StopDumpingFrames()
    logging.info('Stopped capturing video from port #%d', port_id)
    if self.GetCapturedFrameCount() >= self._MAX_CAPTURED_FRAME_COUNT:
      raise DriverError('Exceeded the limit of capture, frame_count >= %d' %
                        self._MAX_CAPTURED_FRAME_COUNT)

  @_VideoMethod
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
    x, y, width, height = self._AutoFillArea(port_id, x, y, width, height)
    logging.info('Capture video from port #%d', port_id)
    max_frame_limit = self.GetMaxFrameLimit(port_id, width, height)
    if total_frame > max_frame_limit:
      raise DriverError('Exceed the max frame limit %d > %d',
                        total_frame, max_frame_limit)

    self._PrepareCapturingVideo(port_id, x, y, width, height)
    # TODO(waihong): Make the timeout value based on the FPS rate.
    self._flows[port_id].DumpFramesToLimit(
        total_frame, x, y, width, height, self._TIMEOUT_FRAME_DUMP_PROBE)

  def GetCapturedFrameCount(self):
    """Gets the total count of the captured frames.

    Returns:
      The number of frames captured.
    """
    port_id = self._captured_params['port_id']
    return self._flows[port_id].GetDumpedFrameCount()

  def GetCapturedResolution(self):
    """Gets the resolution of the captured frame.

    If a cropping area is specified on capturing, returns the cropped
    resolution.

    Returns:
      A (width, height) tuple.
    """
    return self._captured_params['resolution']

  def ReadCapturedFrame(self, frame_index):
    """Reads the content of the captured frames from the buffer.

    Args:
      frame_index: The index of the frame to read.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    port_id = self._captured_params['port_id']
    total_frame = self.GetCapturedFrameCount()
    width, height = self.GetCapturedResolution()
    max_frame_limit = self.GetMaxFrameLimit(port_id, width, height)
    # The captured frames are store in a circular buffer. Only the latest
    # max_frame_limit frames are valid.
    first_valid_index = max(0, total_frame - max_frame_limit)
    if not first_valid_index <= frame_index < total_frame:
      raise DriverError('The frame index is out-of-range: %d not in [%d, %d)' %
                        (frame_index, first_valid_index, total_frame))

    # Specify the proper arguemnt for dual-buffer capture.
    if self._captured_params['is_dual_pixel']:
      width = width / 2

    # Modify the memory offset to match the frame.
    PAGE_SIZE = 4096
    frame_size = width * height * self._PIXEL_LEN
    frame_size = ((frame_size - 1) / PAGE_SIZE + 1) * PAGE_SIZE
    offset = frame_size * (frame_index % max_frame_limit)
    offset_args = []
    for arg in self._captured_params['pixeldump_args']:
      if isinstance(arg, (int, long)):
        offset_args.append(arg + offset)
      else:
        offset_args.append(arg)
    logging.info('pixeldump args %r', offset_args)

    with tempfile.NamedTemporaryFile() as f:
      self._tools.Call('pixeldump', f.name, width, height,
                       self._PIXEL_LEN, *offset_args)
      screen = f.read()
    return xmlrpclib.Binary(screen)

  def GetCapturedChecksums(self, start_index=0, stop_index=None):
    """Gets the list of checksums of the captured frames.

    Args:
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of checksums of frames.
    """
    port_id = self._captured_params['port_id']
    total_frame = self.GetCapturedFrameCount()
    if stop_index is None:
      stop_index = total_frame
    if not 0 <= start_index < total_frame:
      raise DriverError('The start index is out-of-range: %d not in [0, %d)' %
                        (start_index, total_frame))
    if not 0 < stop_index <= total_frame:
      raise DriverError('The stop index is out-of-range: %d not in (0, %d]' %
                        (stop_index, total_frame))
    return self._flows[port_id].GetFrameHashes(start_index, stop_index)

  @_VideoMethod
  def ComputePixelChecksum(self, port_id, x=None, y=None, width=None,
        height=None):
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
    x, y, width, height = self._AutoFillArea(port_id, x, y, width, height)
    self.CaptureVideo(port_id, self._DEFAULT_FRAME_LIMIT, x, y, width, height)
    return self.GetCapturedChecksums(self._DEFAULT_FRAME_INDEX,
                                     self._DEFAULT_FRAME_INDEX + 1)[0]

  @_VideoMethod
  def DetectResolution(self, port_id):
    """Detects the video source resolution.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A (width, height) tuple.
    """
    self._SelectInput(port_id)
    resolution = self._flows[port_id].GetResolution()
    logging.info('Detected resolution on port #%d: %dx%d', port_id, *resolution)
    return resolution

  @_AudioMethod(input_only=True)
  def StartCapturingAudio(self, port_id):
    """Starts capturing audio.

    Args:
      port_id: The ID of the audio input port.
    """
    self._SelectInput(port_id)
    logging.info('Start capturing audio from port #%d', port_id)
    self._flows[port_id].StartCapturingAudio()

  @_AudioMethod(input_only=True)
  def StopCapturingAudio(self, port_id):
    """Stops capturing audio and returns recorded audio raw data.

    Args:
      port_id: The ID of the audio input port.

    Returns:
      A tuple (data, format).
      data: The captured audio data wrapped in an xmlrpclib.Binary object.
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
    if (self._selected_input != port_id):
      raise DriverError(
          'The input is selected to %r not %r', self._selected_input, port_id)
    data, data_format = self._flows[port_id].StopCapturingAudio()
    logging.info('Stopped capturing audio from port #%d', port_id)
    return xmlrpclib.Binary(data), data_format

  @_AudioMethod(output_only=True)
  def StartPlayingAudio(self, port_id, data, data_format):
    """Playing audio data from an output port.

    Unwrap audio data and play that data from port_id port.

    Args:
      port_id: The ID of the output connector.
      data: The audio data to play wrapped in xmlrpclib.Binary.
      data_format: The dict representation of AudioDataFormat.
        Refer to docstring of utils.audio.AudioDataFormat for detail.
        Currently Chameleon only accepts data format if it meets
        dict(file_type='raw', sample_format='S32_LE', channel=8, rate=48000)
        Chameleon user should do the format conversion to minimize work load
        on Chameleon board.

    Raises:
      DriverError: There is any audio input port recording.
    """
    self._SelectOutput(port_id)
    logging.info('Start playing audio from port #%d', port_id)
    self._flows[port_id].StartPlayingAudioData((data.data, data_format))

  @_AudioMethod(output_only=True)
  def StartPlayingEcho(self, port_id, input_id):
    """Echoes audio data received from input_id and plays to port_id.

    Echoes audio data received from input_id and plays to port_id.

    Args:
      port_id: The ID of the output connector. Check the value in ids.py.
      input_id: The ID of the input connector. Check the value in ids.py.

    Raises:
      DriverError: input_id is not valid for audio operation.
    """
    if not ids.IsAudioPort(input_id) or not ids.IsInputPort(input_id):
      raise DriverError(
          'Not a valid input_id for audio operation: %d' % input_id)
    self._SelectInput(input_id)
    self._SelectOutput(port_id)
    logging.info('Start playing echo from port #%d using source from port#%d',
                 port_id, input_id)
    self._flows[port_id].StartPlayingEcho(input_id)

  @_AudioMethod(output_only=True)
  def StopPlayingAudio(self, port_id):
    """Stops playing audio from port_id port.

    Args:
      port_id: The ID of the output connector.

    Raises:
      DriverError: Output is selected to port other than port_id.
        This happens if user has used API related to output operation on other
        port. The API includes StartPlayingAudio, StartPlayingEcho.
    """
    if (self._selected_output != port_id):
      raise DriverError(
          'The output is selected to %r not %r', self._selected_output, port_id)
    logging.info('Stop playing audio from port #%d', port_id)
    self._flows[port_id].StopPlayingAudio()
