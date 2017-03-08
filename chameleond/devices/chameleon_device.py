# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleon device's basic class.."""

import chameleon_common  # pylint: disable=W0611


class ChameleonDevice(object):
  """A basic class of chameleon devices.

  It provides the basic interfaces of Chameleon devices.
  """
  _DEVICE_NAME = 'Unknown'  # A subclass should override it.

  def __init__(self, device_name=None):
    """Constructs a ChameleonDevice object.

    Args:
      device_name: Specify device name of this chameleon device. If it is not
      specified it will use _DEVICE_NAME as its device_name.
    """
    if device_name:
      self._device_name = device_name
    else:
      self._device_name = self._DEVICE_NAME

  def IsDetected(self):
    """Returns if the device can be detected."""
    raise NotImplementedError('IsDetected')

  def InitDevice(self):
    """Init the real device of chameleon board."""
    raise NotImplementedError('InitDevice')

  def Reset(self):
    """Reset chameleon device."""
    raise NotImplementedError('Reset')

  def GetDeviceName(self):
    """Returns the human readable string for the device."""
    return self._device_name


# TODO(mojahsu): Seperate Pluggable and Selectable APIs to 2 devices class.
class Flow(ChameleonDevice):
  """An abstraction of the entire flow for a specific input.

  It provides the basic interfaces of Chameleond driver for a specific input.
  Using this abstraction, each flow can have its own behavior. No need to
  share the same Chameleond driver code.
  """
  def __init__(self):
    """Constructs a Flow object."""
    super(Flow, self).__init__()

  # TODO(mojahsu): use InitDevice to replace it
  def Initialize(self):
    """Initializes the input flow."""
    raise NotImplementedError('Initialize')

  def IsPhysicalPlugged(self):
    """Returns if the physical cable is plugged."""
    raise NotImplementedError('IsPhysicalPlugged')

  def IsPlugged(self):
    """Returns if the flow is plugged."""
    raise NotImplementedError('IsPlugged')

  def Plug(self):
    """Emulates plug."""
    raise NotImplementedError('Plug')

  def Unplug(self):
    """Emulates unplug."""
    raise NotImplementedError('Unplug')

  def Select(self):
    """Selects the flow."""
    raise NotImplementedError('Select')

  def DoFSM(self):
    """Does the Finite-State-Machine to ensure the input flow ready."""
    pass

  # TODO(mojahsu) Replace it with GetDeviceName()
  def GetConnectorType(self):
    """Returns the human readable string for the connector type."""
    return self.GetDeviceName()
