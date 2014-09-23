# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Input flow module which abstracts the entire flow for a specific input."""

import logging
import os
import tempfile
import time
from abc import ABCMeta

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import audio
from chameleond.utils import common
from chameleond.utils import edid
from chameleond.utils import fpga
from chameleond.utils import frame_manager
from chameleond.utils import ids
from chameleond.utils import io
from chameleond.utils import rx
from chameleond.utils import system_tools


class InputFlowError(Exception):
  """Exception raised when any error on InputFlow."""
  pass


class InputFlow(object):
  """An abstraction of the entire flow for a specific input.

  It provides the basic interfaces of Chameleond driver for a specific input.
  Using this abstraction, each flow can have its own behavior. No need to
  share the same Chameleond driver code.
  """
  __metaclass__ = ABCMeta

  _CONNECTOR_TYPE = 'Unknown'  # A subclass should override it.

  _RX_SLAVES = {
    ids.DP1: rx.DpRx.SLAVE_ADDRESSES[0],
    ids.DP2: rx.DpRx.SLAVE_ADDRESSES[1],
    ids.HDMI: rx.HdmiRx.SLAVE_ADDRESSES[0],
    ids.VGA: rx.VgaRx.SLAVE_ADDRESSES[0]
  }
  _MUX_CONFIGS = {
    # Use a dual-pixel-mode setting for IO as no support for two flows
    # simultaneously so far.
    ids.DP1: io.MuxIo.CONFIG_DP1_DUAL,
    ids.DP2: io.MuxIo.CONFIG_DP2_DUAL,
    ids.HDMI: io.MuxIo.CONFIG_HDMI_DUAL,
    ids.VGA: io.MuxIo.CONFIG_VGA
  }

  # Audio data format.
  _AUDIO_DATA_FORMAT = audio.AudioDataFormat(
      file_type='raw', sample_format='S32_LE', channel=8, rate=48000)

  def __init__(self, input_id, main_i2c_bus, fpga_ctrl):
    """Constructs a InputFlow object.

    Args:
      input_id: The ID of the input connector. Check the value in ids.py.
      main_i2c_bus: The main I2cBus object.
      fpga_ctrl: The FpgaController object.
    """
    self._input_id = input_id
    self._main_bus = main_i2c_bus
    self._fpga = fpga_ctrl
    self._power_io = self._main_bus.GetSlave(io.PowerIo.SLAVE_ADDRESSES[0])
    self._mux_io = self._main_bus.GetSlave(io.MuxIo.SLAVE_ADDRESSES[0])
    self._rx = self._main_bus.GetSlave(self._RX_SLAVES[self._input_id])
    self._capture_audio_start_time = None
    self._frame_manager = frame_manager.FrameManager(
        input_id, self._GetEffectiveVideoDumpers())

  def _GetEffectiveVideoDumpers(self):
    """Gets effective video dumpers on the flow."""
    if self.IsDualPixelMode():
      if fpga.VideoDumper.EVEN_PIXELS_FLOW_INDEXES[self._input_id] == 0:
        return [self._fpga.vdump0, self._fpga.vdump1]
      else:
        return [self._fpga.vdump1, self._fpga.vdump0]
    elif fpga.VideoDumper.PRIMARY_FLOW_INDEXES[self._input_id] == 0:
      return [self._fpga.vdump0]
    else:
      return [self._fpga.vdump1]

  def Initialize(self):
    """Initializes the input flow."""
    logging.info('Initialize InputFlow #%d.', self._input_id)
    self._power_io.ResetReceiver(self._input_id)
    self._rx.Initialize(self.IsDualPixelMode())

  def Select(self):
    """Selects the input flow to set the proper muxes and FPGA paths."""
    logging.info('Select InputFlow #%d.', self._input_id)
    self._mux_io.SetConfig(self._MUX_CONFIGS[self._input_id])
    self._fpga.vpass.Select(self._input_id)
    self._fpga.vdump0.Select(self._input_id, self.IsDualPixelMode())
    self._fpga.vdump1.Select(self._input_id, self.IsDualPixelMode())
    self._fpga.asrc.Select(self._input_id)
    self.WaitVideoOutputStable()

  def GetPixelDumpArgs(self):
    """Gets the arguments of pixeldump tool which selects the proper buffers."""
    return fpga.VideoDumper.GetPixelDumpArgs(self._input_id,
                                             self.IsDualPixelMode())

  @classmethod
  def GetConnectorType(cls):
    """Returns the human readable string for the connector type."""
    return cls._CONNECTOR_TYPE

  def GetResolution(self):
    """Gets the resolution of the video flow."""
    self.WaitVideoOutputStable()
    width, height = self._frame_manager.ComputeResolution()
    if width == 0 or height == 0:
      raise InputFlowError('Something wrong with the resolution: %dx%d' %
                           (width, height))
    return (width, height)

  def GetMaxFrameLimit(self, width, height):
    """Returns of the maximal number of frames which can be dumped."""
    if self.IsDualPixelMode():
      width = width / 2
    return fpga.VideoDumper.GetMaxFrameLimit(width, height)

  def GetFrameHashes(self, start, stop):
    """Returns the list of the frame hashes.

    Args:
      start: The index of the start frame.
      stop: The index of the stop frame (excluded).

    Returns:
      A list of frame hashes.
    """
    return self._frame_manager.GetFrameHashes(start, stop)

  def DumpFramesToLimit(self, frame_limit, x, y, width, height, timeout):
    """Dumps frames and waits for the given limit being reached or timeout.

    Args:
      frame_limit: The limitation of frame to dump.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      timeout: Time in second of timeout.

    Raises:
      common.TimeoutError on timeout.
    """
    self.WaitVideoOutputStable()
    self._frame_manager.DumpFramesToLimit(frame_limit, x, y, width, height,
                                          timeout)

  def StartCapturingAudio(self):
    """Starts capturing audio."""
    self._capture_audio_start_time = time.time()
    self._fpga.adump.StartDumpingToMemory()
    logging.info('Started capturing audio.')

  def StopCapturingAudio(self):
    """Stops capturing audio.

    Returns:
      A tuple (data, format).
      data: The captured audio data.
      format: The dict representation of AudioDataFormat. Refer to docstring
        of utils.audio.AudioDataFormat for detail.

    Raises:
      InputFlowError: If captured time or page exceeds the limit.
      InputFlowError: If there is no captured data.
    """
    if not self._capture_audio_start_time:
      raise InputFlowError('Stop Capturing audio before Start')

    captured_time_secs = time.time() - self._capture_audio_start_time
    self._capture_audio_start_time = None

    start_address, page_count = self._fpga.adump.StopDumpingToMemory()

    if page_count > self._fpga.adump.SIMPLE_DUMP_PAGE_LIMIT:
      raise InputFlowError(
          'Dumped number of pages %d exceeds the limit %d',
          page_count, self._fpga.adump.SIMPLE_DUMP_PAGE_LIMIT)

    if captured_time_secs > self._fpga.adump.SIMPLE_DUMP_TIME_LIMIT_SECS:
      raise InputFlowError(
          'Capture time %f seconds exceeds time limit %f secs' % (
              captured_time_secs, self._fpga.adump.SIMPLE_DUMP_TIME_LIMIT_SECS))

    logging.info(
        'Stopped capturing audio. Captured duration: %f seconds; '
        '4K page count: %d', captured_time_secs, page_count)

    # The page count should increase even if there is no audio data
    # sent to this input.
    if page_count == 0:
      raise InputFlowError(
          'No audio data was captured. Perhaps this input is not plugged ?')

    # Use pixeldump to dump a range of memory into file.
    # Originally, the area size is
    # screen_width * screen_height * byte_per_pixel.
    # In our use case, the area size is page_size * page_count * 1.
    with tempfile.NamedTemporaryFile() as f:
      system_tools.SystemTools.Call(
          'pixeldump', '-a', start_address, f.name, self._fpga.adump.PAGE_SIZE,
          page_count, 1)
      logging.info('Captured audio data size: %f MBytes',
                   os.path.getsize(f.name) / 1024.0 / 1024.0)
      return f.read(), self._AUDIO_DATA_FORMAT.AsDict()

  def StartDumpingFrames(self, frame_buffer_limit, x, y, width, height,
                         hash_buffer_limit):
    """Starts dumping frames continuously.

    Args:
      frame_buffer_limit: The size of the buffer which stores the frame.
                          Frames will be dumped to the beginning when full.
      x: The X position of the top-left corner of crop; None for a full-screen.
      y: The Y position of the top-left corner of crop; None for a full-screen.
      width: The width of the area of crop.
      height: The height of the area of crop.
      hash_buffer_limit: The maximum number of hashes to monitor. Stop
                         capturing when this limitation is reached.
    """
    self.WaitVideoOutputStable()
    self._frame_manager.StartDumpingFrames(
        frame_buffer_limit, x, y, width, height, hash_buffer_limit)

  def StopDumpingFrames(self):
    """Stops dumping frames."""
    self._frame_manager.StopDumpingFrames()

  def GetDumpedFrameCount(self):
    """Gets the number of frames which is dumped."""
    return self._frame_manager.GetFrameCount()

  def Do_FSM(self):
    """Does the Finite-State-Machine to ensure the input flow ready.

    The receiver requires to do the FSM in order to clear its state, in case
    of some events happended, like mode change, power reattach, etc.

    It should be called before doing any post-receiver-action, like capturing
    frames.
    """
    pass

  def WaitVideoInputStable(self, unused_timeout=None):
    """Waits the video input stable or timeout."""
    return True

  def WaitVideoOutputStable(self, unused_timeout=None):
    """Waits the video output stable or timeout."""
    return True

  def IsDualPixelMode(self):
    """Returns if the input flow uses dual pixel mode."""
    raise NotImplementedError('IsDualPixelMode')

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    raise NotImplementedError('IsPhysicalPlugged')

  def IsPlugged(self):
    """Returns if the HPD line is plugged."""
    raise NotImplementedError('IsPlugged')

  def Plug(self):
    """Asserts HPD line to high, emulating plug."""
    raise NotImplementedError('Plug')

  def Unplug(self):
    """Deasserts HPD line to low, emulating unplug."""
    raise NotImplementedError('Unplug')

  def FireHpdPulse(self, deassert_interval_usec, assert_interval_usec,
          repeat_count, end_level):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    raise NotImplementedError('FireHpdPulse')

  def ReadEdid(self):
    """Reads the EDID content."""
    raise NotImplementedError('ReadEdid')

  def WriteEdid(self, data):
    """Writes the EDID content."""
    raise NotImplementedError('WriteEdid')


class DpInputFlow(InputFlow):
  """An abstraction of the entire flow for DisplayPort."""

  _CONNECTOR_TYPE = 'DP'
  _IS_DUAL_PIXEL_MODE = False

  def __init__(self, *args):
    super(DpInputFlow, self).__init__(*args)
    self._edid = edid.DpEdid(args[0], self._main_bus)

  def IsDualPixelMode(self):
    """Returns if the input flow uses dual pixel mode."""
    return self._IS_DUAL_PIXEL_MODE

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    return self._rx.IsCablePowered()

  def IsPlugged(self):
    """Returns if the HPD line is plugged."""
    return self._fpga.hpd.IsPlugged(self._input_id)

  def Plug(self):
    """Asserts HPD line to high, emulating plug."""
    self._fpga.hpd.Plug(self._input_id)

  def Unplug(self):
    """Deasserts HPD line to low, emulating unplug."""
    self._fpga.hpd.Unplug(self._input_id)

  def FireHpdPulse(self, deassert_interval_usec, assert_interval_usec,
          repeat_count, end_level):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    self._fpga.hpd.FireHpdPulse(self._input_id, deassert_interval_usec,
            assert_interval_usec, repeat_count, end_level)

  def ReadEdid(self):
    """Reads the EDID content."""
    return self._edid.ReadEdid()

  def WriteEdid(self, data):
    """Writes the EDID content."""
    self._edid.WriteEdid(data)

  def WaitVideoInputStable(self, unused_timeout=None):
    """Waits the video input stable or timeout."""
    # TODO(waihong): Implement this method.
    return True

  def WaitVideoOutputStable(self, unused_timeout=None):
    """Waits the video output stable or timeout."""
    # TODO(waihong): Implement this method.
    return True


class HdmiInputFlow(InputFlow):
  """An abstraction of the entire flow for HDMI."""

  _CONNECTOR_TYPE = 'HDMI'
  _IS_DUAL_PIXEL_MODE = True

  _DELAY_VIDEO_MODE_PROBE = 0.1
  _TIMEOUT_VIDEO_STABLE_PROBE = 10
  _DELAY_WAITING_GOOD_PIXELS = 3

  def __init__(self, *args):
    super(HdmiInputFlow, self).__init__(*args)
    self._edid = edid.HdmiEdid(self._main_bus)

  def IsDualPixelMode(self):
    """Returns if the input flow uses dual pixel mode."""
    return self._IS_DUAL_PIXEL_MODE

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    return self._rx.IsCablePowered()

  def IsPlugged(self):
    """Returns if the HPD line is plugged."""
    return self._fpga.hpd.IsPlugged(self._input_id)

  def Plug(self):
    """Asserts HPD line to high, emulating plug."""
    self._fpga.hpd.Plug(self._input_id)

  def Unplug(self):
    """Deasserts HPD line to low, emulating unplug."""
    self._fpga.hpd.Unplug(self._input_id)

  def FireHpdPulse(self, deassert_interval_usec, assert_interval_usec,
          repeat_count, end_level):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    self._fpga.hpd.FireHpdPulse(self._input_id, deassert_interval_usec,
            assert_interval_usec, repeat_count, end_level)

  def ReadEdid(self):
    """Reads the EDID content."""
    return self._edid.ReadEdid()

  def WriteEdid(self, data):
    """Writes the EDID content."""
    self._edid.WriteEdid(data)

  def Do_FSM(self):
    """Does the Finite-State-Machine to ensure the input flow ready.

    The receiver requires to do the FSM in order to clear its state, in case
    of some events happended, like mode change, power reattach, etc.

    It should be called before doing any post-receiver-action, like capturing
    frames.
    """
    if self.WaitVideoInputStable():
      self._rx.Do_FSM()
      self.WaitVideoOutputStable()
      # TODO(waihong): Remove this hack only for Nyan-Big.
      # http://crbug.com/402152
      time.sleep(self._DELAY_WAITING_GOOD_PIXELS)
    else:
      logging.warn('Skip doing receiver FSM as video input not stable.')

  def WaitVideoInputStable(self, timeout=None):
    """Waits the video input stable or timeout."""
    if timeout is None:
      timeout = self._TIMEOUT_VIDEO_STABLE_PROBE
    try:
      common.WaitForCondition(self._rx.IsVideoInputStable, True,
          self._DELAY_VIDEO_MODE_PROBE, timeout)
    except common.TimeoutError:
      return False
    return True

  def _IsFrameLocked(self):
    """Returns whether the FPGA frame is locked.

    It compares the resolution reported from the receiver with the FPGA.

    Returns:
      True if the frame is locked; otherwise, False.
    """
    resolution_fpga = self._frame_manager.ComputeResolution()
    resolution_rx = self._rx.GetResolution()
    if resolution_fpga == resolution_rx:
      logging.info('same resolution: %dx%d', *resolution_fpga)
      return True
    else:
      logging.info('diff resolution: fpga:%dx%d != rx:%dx%d',
                   *(resolution_fpga + resolution_rx))
      return False

  def WaitVideoOutputStable(self, timeout=None):
    """Waits the video output stable or timeout."""
    if timeout is None:
      timeout = self._TIMEOUT_VIDEO_STABLE_PROBE
    try:
      common.WaitForCondition(self._IsFrameLocked, True,
          self._DELAY_VIDEO_MODE_PROBE, timeout)
    except common.TimeoutError:
      return False
    return True


class VgaInputFlow(InputFlow):
  """An abstraction of the entire flow for VGA."""

  _CONNECTOR_TYPE = 'VGA'
  _IS_DUAL_PIXEL_MODE = False

  def __init__(self, *args):
    super(VgaInputFlow, self).__init__(*args)
    self._edid = edid.VgaEdid(self._fpga)

  def IsDualPixelMode(self):
    """Returns if the input flow uses dual pixel mode."""
    return self._IS_DUAL_PIXEL_MODE

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    return self._rx.IsSyncDetected()

  def IsPlugged(self):
    """Returns if the HPD line is plugged."""
    return True

  def Plug(self):
    """Asserts HPD line to high, emulating plug."""
    pass

  def Unplug(self):
    """Deasserts HPD line to low, emulating unplug."""
    pass

  def FireHpdPulse(self, deassert_interval_usec, assert_interval_usec,
          repeat_count, end_level):
    """Fires one or more HPD pulse (low -> high -> low -> ...).

    Args:
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
                            If None, then use the same value as
                            deassert_interval_usec.
      repeat_count: The count of HPD pulses to fire.
      end_level: HPD ends with 0 for LOW (unplugged) or 1 for HIGH (plugged).
    """
    pass

  def ReadEdid(self):
    """Reads the EDID content."""
    return self._edid.ReadEdid()

  def WriteEdid(self, data):
    """Writes the EDID content."""
    self._edid.WriteEdid(data)

  # TODO(waihong): Implement the following methods for VGA.

  def WaitVideoInputStable(self, unused_timeout=None):
    """Waits the video input stable or timeout."""
    return True

  def WaitVideoOutputStable(self, unused_timeout=None):
    """Waits the video output stable or timeout."""
    return True
