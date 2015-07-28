# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""System tools required for Chameleond execution."""

import os
import subprocess
import threading


class _SystemTools(object):
  """A class to wrap the required tools for Chameleond execution."""

  _TOOL_PATHS = {
      'chameleond': '/etc/init.d/chameleond',
      'i2cdump': '/usr/local/sbin/i2cdump',
      'i2cget': '/usr/local/sbin/i2cget',
      'i2cset': '/usr/local/sbin/i2cset',
      'hpd_control': '/usr/bin/hpd_control',
      'memtool': '/usr/bin/memtool',
      'modprobe':'/sbin/modprobe',
      'reboot': '/sbin/reboot',
      'pixeldump': '/usr/bin/pixeldump',
  }

  def __init__(self):
    """Constructs a _SystemTools object."""
    self._CheckRequiredTools()

  def _CheckRequiredTools(self):
    """Checks all the required tools exist.

    Raises:
      SystemToolsError if missing a tool.
    """
    for path in self._TOOL_PATHS.itervalues():
      if not os.path.isfile(path):
        raise IOError('Required tool %s not existed' % path)

  def Call(self, name, *args):
    """Calls the tool with arguments.

    Args:
      name: The name of the tool.
      *args: The arguments of the tool.
    """
    command = [self._TOOL_PATHS[name]] + map(str, args)
    subprocess.check_call(command)

  def Output(self, name, *args):
    """Calls the tool with arguments and returns its output.

    Args:
      name: The name of the tool.
      *args: The arguments of the tool.

    Returns:
      The output message of the call, including stderr message.
    """
    command = [self._TOOL_PATHS[name]] + map(str, args)
    return subprocess.check_output(command, stderr=subprocess.STDOUT)

  def DelayedCall(self, time, name, *args):
    """Calls the tool with arguments after a given delay.

    The method returns first before the execution.

    Args:
      time: The time in second.
      name: The name of the tool.
      *args: The arguments of the tool.
    """
    threading.Timer(time, lambda: self.Call(name, *args)).start()


# Singleton
SystemTools = _SystemTools()
