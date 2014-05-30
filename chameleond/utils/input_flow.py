# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Input flow module which abstracts the entire flow for a specific input."""

import logging
from abc import ABCMeta

import chameleon_common  # pylint: disable=W0611
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
    ids.DP1: io.MuxIo.CONFIG_DP1_DUAL,
    ids.DP2: io.MuxIo.CONFIG_DP2_DUAL,
    ids.HDMI: io.MuxIo.CONFIG_HDMI_DUAL,
    ids.VGA: io.MuxIo.CONFIG_VGA
  }

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
    self._rx.Initialize()

  def Select(self):
    """Selects the input flow to set the proper muxes and FPGA paths."""
    logging.info('Select InputFlow #%d.', self._input_id)
    self._mux_io.SetConfig(self._MUX_CONFIGS[self._input_id])
    self._fpga.vpass.Select(self._input_id)
    self._fpga.vdump0.Select(self._input_id)
    self._fpga.vdump1.Select(self._input_id)

  def GetPixelDumpArgs(self):
    """Gets the arguments of pixeldump tool which selects the proper buffers."""
    return fpga.VideoDumper.GetPixelDumpArgs(self._input_id)

  def GetResolution(self):
    """Gets the resolution of the video flow."""
    # For dual pixel mode.
    resolution0 = (self._fpga.vdump0.GetWidth(), self._fpga.vdump0.GetHeight())
    resolution1 = (self._fpga.vdump1.GetWidth(), self._fpga.vdump1.GetHeight())
    if resolution0 != resolution1:
      logging.warn('Different resolutions between paths: %dx%d != %dx%d',
                   *(resolution0 + resolution1))
    return (resolution0[0] + resolution1[0], resolution0[1])

  @classmethod
  def GetConnectorType(cls):
    """Returns the human readable string for the connector type."""
    return cls._CONNECTOR_TYPE

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

  def __init__(self, *args):
    super(DpInputFlow, self).__init__(*args)
    self._edid = edid.DpEdid(args[0], self._main_bus)

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


class HdmiInputFlow(InputFlow):
  """An abstraction of the entire flow for HDMI."""

  _CONNECTOR_TYPE = 'HDMI'

  def __init__(self, *args):
    super(HdmiInputFlow, self).__init__(*args)
    self._edid = edid.HdmiEdid(self._main_bus)

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


class VgaInputFlow(InputFlow):
  """An abstraction of the entire flow for VGA."""

  _CONNECTOR_TYPE = 'VGA'

  def __init__(self, *args):
    super(VgaInputFlow, self).__init__(*args)
    self._edid = edid.VgaEdid(self._fpga)

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
