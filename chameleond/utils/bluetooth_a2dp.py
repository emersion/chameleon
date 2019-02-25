# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides emulation of bluetooth A2DP devices."""

from __future__ import print_function

from bluetooth_peripheral_kit import PeripheralKit
from bluetooth_rn52 import RN52
from chameleond.utils import bluetooth_hid
from chameleond.devices import bluetooth_hid_flow

# TODO(npoojary): Fix inheritance.
# Probably needs a separate BluetoothPeripheral
# class for both BluetoothHID and BluetoothA2DPx
# to inherit kit interface from.
class BluetoothA2DPSink(bluetooth_hid.BluetoothHID):
  """A bluetooth A2DP sink emulator class."""

  def __init__(self, authentication_mode, kit_impl):
    """Initialization of BluetoothA2DPSink

    Args:
      authentication_mode: the authentication mode
      kit_impl: the implementation of a Bluetooth HID peripheral kit to use
    """
    super(BluetoothA2DPSink, self).__init__(
        PeripheralKit.A2DP_SINK, authentication_mode, kit_impl)



# TODO(npoojary): Fix inheritance.
# Again using BluetoothHIDFlow for IsDetected(), FindAndSetTty() etc.
# These probably need to go into a common serial device class.
class BluetoothA2DPSinkFlow(
    BluetoothA2DPSink,
    bluetooth_hid_flow.BluetoothHIDFlow):
  """A flow object that emulates a Bluetooth A2DP sink."""

  DRIVER = RN52.DRIVER

  def __init__(self, port_id, usb_ctrl):
    """Initializes a BluetoothHOGMouseFlow object.

    Args:
      port_id: the port id that represents the type of port used.
      usb_ctrl: a USBController object that BluetoothA2DPFlow references to.
    """
    BluetoothA2DPSink.__init__(self, PeripheralKit.SSP_JUST_WORK_MODE, RN52)
    bluetooth_hid_flow.BluetoothHIDFlow.__init__(
        self, port_id, 'BluetoothBR/EDR', usb_ctrl,
        RN52.USB_VID, RN52.USB_PID, RN52.KNOWN_DEVICE_SET)
