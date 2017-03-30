# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A manager for all chameleon devices."""

import logging

from chameleond.devices import chameleon_device
from chameleond.utils import ids


class DeviceManager(object):
  """A device manager for managing chameleon devices."""

  def __init__(self, devices_table):
    """Constructs a DeviceManager object.

    Args:
      devices_table: The table of chameleon devices. It's a dict with device
          id as key and a device object as value. The parent class of the
          of the device must be a ChameleonDevice.
          User can't change the content of devices_table at runtime.
          If the object inherit from class Flow means that the device is a flow
          based device.
          e.g.
          {
              ids.AVSYNC_PROBE: avsync_probe_object,
              ids.DP1: dp1_object,
              ids.DP2: dp2_object
          }
    """
    self._devices_table = devices_table
    self._detected_devices = {}
    self._detected_flows = {}

  def Init(self):
    """Detect and initialize all chameleon devices."""
    self._detected_devices = {}
    self._detected_flows = {}
    for device_id, device in self._devices_table.iteritems():
      name = ids.DEVICE_NAMES[device_id]
      if not device.IsDetected():
        logging.info('Device %s is not detected', name)
        continue
      logging.info('Device %s is detected', name)
      self._detected_devices.update({device_id: device})
      if isinstance(device, chameleon_device.Flow):
        self._detected_flows.update({device_id: device})
        logging.info('Add device %s, port #%d to detected flow',
                     name, device_id)

    for device in self._detected_devices.values():
      device.InitDevice()

  def Reset(self):
    """Reset all detected chameleon devices."""
    for device in self._detected_devices.values():
      device.Reset()

  def GetChameleonDevice(self, device_id):
    """Get exist chameleon device instance.

    Args:
      device_id: The id of the device.

    Returns:
      An chameleon device object. None for undetected device.
    """
    return self._detected_devices.get(device_id)

  def GetDetectedFlows(self):
    """Get exist flow-based chameleon devices' instance.

    Returns:
      A dict with port id as a key and flow object as value.
    """
    return self._detected_flows
