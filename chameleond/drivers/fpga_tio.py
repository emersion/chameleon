# -*- coding: utf-8 -*-
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

from chameleond.devices import audio_board
from chameleond.devices import avsync_probe
from chameleond.devices import bluetooth_hid_flow
from chameleond.devices import codec_flow
from chameleond.devices import input_flow
from chameleond.devices import motor_board
from chameleond.devices import usb_audio_flow
from chameleond.devices import usb_hid_flow
from chameleond.devices import usb_printer_device
from chameleond.utils import caching_server
from chameleond.utils import device_manager
from chameleond.utils import fpga
from chameleond.utils import flow_manager
from chameleond.utils import i2c
from chameleond.utils import ids
from chameleond.utils import system_tools
from chameleond.utils import usb
from chameleond.utils import usb_printer_control
from chameleond.utils.common import lazy
from chameleond.utils import bluetooth_a2dp

class DriverError(Exception):
  """Exception raised when any error on FPGA driver."""
  pass


def _DeviceMethod(device_id):
  """Decorator that checks if the device exists.

  Args:
    device_id: The device ID.
  """
  def _ActualDecorator(func):
    @functools.wraps(func)
    def wrapper(instance, *args, **kwargs):
      if not instance.HasDevice(device_id):
        raise DriverError('There is no %s' % ids.DEVICE_NAMES[device_id])
      return func(instance, *args, **kwargs)
    return wrapper
  return _ActualDecorator


class ChameleondDriver(ChameleondInterface):
  """Chameleond Driver for FPGA customized platform."""

  _I2C_BUS_MAIN = 0
  _I2C_BUS_AUDIO_CODEC = 1
  _I2C_BUS_EXT_BOARD = 3

  # Time to wait for video frame dump to start before a timeout error is raised
  _TIMEOUT_FRAME_DUMP_PROBE = 60.0

  # The frame index which is used for the regular DumpPixels API.
  _DEFAULT_FRAME_INDEX = 0
  _DEFAULT_FRAME_LIMIT = _DEFAULT_FRAME_INDEX + 1

  # Limit the period of async capture to 3min (in 60fps).
  _MAX_CAPTURED_FRAME_COUNT = 3 * 60 * 60

  def __init__(self, *args, **kwargs):
    super(ChameleondDriver, self).__init__(*args, **kwargs)

    # The default platform is 'fpga', and could be 'chromeos' if specified.
    platform = kwargs.get('platform', 'fpga')
    self._captured_params = {}
    self._process = None

    logging.info("platform: %s", platform)

    # waihong@chromium.org suggests to use a lazy wrapper which instantiates
    # the following control objects when requested at the first time.
    self._main_bus = lazy(i2c.I2cBus)(self._I2C_BUS_MAIN)
    self._ext_board_bus = lazy(i2c.I2cBus)(self._I2C_BUS_EXT_BOARD)
    self._audio_codec_bus = lazy(i2c.I2cBus)(self._I2C_BUS_AUDIO_CODEC)
    self._fpga_ctrl = lazy(fpga.FpgaController)()
    self._usb_audio_ctrl = lazy(usb.USBAudioController)()
    self._usb_hid_ctrl = lazy(usb.USBController)('g_hid')
    self._usb_printer_ctrl = lazy(usb_printer_control.USBPrinterController)()
    self._bluetooth_hid_ctrl = lazy(usb.USBController)(
        bluetooth_hid_flow.BluetoothHIDMouseFlow.DRIVER)
    self._bluetooth_a2dp_sink_ctrl = lazy(usb.USBController)(
        bluetooth_a2dp.BluetoothA2DPSinkFlow.DRIVER)
    # See explanation for using DRIVER_MODULE in bluetooth_nrf52.py
    self._ble_hid_ctrl = lazy(usb.USBController)(
        bluetooth_hid_flow.BleHIDMouseFlow.DRIVER_MODULE)

    if platform == 'chromeos':
      self._devices = self.init_devices_for_chromeos()
    else:
      self._devices = self.init_devices_for_fpga()

    self._device_manager = device_manager.DeviceManager(self._devices)
    self._device_manager.Init()
    self._flows = self._device_manager.GetDetectedFlows()

    # Allow to access the methods through object.
    # Hence, there is no need to export the methods in ChameleondDriver.
    # An object in the following would be None if it is not instantiated
    # in self._devices above.
    self.audio_board = self._device_manager.GetChameleonDevice(ids.AUDIO_BOARD)
    self.bluetooth_mouse = self._device_manager.GetChameleonDevice(
        ids.BLUETOOTH_HID_MOUSE)
    self.avsync_probe = self._device_manager.GetChameleonDevice(
        ids.AVSYNC_PROBE)
    self.motor_board = self._device_manager.GetChameleonDevice(ids.MOTOR_BOARD)
    self.printer = self._device_manager.GetChameleonDevice(ids.USB_PRINTER)
    self.bluetooth_a2dp_sink = self._device_manager.GetChameleonDevice(
        ids.BLUETOOTH_A2DP_SINK)
    self.ble_mouse = self._device_manager.GetChameleonDevice(
        ids.BLE_MOUSE)
    self._flow_manager = flow_manager.FlowManager(self._flows)

    self.Reset()

  def init_devices_for_chromeos(self):
    devices = {
        ids.BLUETOOTH_HID_MOUSE:
            bluetooth_hid_flow.BluetoothHIDMouseFlow(
                ids.BLUETOOTH_HID_MOUSE, self._bluetooth_hid_ctrl),
        ids.BLUETOOTH_A2DP_SINK:
            bluetooth_a2dp.BluetoothA2DPSinkFlow(
                ids.BLUETOOTH_A2DP_SINK, self._bluetooth_a2dp_sink_ctrl),
        ids.BLE_MOUSE:
            bluetooth_hid_flow.BleHIDMouseFlow(
                ids.BLE_MOUSE, self._ble_hid_ctrl),
    }
    return devices

  def init_devices_for_fpga(self):
    devices = {
        ids.DP1: input_flow.DpInputFlow(
            ids.DP1, self._main_bus, self._fpga_ctrl),
        ids.DP2: input_flow.DpInputFlow(
            ids.DP2, self._main_bus, self._fpga_ctrl),
        ids.HDMI: input_flow.HdmiInputFlow(
            ids.HDMI, self._main_bus, self._fpga_ctrl),
        ids.VGA: input_flow.VgaInputFlow(
            ids.VGA, self._main_bus, self._fpga_ctrl),
        ids.MIC: codec_flow.InputCodecFlow(
            ids.MIC, self._audio_codec_bus, self._fpga_ctrl),
        ids.LINEIN: codec_flow.InputCodecFlow(
            ids.LINEIN, self._audio_codec_bus, self._fpga_ctrl),
        ids.LINEOUT: codec_flow.OutputCodecFlow(
            ids.LINEOUT, self._audio_codec_bus, self._fpga_ctrl),
        ids.USB_AUDIO_IN: usb_audio_flow.InputUSBAudioFlow(
            ids.USB_AUDIO_IN, self._usb_audio_ctrl),
        ids.USB_AUDIO_OUT: usb_audio_flow.OutputUSBAudioFlow(
            ids.USB_AUDIO_OUT, self._usb_audio_ctrl),
        ids.USB_KEYBOARD: usb_hid_flow.KeyboardUSBHIDFlow(
            ids.USB_KEYBOARD, self._usb_hid_ctrl),
        ids.USB_TOUCH: usb_hid_flow.TouchUSBHIDFlow(
            ids.USB_TOUCH, self._usb_hid_ctrl),
        ids.AVSYNC_PROBE: avsync_probe.AVSyncProbe(ids.AVSYNC_PROBE),
        ids.AUDIO_BOARD: audio_board.AudioBoard(self._ext_board_bus),
        ids.MOTOR_BOARD: motor_board.MotorBoard(self._ext_board_bus),
        ids.USB_PRINTER: usb_printer_device.USBPrinter(self._usb_printer_ctrl),
    }

    return devices

  def Reset(self):
    """Resets Chameleon board."""
    logging.info('Execute the reset process')
    self._flow_manager.Reset()
    self._device_manager.Reset()

    self._ClearAudioFiles()
    self._ClearPrinterFiles()
    caching_server.ClearCachedDir()

  def Reboot(self):
    """Reboots Chameleon board."""
    logging.info('The chameleon board is going to reboot.')
    system_tools.SystemTools.Call('reboot')

  def GetDetectedStatus(self):
    """Returns detetcted status of all devices.

    User can use this API to know the capability of the chameleon board.

    Returns:
      A list of a tuple of detected devices' strings detected status.
      e.g. [('HDMI', True), ('MIC', False)]
    """
    detected_list = []
    for device_id in self._devices:
      detected = False
      if self._device_manager.GetChameleonDevice(device_id):
        detected = True
      detected_list.append((ids.DEVICE_NAMES[device_id], detected))
    return detected_list

  def GetSupportedPorts(self):
    """Returns all supported ports on the board.

    Not like the ProbePorts() method which only returns the ports which
    are connected, this method returns all supported ports on the board.

    Returns:
      A tuple of port_id, for all supported ports on the board.
    """
    return self._flow_manager.GetSupportedPorts()

  def GetSupportedInputs(self):
    """Returns all supported input ports on the board.

    Not like the ProbeInputs() method which only returns the input ports which
    are connected, this method returns all supported input ports on the board.

    Returns:
      A tuple of port_id, for all supported input port on the board.
    """
    return self._flow_manager.GetSupportedInputs()

  def GetSupportedOutputs(self):
    """Returns all supported output ports on the board.

    Not like the ProbeOutputs() method which only returns the output ports which
    are connected, this method returns all supported output ports on the board.

    Returns:
      A tuple of port_id, for all supported output port on the board.
    """
    return self._flow_manager.GetSupportedOutputs()

  def IsPhysicalPlugged(self, port_id):
    """Returns true if the physical cable is plugged between DUT and Chameleon.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    return self._flow_manager.IsPhysicalPlugged(port_id)

  def ProbePorts(self):
    """Probes all the connected ports on Chameleon board.

    Returns:
      A tuple of port_id, for the ports connected to DUT.
    """
    return self._flow_manager.ProbePorts()

  def ProbeInputs(self):
    """Probes all the connected input ports on Chameleon board.

    Returns:
      A tuple of port_id, for the input ports connected to DUT.
    """
    return self._flow_manager.ProbeInputs()

  def ProbeOutputs(self):
    """Probes all the connected output ports on Chameleon board.

    Returns:
      A tuple of port_id, for the output ports connected to DUT.
    """
    return self._flow_manager.ProbeOutputs()

  def GetConnectorType(self, port_id):
    """Returns the human readable string for the connector type.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      A string, like "HDMI", "DP", "MIC", etc.
    """
    return self._flow_manager.GetConnectorType(port_id)

  def HasAudioSupport(self, port_id):
    """Returns true if the port has audio support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has audio support; otherwise, False.
    """
    return self._flow_manager.HasAudioSupport(port_id)

  def HasVideoSupport(self, port_id):
    """Returns true if the port has video support.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the input/output port has video support; otherwise, False.
    """
    return self._flow_manager.HasVideoSupport(port_id)

  def SetVgaMode(self, port_id, mode):
    """Sets the mode for VGA monitor.

    Args:
      port_id: The ID of the VGA port.
      mode: A string of the mode name, e.g. 'PC_1920x1080x60'. Use 'auto'
            to detect the VGA mode automatically.
    """
    return self._flow_manager.SetVgaMode(port_id, mode)

  def WaitVideoInputStable(self, port_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      port_id: The ID of the video input port.
      timeout: The time period to wait for.

    Returns:
      True if the video input becomes stable within the timeout period;
      otherwise, False.
    """
    return self._flow_manager.WaitVideoInputStable(port_id, timeout)

  def CreateEdid(self, edid):
    """Creates an internal record of EDID using the given byte array.

    Args:
      edid: A byte array of EDID data, wrapped in a xmlrpclib.Binary object.

    Returns:
      An edid_id.
    """
    return self._flow_manager.CreateEdid(edid)

  def DestroyEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    self._flow_manager.DestroyEdid(edid_id)

  def SetDdcState(self, port_id, enabled):
    """Sets the enabled/disabled state of DDC bus on the given video input.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable DDC bus due to an user request; False to
               disable it.
    """
    self._flow_manager.SetDdcState(port_id, enabled)

  def IsDdcEnabled(self, port_id):
    """Checks if the DDC bus is enabled or disabled on the given video input.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the DDC bus is enabled; False if disabled.
    """
    return self._flow_manager.IsDdcEnabled(port_id)

  def ReadEdid(self, port_id):
    """Reads the EDID content of the selected video input on Chameleon.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object,
      or None if the EDID is disabled.
    """
    return self._flow_manager.ReadEdid(port_id)

  def ApplyEdid(self, port_id, edid_id):
    """Applies the EDID to the selected video input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    Args:
      port_id: The ID of the video input port.
      edid_id: The ID of the EDID.
    """
    self._flow_manager.ApplyEdid(port_id, edid_id)

  def IsPlugged(self, port_id):
    """Returns true if the port is emulated as plugged.

    Args:
      port_id: The ID of the input/output port.

    Returns:
      True if the port is emualted as plugged; otherwise, False.
    """
    return self._flow_manager.IsPlugged(port_id)

  def Plug(self, port_id):
    """Emualtes plug, like asserting HPD line to high on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    return self._flow_manager.Plug(port_id)

  def Unplug(self, port_id):
    """Emulates unplug, like deasserting HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    return self._flow_manager.Unplug(port_id)

  def UnplugHPD(self, port_id):
    """Only deassert HPD line to low on a video port.

    Args:
      port_id: The ID of the input/output port.
    """
    return self._flow_manager.UnplugHPD(port_id)

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
    return self._flow_manager.FireHpdPulse(
        port_id, deassert_interval_usec, assert_interval_usec, repeat_count,
        end_level)

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
    return self._flow_manager.FireMixedHpdPulses(port_id, widths_msec)

  def ScheduleHpdToggle(self, port_id, delay_ms, rising_edge):
    """Schedules one HPD Toggle, with a delay between the toggle.

    Args:
      port_id: The ID of the video input port.
      delay_ms: Delay in milli-second before the toggle takes place.
      rising_edge: Whether the toggle should be a rising edge or a falling edge.
    """
    return self._flow_manager.ScheduleHpdToggle(port_id, delay_ms, rising_edge)

  def SetContentProtection(self, port_id, enabled):
    """Sets the content protection state on the port.

    Args:
      port_id: The ID of the video input port.
      enabled: True to enable; False to disable.
    """
    self._flow_manager.SetContentProtection(port_id, enabled)

  def IsContentProtectionEnabled(self, port_id):
    """Returns True if the content protection is enabled on the port.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the content protection is enabled; otherwise, False.
    """
    return self._flow_manager.IsContentProtectionEnabled(port_id)

  def IsVideoInputEncrypted(self, port_id):
    """Returns True if the video input on the port is encrypted.

    Args:
      port_id: The ID of the video input port.

    Returns:
      True if the video input is encrypted; otherwise, False.
    """
    return self._flow_manager.IsVideoInputEncrypted(port_id)

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
    return self._flow_manager.GetMaxFrameLimit(port_id, width, height)

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
    self._flow_manager.SelectInput(port_id)
    if not self._flow_manager.IsPlugged(port_id):
      raise DriverError('HPD is unplugged. No signal is expected.')
    self._captured_params = {
        'port_id': port_id,
        'max_frame_limit': self._flow_manager.GetMaxFrameLimit(port_id,
                                                               width, height)
    }

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
    self._flow_manager.StartDumpingFrames(
        port_id, max_frame_limit, x, y, width, height,
        self._MAX_CAPTURED_FRAME_COUNT)

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

    self._flow_manager.StopDumpingFrames(port_id)
    logging.info('Stopped capturing video from port #%d', port_id)
    if self.GetCapturedFrameCount() >= self._MAX_CAPTURED_FRAME_COUNT:
      raise DriverError('Exceeded the limit of capture, frame_count >= %d' %
                        self._MAX_CAPTURED_FRAME_COUNT)

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
    self._flow_manager.DumpFramesToLimit(
        port_id, total_frame, x, y, width, height,
        self._TIMEOUT_FRAME_DUMP_PROBE)

  def GetCapturedFrameCount(self):
    """Gets the total count of the captured frames.

    Returns:
      The number of frames captured.
    """
    port_id = self._captured_params['port_id']
    return self._flow_manager.GetDumpedFrameCount(port_id)

  def GetCapturedResolution(self):
    """Gets the resolution of the captured frame.

    If a cropping area is specified on capturing, returns the cropped
    resolution.

    Returns:
      A (width, height) tuple.
    """
    port_id = self._captured_params['port_id']
    return self._flow_manager.GetCapturedResolution(port_id)

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
    screen = self._flow_manager.ReadCapturedFrame(port_id, frame_index)
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
    return self._flow_manager.CacheFrameThumbnail(port_id, frame_index, ratio)

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

  def DetectResolution(self, port_id):
    """Detects the video source resolution.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A (width, height) tuple.
    """
    return self._flow_manager.DetectResolution(port_id)

  def GetVideoParams(self, port_id):
    """Gets video parameters.

    Args:
      port_id: The ID of the video input port.

    Returns:
      A dict containing video parameters. Fields are omitted if unknown.
    """
    return self._flow_manager.GetVideoParams(port_id)

  def HasAudioBoard(self):
    """Returns True if there is an audio board.

    Returns:
      True if there is an audio board. False otherwise.
    """
    return self.audio_board is not None

  def HasDevice(self, device_id):
    """Returns True if there is a device.

    Returns:
      True if there is a device . False otherwise.
    """
    return self._device_manager.GetChameleonDevice(device_id) is not None

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
    return self._flow_manager.GetAudioChannelMapping(port_id)

  def GetAudioFormat(self, port_id):
    """Gets the format currently used by audio capture.

    Args:
      port_id: The ID of the audio input port.

    Returns:
      A dict containing the format properties. The keys are:
      file_type: 'raw' or 'wav'
      sample_format: 'S32_LE' for 32-bit signed integers in little-endian. See
        aplay(1) for more formats.
      channel: number of channels
      rate: sampling rate in Hz (or zero if unknown)

    Raises:
      FlowManagerError: no audio capture in progress
    """
    return self._flow_manager.GetAudioFormat(port_id).AsDict()

  def StartCapturingAudio(self, port_id, has_file=True):
    """Starts capturing audio.

    Refer to the docstring of StartPlayingEcho about the restriction of
    capturing and echoing at the same time.

    Args:
      port_id: The ID of the audio input port.
      has_file: True for saving audio data to file. False otherwise.
    """
    self._flow_manager.StartCapturingAudio(port_id, has_file)

  def StopCapturingAudio(self, port_id):
    """Stops capturing audio and returns recorded data path and format.

    Args:
      port_id: The ID of the audio input port.

    Returns:
      A tuple (path, format).
      path: The path to the captured audio data.
      format: The format of the captured data. See GetAudioFormat. Note that
        the returned audio frequency may not be correct, for this reason
        calling GetAudioFormat during the capture is preferred.
      If we assign parameter has_file=False in StartCapturingAudio, we will get
      both empty string in path and format.
    """
    return self._flow_manager.StopCapturingAudio(port_id)

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
    """
    self._flow_manager.StartPlayingAudio(port_id, path, data_format)

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
    self._flow_manager.StartPlayingEcho(port_id, input_id)

  def StopPlayingAudio(self, port_id):
    """Stops playing audio from port_id port.

    Args:
      port_id: The ID of the output connector.
    """
    self._flow_manager.StopPlayingAudio(port_id)

  def _ClearPrinterFiles(self):
    """Clears temporary printer files.

    Chameleon board does not reboot very often. We should clear the temporary
    printer files used in capturing printer data.
    """
    for path in glob.glob('/tmp/printer_*'):
      os.unlink(path)

  def _ClearAudioFiles(self):
    """Clears temporary audio files.

    Chameleon board does not reboot very often. We should clear the temporary
    audio files used in capturing audio or playing audio when Reset is called.
    """
    for path in glob.glob('/tmp/audio_*'):
      os.unlink(path)

  @_DeviceMethod(ids.AUDIO_BOARD)
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
      current_sources, _ = self.audio_board.GetConnections(bus_number)
      if current_sources and endpoint not in current_sources:
        raise DriverError(
            'Sources %s other than %s are currently occupying audio bus.' %
            (current_sources, endpoint))

    self.audio_board.SetConnection(
        bus_number, endpoint, True)

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardDisconnect(self, bus_number, endpoint):
    """Disconnects an endpoint to an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
      endpoint: An endpoint defined in audio_board.AudioBusEndpoint.

    Raises:
      DriverError: If the endpoint is not connected to audio bus.
    """
    if not self.audio_board.IsConnected(bus_number, endpoint):
      raise DriverError(
          'Endpoint %s is not connected to audio bus %d.' %
          (endpoint, bus_number))

    self.audio_board.SetConnection(
        bus_number, endpoint, False)

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardGetRoutes(self, bus_number):
    """Gets a list of routes on audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.

    Returns:
      A list of tuples (source, sink) that are routed on audio bus
      where source and sink are endpoints defined in
      audio_board.AudioBusEndpoint.
    """
    sources, sinks = self.audio_board.GetConnections(bus_number)
    routes = []
    for source in sources:
      for sink in sinks:
        logging.info('Route on bus %d: %s ---> %s',
                     bus_number, source, sink)
        routes.append((source, sink))
    return routes

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardClearRoutes(self, bus_number):
    """Clears routes on an audio bus.

    Args:
      bus_number: 1 or 2 for audio bus 1 or bus 2.
    """
    self.audio_board.ResetConnections(bus_number)

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardHasJackPlugger(self):
    """If there is jack plugger on audio board.

    Audio board must have the motor cable connected in order to control
    jack plugger of audio box.

    Returns:
      True if there is jack plugger on audio board. False otherwise.
    """
    return self.audio_board.HasJackPlugger()

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardAudioJackPlug(self):
    """Plugs audio jack to connect audio board and Cros device."""
    logging.info('Plug audio jack to connect audio board and Cros device.')
    self.audio_board.SetJackPlugger(True)

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardAudioJackUnplug(self):
    """Unplugs audio jack to disconnect audio board and Cros device."""
    logging.info('Unplug audio jack to disconnect audio board and Cros device.')
    self.audio_board.SetJackPlugger(False)

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardResetBluetooth(self):
    """Resets bluetooth module on audio board."""
    logging.info('Resets bluetooth module on audio board.')
    self.audio_board.ResetBluetooth()

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardDisableBluetooth(self):
    """Disables bluetooth module on audio board."""
    logging.info('Disables bluetooth module on audio board.')
    self.audio_board.DisableBluetooth()

  @_DeviceMethod(ids.AUDIO_BOARD)
  def AudioBoardIsBluetoothEnabled(self):
    """Checks if bluetooth module on audio board is enabled.

    Returns:
      True if bluetooth module is enabled. False otherwise.
    """
    return self.audio_board.IsBluetoothEnabled()

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
    """
    self._flow_manager.SetUSBDriverPlaybackConfigs(playback_data_format)

  def SetUSBDriverCaptureConfigs(self, capture_data_format):
    """Updates the corresponding capture configurations to argument values.

    This provides flexibility for simulating the USB gadget driver using other
    configurations different from the default values.

    Args:
      capture_data_format: The dict form of an AudioDataFormat object. The
        'file_type' field will be saved by InputUSBAudioFlow as the file type
        for captured data. Other fields are used to set USB driver
        configurations.
    """
    self._flow_manager.SetUSBDriverCaptureConfigs(capture_data_format)

  def GetMacAddress(self):
    """Gets the MAC address of this Chameleon.

    Returns:
      A string for MAC address.
    """
    return open('/sys/class/net/eth0/address').read().strip()

  def SendHIDEvent(self, port_id, event_type, *args, **kwargs):
    """Sends HID event with event_type and arguments for HID port #port_id.

    Args:
      port_id: The ID of the HID port.
      event_type: Supported event type of string for HID port #port_id.

    Returns:
      Returns as event function if applicable.
    """
    return self._flow_manager.SendHIDEvent(port_id, event_type, *args, **kwargs)

  def ResetBluetoothRef(self):
    """Reset BTREF"""
    # Reloads serial port driver if needed
    self._bluetooth_a2dp_sink_ctrl.EnableDriver()
    # Reads peripheral configuration settings
    self.bluetooth_a2dp_sink.GetBasicSettings()

  def EnableBluetoothRef(self):
    """Enable BTREF"""
    self._bluetooth_a2dp_sink_ctrl.EnableDriver()

  def DisableBluetoothRef(self):
    """Disable BTREF"""
    self.bluetooth_a2dp_sink.Close()

  def IsBluetoothRefDisabled(self):
    """Check if BTREF is enabled"""
    raise NotImplementedError('IsBluetoothRefDisabled')
