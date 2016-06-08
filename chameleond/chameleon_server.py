# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleon Server."""

import logging
import signal
import sys

from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler

import chameleon_common  # pylint: disable=W0611
from chameleond.utils.caching_server import CachingServer


class ChameleonXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
  """XMLRPC request handler for Chameleon server.

  During the response of SimpleXMLRPCRequestHandler, it will try to obtain
  client's domain name for logging. When there is no DNS server in the
  network, this step will take a long time and delay the returning of calls
  from server proxy. We override address_string method to bypass requesting
  domain name.
  """
  def address_string(self):
    """Returns the client address formatted for logging.

    This method is overridden to bypass requesting domain name.

    Returns:
      The formatted string for client address.
    """
    host = self.client_address[0]
    # original: return socket.getfqdn(host)
    return '%s (no getfqdn)' % host


class ChameleonServer(object):
  """Chameleon Server, which starts a RPC service."""

  def __init__(self, driver, *args, **kwargs):
    """Initializes ChameleonServer object.

    Args:
      driver: String of the driver to serve the RPC server.
    """
    # TODO(waihong): Probe all drivers and find a suitable one.
    self._driver = self._LoadDriver(driver)(*args, **kwargs)

  def _LoadDriver(self, name):
    """Load the driver from the driver directory.

    Args:
      name: String of the driver name.

    Returns:
      The class of the driver.
    """
    module_name = name
    logging.info('Load module %s...', module_name)
    package = __import__('chameleond.drivers', fromlist=[module_name])
    module = getattr(package, module_name)
    return getattr(module, 'ChameleondDriver')

  def RunServer(self, host='0.0.0.0', port=9992):
    """Runs Chameleon RPC server.

    Args:
      host: host address to serve the service.
      port: port number of RPC server.
    """
    caching = CachingServer(port + 1)
    server = SimpleXMLRPCServer((host, port), allow_none=True,
                                requestHandler=ChameleonXMLRPCRequestHandler,
                                logRequests=True)
    server.register_introspection_functions()
    server.register_instance(self._driver)

    signal_handler = lambda signum, frame: sys.exit(0)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
      # Launch the caching server on the next port, serving cached files.
      logging.info('Start the caching server process.')
      caching.start()

      # Launch the XMLRPC server to serve Chameleond APIs.
      logging.info('Listening on %s port %d...', host, port)
      server.serve_forever()
    finally:
      logging.info('Terminate the caching server process.')
      caching.terminate()
