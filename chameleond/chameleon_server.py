# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleon Server."""

import logging
from SimpleXMLRPCServer import SimpleXMLRPCServer


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
    # Launch the XMLRPC server to serve Chameleond APIs.
    server = SimpleXMLRPCServer((host, port), allow_none=True,
                                logRequests=True)
    server.register_introspection_functions()
    server.register_instance(self._driver)
    logging.info('Listening on %s port %d...', host, port)
    server.serve_forever()
