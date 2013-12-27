#!/usr/bin/env python
# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Chameleon Daemon."""

import argparse
import logging
import shlex
from SimpleXMLRPCServer import SimpleXMLRPCServer


class Chameleond(object):
  """A class to start a Chameleon daemon."""

  def __init__(self, driver='pygprobe', *args, **kwargs):
    """Initializes Chameleond object.

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
    module_name = name + '_driver'
    logging.info('Load module %s...', module_name)
    package = __import__('drivers', fromlist=[module_name])
    module = getattr(package, module_name)
    class_name = ''.join([s.capitalize() for s in module_name.split('_')])
    return getattr(module, class_name)

  def RunServer(self, port=9992):
    """Runs Chameleond server.

    Args:
      port: port number of RPC server.
    """
    # Launch the XMLRPC server to serve Chameleond APIs.
    server = SimpleXMLRPCServer(('localhost', port), allow_none=True,
                                logRequests=True)
    server.register_introspection_functions()
    server.register_instance(self._driver)
    logging.info('Listening on localhost port %d...', port)
    server.serve_forever()


def main():
  """The Main program, to run Chameleon Daemon."""
  parser = argparse.ArgumentParser(
      description='Launch a Chameleon daemon.',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--driver', type=str, dest='driver', default='pygprobe',
                      help='driver of Chameleond')
  parser.add_argument('--port', type=int, dest='port', default=9992,
                      help='port number of RPC server')
  parser.add_argument('-v', '--verbose', action='count', dest='verbose',
                      help='increase message verbosity')
  parser.add_argument("driver_args", nargs=argparse.REMAINDER,
                      help='arguments passed to the driver')

  options = parser.parse_args()
  tokens = shlex.split(' '.join(options.driver_args))
  args = [t for t in tokens if '=' not in t]
  kwargs = dict(t.split('=') for t in tokens if '=' in t)

  verbosity_map = {0: logging.INFO, 1: logging.DEBUG}
  verbosity = verbosity_map.get(options.verbose or 0, logging.NOTSET)
  log_format = '%(asctime)s %(levelname)s '
  if options.verbose > 0:
    log_format += '(%(filename)s:%(lineno)d) '
  log_format += '%(message)s'
  logging.basicConfig(level=verbosity, format=log_format)

  Chameleond(options.driver, *args, **kwargs).RunServer(options.port)


if __name__ == '__main__':
  main()
