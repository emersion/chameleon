# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleond Driver for Pygprobe."""

import logging
import re
import tempfile
import time
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.interface import ChameleondInterface
from pygprobe import cmdline_commands, common  # pylint: disable=F0401


class ChameleondDriver(ChameleondInterface):
  """Chameleond Driver for Pygprobe."""

  _PIXEL_FORMAT = 'rrggbb'

  _ALL_INPUTS = ['RESERVED', 'DP', 'DVI', 'HDMI', 'VGA']  # index starts at 1

  def __init__(self, usb_serial=None, *args, **kwargs):
    super(ChameleondDriver, self).__init__(*args, **kwargs)
    self._hdmi_initialized = False
    self._selected_input = 0
    self._all_edids = ['RESERVED']  # index starts at 1
    self._loaded_edid = 0
    self._scan_input_pattern = re.compile(
        r'(\w+)\n  Cable Status *= ([01])\n  Cable Source *power *= ([01])',
        re.MULTILINE)
    logging.info('Use USB serial device: %s', usb_serial)
    self._serial_device = common.USBSerialDevice(usb_serial)

  def Reset(self):
    """Resets Chameleon board."""
    self._serial_device.Flush()
    cmdline_commands.Reset(self._serial_device)

  def IsHealthy(self):
    """Returns if the Chameleon is healthy or any repair is needed.

    Returns:
      True if the Chameleon is healthy; otherwise, False, need to repair.
    """
    return True

  def Repair(self):
    """Repairs the Chameleon.

    It can be an asynchronous call, e.g. do the repair after return. An
    approximate time of the repair is returned. The caller should wait that
    time before the next action.

    Returns:
      An approximate repair time in second.
    """
    return 0

  def GetSupportedInputs(self):
    """Returns all supported connectors on the board.

    Not like the ProbeInputs() method which only returns the connectors which
    are connected, this method returns all supported connectors on the board.

    Returns:
      A tuple of input_id, for all supported connectors on the board.
    """
    return range(1, len(self._ALL_INPUTS))

  def IsPhysicalPlugged(self, input_id):
    """Returns if the physical cable is plugged.

    It checks the source power +5V/+3.3V pin.

    Returns:
      True if the physical cable is plugged; otherwise, False.
    """
    # Always return True, for compatibility.
    return True

  def ProbeInputs(self):
    """Probes all the display connectors on Chameleon board.

    Returns:
      A tuple of input_id, for the connectors connected to DUT.
    """
    input_ids = []
    # XXX: The board need to select HDMI first to initialize its video
    # pipeline; otherwise, Chrome OS can't see the HDMI external screen.
    if not self._hdmi_initialized:
      self._SelectInput(3)  # HDMI
      self._hdmi_initialized = True
    self._serial_device.Flush()
    message = cmdline_commands.ScanInput(self._serial_device)

    # Parse the output message of ScanInput().
    matches = self._scan_input_pattern.findall(message)
    for m in matches:
      source, status, _ = m
      if status == '1':
        if source == 'DisplayPort':  # Rename DisplayPort.
          source = 'DP'
        # Use the index of _ALL_INPUTS as input_id.
        input_ids.append(self._ALL_INPUTS.index(source))

    return input_ids

  def _SelectInput(self, input_id):
    """Selects the input on Chameleon.

    Args:
      input_id: The ID of the input connector.
    """
    if input_id != self._selected_input:
      connector = self.GetConnectorType(input_id)
      self._serial_device.Flush()
      cmdline_commands.SelectInput(self._serial_device, connector)
      self._selected_input = input_id

  def GetConnectorType(self, input_id):
    """Returns the human readable string for the connector type.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A string, like "VGA", "DVI", "HDMI", or "DP".
    """
    return self._ALL_INPUTS[input_id]

  def WaitVideoInputStable(self, input_id, timeout=None):
    """Waits the video input stable or timeout.

    Args:
      input_id: The ID of the input connector.
      timeout: The time period to wait for.

    Returns:
      True if the video input becomes stable within the timeout period;
      otherwise, False.
    """
    # Always return True, for compatibility.
    return True

  def _LoadEdidToBuffer(self, edid_id):
    """Loads the EDID to host buffer. Will be applied later.

    It doesn't load again if the edid_id is loaded before.

    Args:
      edid_id: The ID of the EDID.
    """
    if edid_id != self._loaded_edid:
      edid = self._all_edids[edid_id]
      with tempfile.NamedTemporaryFile() as f:
        f.write(edid)
        f.flush()
        self._serial_device.Flush()
        cmdline_commands.LoadEDID(self._serial_device, f.name)
      self._loaded_edid = edid_id

  def CreateEdid(self, edid):
    """Creates an internal record of EDID using the given byte array.

    Args:
      edid: A byte array of EDID data, wrapped in a xmlrpclib.Binary object.

    Returns:
      An edid_id.
    """
    if None in self._all_edids:  # None means previously-freed slot.
      last = self._all_edids.index(None)
      self._all_edids[last] = edid.data
    else:
      last = len(self._all_edids)
      self._all_edids.append(edid.data)
    # Pre-load the EDID to buffer, to speed-up the time of applying it later.
    self._LoadEdidToBuffer(last)
    return last

  def DestroyEdid(self, edid_id):
    """Destroys the internal record of EDID. The internal data will be freed.

    Args:
      edid_id: The ID of the EDID, which was created by CreateEdid().
    """
    # Mark None to free the slot.
    self._all_edids[edid_id] = None

  def ReadEdid(self, input_id):
    """Reads the EDID content of the selected input on Chameleon.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A byte array of EDID data, wrapped in a xmlrpclib.Binary object.
    """
    self._SelectInput(input_id)
    self._serial_device.Flush()
    connector = self.GetConnectorType(input_id)
    if connector == 'DP':
      edid = cmdline_commands.DumpDPEDID(self._serial_device)
    elif connector == 'HDMI':
      edid = cmdline_commands.DumpHDMIEDID(self._serial_device)
    else:
      raise NotImplementedError('ReadEdid')
    return xmlrpclib.Binary(edid)

  def ApplyEdid(self, input_id, edid_id):
    """Applies the EDID to the selected input.

    Note that this method doesn't pulse the HPD line. Should call Plug(),
    Unplug(), or FireHpdPulse() later.

    XXX: Current Chameleon firmware does fire HPD pulse after applying the EDID
    on DisplayPort interface. This behavior breaks the above rule.

    Args:
      input_id: The ID of the input connector.
      edid_id: The ID of the EDID.
    """
    self._LoadEdidToBuffer(edid_id)
    self._SelectInput(input_id)
    self._serial_device.Flush()
    connector = self.GetConnectorType(input_id)
    if connector == 'DP':
      cmdline_commands.ApplyDisplayPortEDID(self._serial_device)
    elif connector == 'HDMI':
      cmdline_commands.ApplyHDMIEDID(self._serial_device)
    else:
      raise NotImplementedError('ApplyEdid')

  def IsPlugged(self, input_id):
    """Returns if the HPD line is plugged.

    Args:
      input_id: The ID of the input connector.

    Returns:
      True if the HPD line is plugged; otherwise, False.
    """
    # Always return True, as this version of Chameleon board can't unplug,
    # so it is supposed to be always plugged.
    return True

  def Plug(self, input_id):
    """Asserts HPD line to high, emulating plug.

    Args:
      input_id: The ID of the input connector.
    """
    # Do nothing, as this version of Chameleon board can't unplug,
    # so it is supposed to be always plugged.
    pass

  def Unplug(self, input_id):
    """Deasserts HPD line to low, emulating unplug.

    Args:
      input_id: The ID of the input connector.
    """
    raise NotImplementedError('Unplug')

  def FireHpdPulse(self, input_id, deassert_interval_usec,
                   assert_interval_usec=None, repeat_count=1):
    """Fires a HPD pulse (high -> low -> high) or multiple HPD pulses.

    Args:
      input_id: The ID of the input connector.
      deassert_interval_usec: The time in microsecond of the deassert pulse.
      assert_interval_usec: The time in microsecond of the assert pulse.
      repeat_count: The count of repeating the HPD pulses.
    """
    self._SelectInput(input_id)
    self._serial_device.Flush()
    connector = self.GetConnectorType(input_id)
    # Only support HDMI HPD pulse.
    if connector == 'HDMI':
      deassert_in_10ms = deassert_interval_usec / 10000
      assert_in_sec = float(assert_interval_usec) / 1000000
      for i in range(repeat_count):
        # SetHDMIHPDPulse only accepts integer and the unit is 10ms.
        cmdline_commands.SetHDMIHPDPulse(self._serial_device, deassert_in_10ms)
        if i != repeat_count - 1:
          time.sleep(assert_in_sec)
    else:
      raise NotImplementedError('FireHpdPulse')

  def GetPixelFormat(self):
    """Returns the pixel format for the output of DumpPixels.

    Returns:
      A string of the format, like 'rgba', 'bgra', 'rgb', etc.
    """
    return self._PIXEL_FORMAT

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
    if x is not None and y is not None and width and height:
      self._SelectInput(input_id)
      self._serial_device.Flush()
      pixels, _ = cmdline_commands.DumpPixels(
          self._serial_device, x, y, width, height)
      return xmlrpclib.Binary(pixels)
    else:
      raise NotImplementedError('DumpPixels')

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
    if x is not None and y is not None and width and height:
      self._SelectInput(input_id)
      self._serial_device.Flush()
      _, checksum = cmdline_commands.DumpPixels(
          self._serial_device, x, y, width, height)
      return checksum
    else:
      raise NotImplementedError('ComputePixelChecksum')

  def DetectResolution(self, input_id):
    """Detects the source resolution.

    Args:
      input_id: The ID of the input connector.

    Returns:
      A (width, height) tuple.
    """
    raise NotImplementedError('DetectResolution')
