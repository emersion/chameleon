# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Standalone user interface (LCM display module) server."""

import xmlrpclib

from chameleond.utils.lcm_interface import LcmInterface
from chameleond.utils.lcm_queue import LcmEventQueue


class DisplayServer(object):
  """Standalone UI server with a proxy to chameleon server."""

  def __init__(self, chameleon_host='0.0.0.0', chameleon_port='9992'):
    """Initializes DisplayServer object.

    Args:
      chameleon_host: host address of chameleon server to link.
      chameleon_port: port number of chameleon server to link.
    """
    address = 'http://%s:%s' % (chameleon_host, chameleon_port)
    self._chameleon_client = xmlrpclib.ServerProxy(address, allow_none=True)

  def RunServer(self):
    """Runs display server for standalone user interface."""
    server = LcmInterface(self._chameleon_client, LcmEventQueue)
    server.Run()
