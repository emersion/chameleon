# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The pool of LCM interface supported Chameleon functions."""

import fcntl
import functools
import logging
import socket
import struct
import xmlrpclib

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import system_tools


def _LcmMethod(func):
  """Decorator for calling LCM menu leaf functions.

  Catches all exceptions to keep daemon going and prints error message to
  display.
  """
  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    try:
      output = func(*args, **kwargs)
      # Also show message for non-return functions.
      if output is None:
        return 'Success!!'
      return output
    except xmlrpclib.Fault as e:
      # Print message when XML-RPC fault occurs.
      return 'Func failed!!\n%s' % e.faultString
    except xmlrpclib.ProtocolError as e:
      # Print message when protocol error occurs.
      return 'Not responded!!\n%s' % e.errmsg
    except Exception as e:
      # Print message for any else exceptions.
      return 'Error!! %s:\n%s' % (type(e).__name__, e.message)
  return wrapper


@_LcmMethod
def GetPortStatus(chameleond, port_id):
  """Gets port status with port_id through chameleond proxy."""
  if not chameleond.IsPhysicalPlugged(port_id):
    return 'Not connected\n'
  if chameleond.IsPlugged(port_id):
    return 'Connected\nPlugged\n'
  return 'Connected\nNot plugged\n'


@_LcmMethod
def PlugPort(chameleond, port_id):
  """Plugs port with port_id through chameleond proxy."""
  logging.info('Call Plug #%d', port_id)
  if not chameleond.IsPhysicalPlugged(port_id):
    return 'Cannot plug since it is not connected.'
  return chameleond.Plug(port_id)


@_LcmMethod
def UnplugPort(chameleond, port_id):
  """Unplugs port with port_id through chameleond proxy."""
  logging.info('Call Unplug #%d', port_id)
  return chameleond.Unplug(port_id)


@_LcmMethod
def ApplyEdid(chameleond, port_id, edid_id):  # pylint: disable=W0613
  """Applies edid to port with port_id through chameleond proxy."""
  raise NotImplementedError


@_LcmMethod
def AudioMethod(chameleond):  # pylint: disable=W0613
  raise NotImplementedError


@_LcmMethod
def GetIpAndMacAddress(chameleond, ifname='eth0'):  # pylint: disable=W0613
  """Gets Chameleon IP address and MAC address."""
  logging.info('Get IP address for eth0')
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  ip_addr = socket.inet_ntoa(fcntl.ioctl(
      s.fileno(),
      0x8915,
      struct.pack('256s', ifname[:15]))[20:24])
  mac_addr_info = fcntl.ioctl(s.fileno(),
                              0x8927,
                              struct.pack('256s', ifname[:15]))
  mac_addr = ':'.join(['%02x' % ord(char) for char in mac_addr_info[18:24]])
  return '\n'.join([ip_addr, mac_addr])


@_LcmMethod
def GetChameleondStatus(chameleond):  # pylint: disable=W0613
  """Gets chameleond status."""
  logging.info('Call SystemTools to get Chameleond status')
  return system_tools.SystemTools.Output('chameleond', 'status')


@_LcmMethod
def RestartChameleond(chameleond):  # pylint: disable=W0613
  """Restarts chameleond."""
  logging.info('Call SystemTools to restart Chameleond')
  return system_tools.SystemTools.Call('chameleond', 'restart')
