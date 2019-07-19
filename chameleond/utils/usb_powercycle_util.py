# -*- coding: utf-8 -*-
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module implement code to powercycle USB port on fizz board."""

import collections
import logging
import subprocess
import time


TOKEN_NEW_BUS = '/:  '
TOKEN_ROOT_DEVICE = '\n    |__ '

PortId = collections.namedtuple('PortId', ['bus', 'port_number'])

# Mapping from bus ID and port number to the GPIO Index.
# We know of no way to detect this through tools, why the board
# specific setup is hard coded here.
_PORT_ID_TO_GPIO_INDEX_DICT = {'fizz':{
    # USB 2 bus.
    PortId(bus=1, port_number=3): 4,  # Front right USB 2, near the power button
    PortId(bus=1, port_number=4): 5,  # Front left USB 2, next to audio jack
    PortId(bus=1, port_number=5): 1,  # Back left USB 2, next to ethernet port
    PortId(bus=1, port_number=6): 2,  # Back middle USB 2
    PortId(bus=1, port_number=2): 3,  # Back right USB 2, next to power port
    # USB 3 bus.
    PortId(bus=2, port_number=3): 4,  # Front right USB 3, near the power button
    PortId(bus=2, port_number=4): 5,  # Front left USB 3, next to audio jack
    PortId(bus=2, port_number=5): 1,  # Back left USB 3, next to ethernet port
    PortId(bus=2, port_number=6): 2,  # Back middle USB 3
    PortId(bus=2, port_number=2): 3,  # Back right USB 3, next to power port
}}

def PowerCycleUSBPort(usb_vid, usb_pid):
  """Cycle power to USB port where usb device with vid:pid is connected

  This function finds the USB bus ID and port number where vid:pid is
  connected and maps it to the GPIO index. The USB port is then power
  cycled using 'ectool gpioset' command.

  On Fizz, there are in total 5 usb ports and per port usb power
  is controlled by EC with user space command:
  ectool gpioset USBx_ENABLE 0/1 (x from 1 to 5).

  This function is works only on fizz boards running chameleond. Write
  protection needs to be removed from chameleond host for 'ectool gpioset'
  command to work. This function is intented to reset the bluetooth dongles.
  Note: RN-42 and RN-52 has the same vid:pid so both will be powercycled.

  This is based on code in
  autotest/files/client/common_lib/cros/cfm/usb/usb_port_manager.py
  and autotest/files/client/common_lib/cros/power_cycle_usb_util.py.

  Args:
    usb_vid: The USB VID (Vendor ID) as a hexadecimal string
    usb_pid: The USB PID (Product ID) as a hexadecimal string

  Returns:
    True: If the port was powercycled
  """

  def _run(cmd):
    logging.debug('running command %s', cmd)
    result = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                     shell=True).strip('\n')
    logging.debug('cmd result is  %s', result)
    return result

  def _get_gpio_index(board, port_id):
    logging.debug('_get_gpio_index board %s port_id %s', board, port_id)
    try:
      index = _PORT_ID_TO_GPIO_INDEX_DICT[board][port_id]
    except KeyError:
      logging.debug('gpio index not found')
      return None
    else:
      logging.debug('returning %s', index)
      return index

  def _get_board():
    """Get the board name."""
    try:
      board = _run('mosys platform name').lower()
      return board
    except subprocess.CalledProcessError:
      logging.debug('Unable to get board name')
      return None

  def _cycle_gpio_power_fizz(gpio_idx):
    """Turns on or off the power for a specific GPIO on board Fizz.

    Args gpio_idx The index of the gpio to set the power for.
    Args power_on If True, powers on the GPIO. If False, powers it off.
    """
    if gpio_idx not in range(1, 6):
      logging.error('Invalid GPIO %s', gpio_idx)
      return False

    status = True
    try:
      cmd = 'ectool gpioset USB%s_ENABLE %s' % (gpio_idx, 0)
      _run(cmd)
    except subprocess.CalledProcessError:
      logging.error('Powering off GPIO failed %s', gpio_idx)
      status = False
      # Proceed with power on even if power off fails

    # Hold the power off for 1 second to make sure the device resets.
    time.sleep(1)

    try:
      cmd = 'ectool gpioset USB%s_ENABLE %s' % (gpio_idx, 1)
      logging.debug('command is %s', cmd)
      _run(cmd)
    except subprocess.CalledProcessError:
      logging.error('Powering on GPIO %s failed', gpio_idx)
      status = False
    return status

  def _get_bus_dev_id(lsusb_output, vid, pid):
    """Get bus number and device index device(s) are connected to on DUT.

    Get the bus number and port number of the usb port the target perpipharel
    device is connected to based on the output of command 'lsusb -d VID:PID'.

    Args lsusb_output: output of command 'lsusb -d VID:PID' running on DUT.
    Args vid: Vendor ID of the peripharel device.
    Args pid: Product ID of the peripharel device.

    Returns [(bus number, device index)], if device not found,
          returns (None, None)
    """

    result = []
    if lsusb_output == '':
      return result

    lsusb_device_info = lsusb_output.strip().split('\n')

    for line in lsusb_device_info:
      # An example of the info line is 'Bus 001 Device 006:  ID 266e:0110 '
      fields = line.split(' ')
      assert len(fields) >= 6, 'Wrong format: %s' % lsusb_device_info
      target_bus_idx = int(fields[1])
      target_device_idx = int(fields[3][:-1])
      logging.debug('found target device %s:%s, bus: %d, dev: %d',
                    vid, pid, target_bus_idx, target_device_idx)
      result.append((target_bus_idx, target_device_idx))
    logging.debug("Returning %s from get_bus_dev_id", result)
    return result

  def _get_port_number(lsusb_tree_output, bus, dev):
    """Get port number that certain device is connected to on DUT.

    Get the port number of the usb port that the target peripharel device is
    connected to based on the output of command 'lsusb -t', its bus number and
    device index.
    An example of lsusb_tree_output could be:
    /:  Bus 02.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/4p, 5000M
        |__ Port 2: Dev 2, If 0, Class=Hub, Driver=hub/4p, 5000M
    /:  Bus 01.Port 1: Dev 1, Class=root_hub, Driver=xhci_hcd/11p, 480M
        |__ Port 2: Dev 52, If 0, Class=Hub, Driver=hub/4p, 480M
            |__ Port 1: Dev 55, If 0, Class=Human Interface Device,
                        Driver=usbhid, 12M
            |__ Port 3: Dev 54, If 0, Class=Vendor Specific Class,
                        Driver=udl, 480M
        |__ Port 3: Dev 3, If 0, Class=Hub, Driver=hub/4p, 480M
        |__ Port 4: Dev 4, If 0, Class=Wireless, Driver=btusb, 12M
        |__ Port 4: Dev 4, If 1, Class=Wireless, Driver=btusb, 12M

    Args lsusb_tree_output: The output of command 'lsusb -t' on DUT.
    Args bus: The bus number the peripharel device is connected to.
    Args dev: The device index of the peripharel device on DUT.

    Returns the target port number, if device not found, returns None.
    """
    lsusb_device_buses = lsusb_tree_output.strip().split(TOKEN_NEW_BUS)
    target_bus_token = 'Bus {:02d}.'.format(bus)
    for bus_info in lsusb_device_buses:
      if bus_info.find(target_bus_token) != 0:
        continue
      target_dev_token = 'Dev %s' % dev
      device_info = bus_info.strip(target_bus_token).split(TOKEN_ROOT_DEVICE)
      for device in device_info:
        if target_dev_token not in device:
          continue
        target_port_number = int(device.split(':')[0].split(' ')[1])
        return target_port_number
    return None

  def _get_port_numbers_from_vidpid(vid, pid):
    """Get bus number and port number a device is connected to on DUT.

    Get the bus number and port number of the usb port the target perpipharel
    device is connected to.

    Args vid: Vendor ID of the peripharel device.
    Args pid: Product ID of the peripharel device.

    Returns the target bus number and port number, if device not found, returns
          (None, None).
    """
    cmd = 'lsusb -d %s:%s' %(vid, pid)
    try:
      lsusb_output = _run(cmd)
    except subprocess.CalledProcessError:
      logging.debug('lsusb command failed')
      return []

    bus_dev_list = _get_bus_dev_id(lsusb_output, vid, pid)
    logging.debug('bus_devices are  %s', bus_dev_list)
    if bus_dev_list == []:
      return []

    cmd = 'lsusb -t'
    try:
      lsusb_output = _run(cmd)
    except subprocess.CalledProcessError:
      logging.debug('lsusb -t command failed')
      return []

    result = []
    for (target_bus_idx, target_dev_idx) in bus_dev_list:
      target_port_number = _get_port_number(
          lsusb_output, target_bus_idx, target_dev_idx)
      if target_port_number is None:
        continue
      else:
        result.append((target_bus_idx, target_port_number))
    logging.debug('returning %s from get_port_number_from_vidpid', result)
    return result


  logging.debug('PowerCycleUSBPort: usb_vid %s usb_pid %s', usb_vid, usb_pid)

  board = _get_board()
  if board != 'fizz':
    logging.debug('PowerCycleUSBPort: This function is supported only'
                  'on fizz boards')
    return False

  usb_bus_ports = _get_port_numbers_from_vidpid(usb_vid, usb_pid)
  logging.debug('PowerCycleUSBPort: port numbers are %s', usb_bus_ports)
  port_ids = []
  for bus_idx, port_idx in usb_bus_ports:
    port_id = PortId(bus=bus_idx, port_number=port_idx)
    logging.debug('PowerCycleUSBPort: bus %s port %s GPIO %s', bus_idx,
                  port_idx, port_id)
    port_ids.append(port_id)

  if port_ids == []:
    logging.info('No port ids were found')
    return False
  else:
    logging.debug('Got port ids %s', port_ids)

  status = True
  for port_id in port_ids:
    logging.info('PowerCycleUSBPort: reset port id %s', port_id)
    gpio_index = _get_gpio_index(board, port_id)
    if not _cycle_gpio_power_fizz(gpio_index):
      logging.info('PowerCycleUSBPort: power cycle port_id %s failed', port_id)
      status = False
    else:
      logging.info('PowerCycleUSBPort: power cycle port_id %s success', port_id)
  logging.info('PowerCycleUSBPort returns %s', status)
  return status


#
# This is used while updating chameleond manually
#
if __name__ == '__main__':
  import sys
  if len(sys.argv) != 3:
    print 'invoke with python powertest.py <vid> <pid>'
  else:
    VID = sys.argv[1]
    PID = sys.argv[2]
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logging.info("Resetting %s %s", VID, PID)
    PowerCycleUSBPort(VID, PID)
