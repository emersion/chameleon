# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Input flow module which abstracts the entire flow for a specific input."""

import logging
from abc import ABCMeta

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import common
from chameleond.utils import edid
from chameleond.utils import fpga
from chameleond.utils import ids
from chameleond.utils import io
from chameleond.utils import rx


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

  # Delay in second to ensure at least one frame is dumped.
  _DELAY_VIDEO_DUMP_PROBE = 0.1

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
    self.WaitVideoOutputStable()

  def GetPixelDumpArgs(self):
    """Gets the arguments of pixeldump tool which selects the proper buffers."""
    return fpga.VideoDumper.GetPixelDumpArgs(self._input_id,
                                             self.IsDualPixelMode())

  @classmethod
  def GetConnectorType(cls):
    """Returns the human readable string for the connector type."""
    return cls._CONNECTOR_TYPE

  def _GetResolutionFromFpgaForDualPixelMode(self):
    """Gets the resolution reported from the FPGA for dual pixel mode."""
    resolution0 = (self._fpga.vdump0.GetWidth(), self._fpga.vdump0.GetHeight())
    resolution1 = (self._fpga.vdump1.GetWidth(), self._fpga.vdump1.GetHeight())
    if self._input_id != ids.VGA and resolution0 != resolution1:
      logging.warn('Different resolutions between paths: %dx%d != %dx%d',
                   *(resolution0 + resolution1))
    return (resolution0[0] + resolution1[0], resolution0[1])

  def _GetResolutionFromFpga(self):
    """Gets the resolution reported from the FPGA."""
    if self.IsDualPixelMode():
      return self._GetResolutionFromFpgaForDualPixelMode()
    else:
      vdump = self._GetEffectiveVideoDumpers()[0]
      return (vdump.GetWidth(), vdump.GetHeight())

  def GetResolution(self):
    """Gets the resolution of the video flow."""
    self.WaitVideoOutputStable()
    return self._GetResolutionFromFpga()

  def _GetEffectiveVideoDumpers(self):
    """Gets effective video dumpers on the flow."""
    if self.IsDualPixelMode():
      return [self._fpga.vdump0, self._fpga.vdump1]
    elif fpga.VideoDumper.PRIMARY_FLOW_INDEXES[self._input_id] == 0:
      return [self._fpga.vdump0]
    else:
      return [self._fpga.vdump1]

  def GetMaxFrameLimit(self):
    """Returns of the maximal number of frames which can be dumped."""
    vdump = self._GetEffectiveVideoDumpers()[0]
    return vdump.GetMaxFrameLimit(self.IsDualPixelMode())

  def _StopVideoDump(self):
    """Stops video dump."""
    for vdump in self._GetEffectiveVideoDumpers():
      vdump.Stop()

  def _StartVideoDump(self):
    """Starts video dump."""
    for vdump in self._GetEffectiveVideoDumpers():
      vdump.Start(self._input_id, self.IsDualPixelMode())

  def _IsVideoDumpFrameReady(self):
    """Returns true if FPGA dumps at least one frame.

    The function assumes that the frame count starts at zero.
    """
    dumpers = self._GetEffectiveVideoDumpers()
    target_count = len(dumpers)
    ready_count = 0
    for dumper in dumpers:
      if dumper.GetFrameCount():
        ready_count = ready_count + 1
    return ready_count == target_count

  def WaitForVideoDumpFrameReady(self, timeout):
    """Waits until FPGA dumps at least one frame."""
    common.WaitForCondition(self._IsVideoDumpFrameReady, True,
        self._DELAY_VIDEO_DUMP_PROBE, timeout)

  def RestartVideoDump(self, frame_limit=None):
    """Restarts video dump.

    Args:
      frame_limit: The limitation of frame to dump.
    """
    self._StopVideoDump()
    if frame_limit:
      for vdump in self._GetEffectiveVideoDumpers():
        vdump.SetFrameLimit(frame_limit)
    self._StartVideoDump()

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
    resolution_fpga = self._GetResolutionFromFpga()
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

  # TODO(waihong): Implement the following methods for VGA.

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    return True

  def IsPlugged(self):
    """Returns if the HPD line is plugged."""
    return True

  def Plug(self):
    """Asserts HPD line to high, emulating plug."""
    pass

  def Unplug(self):
    """Deasserts HPD line to low, emulating unplug."""
    pass

  def ReadEdid(self):
    """Reads the EDID content."""
    return self._edid.ReadEdid()

  def WriteEdid(self, data):
    """Writes the EDID content."""
    self._edid.WriteEdid(data)

  def WaitVideoInputStable(self, unused_timeout=None):
    """Waits the video input stable or timeout."""
    return True

  def WaitVideoOutputStable(self, unused_timeout=None):
    """Waits the video output stable or timeout."""
    return True
