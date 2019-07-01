# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The control interface of Bluetooth flow for Raspi devices."""

from chameleond.devices import chameleon_device
from chameleond.utils.bluetooth_raspi import BluezPeripheral
from chameleond.utils.raspi_bluez_service import BluezKeyboardService


class RaspiFlow(chameleon_device.Flow):
  """The control interface of a Raspi bluetooth (Bluez-based) device."""

  # Should be BluezPeripheral for builtin bluetooth peripheral. May be different for
  # other subclasses (e.g. Intel ThP2 solution).

  def __init__(self):
    """Initializes a Raspi flow object."""
    super(RaspiFlow, self).__init__()
    self._bluez = BluezPeripheral()
    self._dev_addr = self._bluez.GetLocalBluetoothAddress()
    self._bluez_service = None

  def IsDetected(self):
    """Returns true if BT adapter is detected."""
    return self._dev_addr is not None

  def InitDevice(self):
    """Initialize Bluez device.

    Initializing Bluez parameters is mostly done in __init__().
    This function initializes the service.
    """
    self._bluez_service = BluezKeyboardService(self._dev_addr)
    return

  def Reset(self):
    return

  def Select(self):
    return

  def GetConnectorType(self):
    return None

  def IsPhysicalPlugged(self):
    return True

  def IsPlugged(self):
    return True

  def Plug(self):
    return

  def Unplug(self):
    return

  def DoFSM(self):
    return
