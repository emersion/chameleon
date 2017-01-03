# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for FPGA customized platform with the TIO card."""

import functools
import glob
import logging
import os
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.interface import ChameleondInterface

from chameleond.utils import audio_board
from chameleond.utils import avsync_probe_flow
from chameleond.utils import bluetooth_hid_flow
from chameleond.utils import caching_server
from chameleond.utils import codec_flow
from chameleond.utils import fpga
from chameleond.utils import i2c
from chameleond.utils import ids
from chameleond.utils import input_flow
from chameleond.utils import system_tools
from chameleond.utils import usb
from chameleond.utils import usb_audio_flow
from chameleond.utils import usb_hid_flow


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


def _AudioBoardMethod(func):
  """Decorator that checks there is an audio board."""
  @functools.wraps(func)
  def wrapper(instance, *args, **kwargs):
    if not instance.HasAudioBoard():
      raise DriverError('There is no audio board')
    return func(instance, *args, **kwargs)
  return wrapper


def _USBHIDMethod(func):
  """Decorator that checks the port_id argument is a USB HID port."""
  @functools.wraps(func)
  def wrapper(instance, port_id, *args, **kwargs):
    if not ids.IsUSBHIDPort(port_id):
      raise DriverError('Not a valid port_id for HID operation: %d' % port_id)
    return func(instance, port_id, *args, **kwargs)
  return wrapper


class ChameleondDriver(ChameleondInterface):
  """Chameleond Driver for FPGA customized platform."""

  _I2C_BUS_MAIN = 0
  _I2C_BUS_AUDIO_CODEC = 1
  _I2C_BUS_AUDIO_BOARD = 3

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
    self._process = None
    # Reserve index 0 as the default EDID.
    self._all_edids = [self._ReadDefaultEdid()]

    main_bus = i2c.I2cBus(self._I2C_BUS_MAIN)
    audio_codec_bus = i2c.I2cBus(self._I2C_BUS_AUDIO_CODEC)
    fpga_ctrl = fpga.FpgaController()
    usb_audio_ctrl = usb.USBAudioController()
    usb_hid_ctrl = usb.USBController('g_hid')
    bluetooth_hid_ctrl = usb.USBController('ftdi_sio')

    self._flows = {
        ids.DP1: input_flow.DpInputFlow(ids.DP1, main_bus, fpga_ctrl),
        ids.DP2: input_flow.DpInputFlow(ids.DP2, main_bus, fpga_ctrl),
        ids.HDMI: input_flow.HdmiInputFlow(ids.HDMI, main_bus, fpga_ctrl),
        ids.VGA: input_flow.VgaInputFlow(ids.VGA, main_bus, fpga_ctrl),
        ids.MIC: codec_flow.InputCodecFlow(ids.MIC, audio_codec_bus, fpga_ctrl),
        ids.LINEIN: codec_flow.InputCodecFlow(ids.LINEIN, audio_codec_bus,
                                              fpga_ctrl),
        ids.LINEOUT: codec_flow.OutputCodecFlow(
            ids.LINEOUT, audio_codec_bus, fpga_ctrl),
        ids.USB_AUDIO_IN: usb_audio_flow.InputUSBAudioFlow(
            ids.USB_AUDIO_IN, usb_audio_ctrl),
        ids.USB_AUDIO_OUT: usb_audio_flow.OutputUSBAudioFlow(
            ids.USB_AUDIO_OUT, usb_audio_ctrl),
        ids.USB_KEYBOARD: usb_hid_flow.KeyboardUSBHIDFlow(
            ids.USB_KEYBOARD, usb_hid_ctrl),
        ids.USB_TOUCH: usb_hid_flow.TouchUSBHIDFlow(
            ids.USB_TOUCH, usb_hid_ctrl),
        ids.BLUETOOTH_HID_MOUSE: bluetooth_hid_flow.BluetoothHIDMouseFlow(
            ids.BLUETOOTH_HID_MOUSE, bluetooth_hid_ctrl),
        ids.AVSYNC_PROBE: avsync_probe_flow.AVSyncProbeFlow(ids.AVSYNC_PROBE),
    }

    # Allow to accees the mouse methods through bluetooth_mouse member object.
    # Hence, there is no need to export the mouse methods in ChameleondDriver.
    self.bluetooth_mouse = self._flows[ids.BLUETOOTH_HID_MOUSE]
    self.avsync_probe = self._flows[ids.AVSYNC_PROBE]

    for flow in self._flows.itervalues():
      if flow:
        flow.Initialize()

    # Some Chameleon might not have audio board installed.
    self._audio_board = None
    try:
      audio_board_bus = i2c.I2cBus(self._I2C_BUS_AUDIO_BOARD)
      self._audio_board = audio_board.AudioBoard(audio_board_bus)
    except audio_board.AudioBoardException:
      logging.warning('There is no audio board on this Chameleon')
    else:
      logging.info('There is an audio board on this Chameleon')

    self.Reset()

  def Reset(self):
    """Resets Chameleon board."""
    logging.info('Execute the reset process')
    # TODO(waihong): Add other reset routines.
    logging.info('Apply the default EDID and enable DDC on all video inputs')
    for port_id in self.GetSupportedInputs():
      if self.HasVideoSupport(port_id):
        self.ApplyEdid(port_id, ids.EDID_ID_DEFAULT)
        self.SetDdcState(port_id, enabled=True)
    for port_id in self.GetSupportedPorts():
      if self.HasAudioSupport(port_id):
        # Stops all audio capturing.
        if ids.IsInputPort(port_id) and self._flows[port_id].is_capturing_audio:
          self._flows[port_id].StopCapturingAudio()

        self._flows[port_id].ResetRoute()

    if self.HasAudioBoard():
      self._audio_board.Reset()

    self._ClearAudioFiles()
    caching_server.ClearCachedDir()

    # Set all ports unplugged on initialization.
    for port_id in self.GetSupportedPorts():
      self.Unplug(port_id)

  def Reboot(self):
    """Reboots Chameleon board."""
    logging.info('The chameleon board is going to reboot.')
    system_tools.SystemTools.Call('reboot')

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
  def SetDdcState(self, port_id, enabled):
    """Sets the enabled/disabled state of DDC bus on the given video input.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable DDC bus due to an user request; False to
               disable it.
    """
    logging.info('Set DDC bus on port #%d to enabled %r', port_id, enabled)
    self._flows[port_id].SetDdcState(enabled)

  @_VideoMethod
  def IsDdcEnabled(self, port_id):
    """Checks if the DDC bus is enabled or disabled on the given video input.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the DDC bus is enabled; False if disabled.
    """
    return self._flows[port_id].IsDdcEnabled()

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
    return self._flows[port_id].FireHpdPulse(
        deassert_interval_usec, assert_interval_usec, repeat_count, end_level)

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

  @_VideoMethod
  def SetContentProtection(self, port_id, enabled):
    """Sets the content protection state on the port.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable; False to disable.
    """
    logging.info('Set content protection on port #%d: %r', port_id, enabled)
    self._flows[port_id].SetContentProtection(enabled)

  @_VideoMethod
  def IsContentProtectionEnabled(self, port_id):
    """Returns True if the content protection is enabled on the port.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the content protection is enabled; otherwise, False.
    """
    return self._flows[port_id].IsContentProtectionEnabled()

  @_VideoMethod
  def IsVideoInputEncrypted(self, port_id):
    """Returns True if the video input on the port is encrypted.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the video input is encrypted; otherwise, False.
    """
    return self._flows[port_id].IsVideoInputEncrypted()

  def _SelectInput(self, port_id):
    """Selects the input on Chameleon.

    Args:
      port_id: The ID of the input port.
    """
    if port_id != self._selected_input:
      self._flows[port_id].Select()
      self._selected_input = port_id
    self._flows[port_id].DoFSM()

  def _SelectOutput(self, port_id):
    """Selects the output on Chameleon.

    Args:
      port_id: The ID of the output port.
    """
    if port_id != self._selected_output:
      self._flows[port_id].Select()
      self._selected_output = port_id
    self._flows[port_id].DoFSM()

  def StartMonitoringAudioVideoCapturingDelay(self):
    """Starts an audio/video synchronization utility

    The example of usage:
      chameleon.StartMonitoringAudioVideoCapturingDelay()
      chameleon.StartCapturingVideo(hdmi_input)
      chameleon.StartCapturingAudio(hdmi_input)
      time.sleep(2)
      chameleon.StopCapturingVideo()
      chameleon.StopCapturingAudio(hdmi_input)
      delay = chameleon.GetAudioVideoCapturingDelay()
    """
    self._process = system_tools.SystemTools.RunInSubprocess('avsync')

  def GetAudioVideoCapturingDelay(self):
    """Get the time interval between the first audio/video cpatured data

    Returns:
      A floating points indicating the time interval between the first
      audio/video data captured. If the result is negative, then the first
      video data is earlier, otherwise the first audio data is earlier.

    Raises:
      DriverError if there is no output from the monitoring process.
    """

    if self._process.poll() == None:
      self._process.terminate()
      raise DriverError('The monitoring process has not finished.')

    return_code, out, err = system_tools.SystemTools.GetSubprocessOutput(
        self._process)

    if return_code != 0 or err:
      raise DriverError('Runtime error in the monitoring process')

    if not out:
      raise DriverError('No output from the monitoring process.')

    return float(out)

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
    # This result is related to the video flow status, e.g.
    # single/dual pixel mode, progressive/interlaced mode.
    # Need to select the input flow first.
    self._SelectInput(port_id)
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
    caching_server.ClearCachedDir()
    self._SelectInput(port_id)
    if not self.IsPlugged(port_id):
      raise DriverError('HPD is unplugged. No signal is expected.')
    self._captured_params = {
        'port_id': port_id,
        'max_frame_limit': self._flows[port_id].GetMaxFrameLimit(width, height)
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
    max_frame_limit = self._captured_params['max_frame_limit']
    logging.info('Start capturing video from port #%d', port_id)
    self._flows[port_id].StartDumpingFrames(
        max_frame_limit, x, y, width, height, self._MAX_CAPTURED_FRAME_COUNT)

  def StopCapturingVideo(self, stop_index=None):
    """Stops video capturing which was started previously.

    Args:
      stop_index: Wait for the captured frame count to reach this index. If
                  not given, stop immediately. Note that the captured frame of
                  stop_index should not be read.

    Raises:
      DriverError if the capture period is longer than the capture limitation.
    """
    port_id = self._captured_params['port_id']
    if stop_index:
      if stop_index >= self._MAX_CAPTURED_FRAME_COUNT:
        raise DriverError('Exceeded the limit of capture, stop_index >= %d' %
                          self._MAX_CAPTURED_FRAME_COUNT)
      logging.info('Waiting the captured frame count reaches %d...', stop_index)
      while self.GetCapturedFrameCount() < stop_index:
        pass

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
    self._PrepareCapturingVideo(port_id, x, y, width, height)
    max_frame_limit = self._captured_params['max_frame_limit']
    if total_frame > max_frame_limit:
      raise DriverError('Exceed the max frame limit %d > %d',
                        total_frame, max_frame_limit)

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
    port_id = self._captured_params['port_id']
    return self._flows[port_id].GetCapturedResolution()

  def ReadCapturedFrame(self, frame_index):
    """Reads the content of the captured frame from the buffer.

    Args:
      frame_index: The index of the frame to read.

    Returns:
      A byte-array of the pixels, wrapped in a xmlrpclib.Binary object.
    """
    port_id = self._captured_params['port_id']
    total_frame = self.GetCapturedFrameCount()
    max_frame_limit = self._captured_params['max_frame_limit']
    # The captured frames are store in a circular buffer. Only the latest
    # max_frame_limit frames are valid.
    first_valid_index = max(0, total_frame - max_frame_limit)
    if not first_valid_index <= frame_index < total_frame:
      raise DriverError('The frame index is out-of-range: %d not in [%d, %d)' %
                        (frame_index, first_valid_index, total_frame))

    # Use the projected index.
    frame_index = frame_index % max_frame_limit
    screen = self._flows[port_id].ReadCapturedFrame(frame_index)
    return xmlrpclib.Binary(screen)

  def CacheFrameThumbnail(self, frame_index, ratio=2):
    """Caches the thumbnail of the dumped field to a temp file.

    Args:
      frame_index: The index of the frame to cache.
      ratio: The ratio to scale down the image.

    Returns:
      An ID to identify the cached thumbnail.
    """
    port_id = self._captured_params['port_id']
    return self._flows[port_id].CacheFrameThumbnail(frame_index, ratio)

  def _GetCapturedSignals(self, signal_func_name, start_index=0,
                          stop_index=None):
    """Gets the list of signals of the captured frames.

    Args:
      signal_func_name: The name of the signal function, e.g. 'GetFrameHashes'.
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of signals.
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
    signal_func = getattr(self._flows[port_id], signal_func_name)
    return signal_func(start_index, stop_index)

  def GetCapturedChecksums(self, start_index=0, stop_index=None):
    """Gets the list of checksums of the captured frames.

    Args:
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of checksums of frames.
    """
    return self._GetCapturedSignals('GetFrameHashes', start_index, stop_index)

  def GetCapturedHistograms(self, start_index=0, stop_index=None):
    """Gets the list of histograms of the captured frames.

    Args:
      start_index: The index of the start frame. Default is 0.
      stop_index: The index of the stop frame (excluded). Default is the
                  value of GetCapturedFrameCount.

    Returns:
      The list of histograms of frames.
    """
    return self._GetCapturedSignals('GetHistograms', start_index, stop_index)

  @_VideoMethod
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

  def HasAudioBoard(self):
    """Returns True if there is an audio board.

    Returns:
      True if there is an audio board. False otherwise.
    """
    return self._audio_board is not None

  @_AudioMethod(input_only=True)
  def StartCapturingAudio(self, port_id):
    """Starts capturing audio.

    Refer to the docstring of StartPlayingEcho about the restriction of
    capturing and echoing at the same time.

    Args:
      port_id: The ID of the audio input port.
    """
    self._SelectInput(port_id)
    logging.info('Start capturing audio from port #%d', port_id)
    self._flows[port_id].StartCapturingAudio()

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

    Raises:
      DriverError: Input is selected to port other than port_id.
        This happens if user has used API related to input operation on
        other port. The API includes CaptureVideo, StartCapturingVideo,
        DetectResolution, StartCapturingAudio, StartPlayingEcho.
    """
    if self._selected_input != port_id:
      raise DriverError(
          'The input is selected to %r not %r', self._selected_input, port_id)
    path, data_format = self._flows[port_id].StopCapturingAudio()
    logging.info('Stopped capturing audio from port #%d', port_id)
    return path, data_format

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
      DriverError: There is no file at the path.
    """
    if not os.path.exists(path):
      raise DriverError('File path %r does not exist' % path)
    self._SelectOutput(port_id)
    logging.info('Start playing audio from port #%d', port_id)
    self._flows[port_id].StartPlayingAudio(path, data_format)

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
    if self._selected_output != port_id:
      raise DriverError(
          'The output is selected to %r not %r', self._selected_output, port_id)
    logging.info('Stop playing audio from port #%d', port_id)
    self._flows[port_id].StopPlayingAudio()

  def _ClearAudioFiles(self):
    """Clears temporary audio files.

    Chameleon board does not reboot very often. We should clear the temporary
    audio files used in capturing audio or playing audio when Reset is called.
    """
    for path in glob.glob('/tmp/audio_*'):
      os.unlink(path)

  @_AudioBoardMethod
  def AudioBoardConnect(self, bus_number, endpoint):
    """Connects an endpoint to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in audio_board.AudioBusEndpoint.

    Raises:
      DriverError: If the endpoint is a source and there is other source
                   endpoint occupying audio bus.
    """
    if audio_board.IsSource(endpoint):
      current_sources, _ = self._audio_board.GetConnections(bus_number)
      if current_sources and endpoint not in current_sources:
        raise DriverError(
            'Sources %s other than %s are currently occupying audio bus.' %
            (current_sources, endpoint))

    self._audio_board.SetConnection(
        bus_number, endpoint, True)

  @_AudioBoardMethod
  def AudioBoardDisconnect(self, bus_number, endpoint):
    """Disconnects an endpoint to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in audio_board.AudioBusEndpoint.

    Raises:
      DriverError: If the endpoint is not connected to audio bus.
    """
    if not self._audio_board.IsConnected(bus_number, endpoint):
      raise DriverError(
          'Endpoint %s is not connected to audio bus %d.' %
          (endpoint, bus_number))

    self._audio_board.SetConnection(
        bus_number, endpoint, False)

  @_AudioBoardMethod
  def AudioBoardGetRoutes(self, bus_number):
    """Gets a list of routes on audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.

    Returns:
      A list of tuples (source, sink) that are routed on audio bus
      where source and sink are endpoints defined in
      audio_board.AudioBusEndpoint.
    """
    sources, sinks = self._audio_board.GetConnections(bus_number)
    routes = []
    for source in sources:
      for sink in sinks:
        logging.info('Route on bus %d: %s ---> %s',
                     bus_number, source, sink)
        routes.append((source, sink))
    return routes

  @_AudioBoardMethod
  def AudioBoardClearRoutes(self, bus_number):
    """Clears routes on an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
    """
    self._audio_board.ResetConnections(bus_number)

  @_AudioBoardMethod
  def AudioBoardHasJackPlugger(self):
    """If there is jack plugger on audio board.

    Audio board must have the motor cable connected in order to control
    jack plugger of audio box.

    Returns:
      True if there is jack plugger on audio board. False otherwise.
    """
    return self._audio_board.HasJackPlugger()

  @_AudioBoardMethod
  def AudioBoardAudioJackPlug(self):
    """Plugs audio jack to connect audio board and Cros device."""
    logging.info('Plug audio jack to connect audio board and Cros device.')
    self._audio_board.SetJackPlugger(True)

  @_AudioBoardMethod
  def AudioBoardAudioJackUnplug(self):
    """Unplugs audio jack to disconnect audio board and Cros device."""
    logging.info('Unplug audio jack to disconnect audio board and Cros device.')
    self._audio_board.SetJackPlugger(False)

  @_AudioBoardMethod
  def AudioBoardResetBluetooth(self):
    """Resets bluetooth module on audio board."""
    logging.info('Resets bluetooth module on audio board.')
    self._audio_board.ResetBluetooth()

  @_AudioBoardMethod
  def AudioBoardDisableBluetooth(self):
    """Disables bluetooth module on audio board."""
    logging.info('Disables bluetooth module on audio board.')
    self._audio_board.DisableBluetooth()

  @_AudioBoardMethod
  def AudioBoardIsBluetoothEnabled(self):
    """Checks if bluetooth module on audio board is enabled.

    Returns:
      True if bluetooth module is enabled. False otherwise.
    """
    return self._audio_board.IsBluetoothEnabled()

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
      DriverError if any of the USB Flows is playing or capturing audio.
    """
    if (self._flows[ids.USB_AUDIO_IN].is_capturing_audio or
        self._flows[ids.USB_AUDIO_OUT].is_playing_audio):
      error_message = ('Configuration changes not allowed when USB audio '
                       'driver is still performing playback/capture in one of '
                       'the flows.')
      raise DriverError(error_message)
    self._flows[ids.USB_AUDIO_OUT].SetDriverPlaybackConfigs(
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
      DriverError if any of the USB audio Flows is playing or capturing audio.
    """
    if (self._flows[ids.USB_AUDIO_IN].is_capturing_audio or
        self._flows[ids.USB_AUDIO_OUT].is_playing_audio):
      error_message = ('Configuration changes not allowed when USB audio '
                       'driver is still performing playback/capture in one of '
                       'the flows.')
      raise DriverError(error_message)
    self._flows[ids.USB_AUDIO_IN].SetDriverCaptureConfigs(capture_data_format)

  def GetMacAddress(self):
    """Gets the MAC address of this Chameleon.

    Returns:
      A string for MAC address.
    """
    return open('/sys/class/net/eth0/address').read().strip()

  @_USBHIDMethod
  def SendHIDEvent(self, port_id, event_type, *args, **kwargs):
    """Sends HID event with event_type and arguments for HID port #port_id.

    Args:
      port_id: The ID of the HID port.
      event_type: Supported event type of string for HID port #port_id.

    Returns:
      Returns as event function if applicable.
    """
    return self._flows[port_id].Send(event_type, *args, **kwargs)
