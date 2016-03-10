# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Caching server, providing access to the cached thumbnail images."""

import logging
import multiprocessing
import os

import SimpleHTTPServer
import SocketServer


# Directory for storing the cached images.
CACHED_DIR = '/tmp/cached'


def ClearCachedDir():
  """Removes all files in the cached directory."""
  if os.path.exists(CACHED_DIR):
    for file_name in os.listdir(CACHED_DIR):
      file_path = os.path.join(CACHED_DIR, file_name)
      if os.path.isfile(file_path):
        os.unlink(file_path)
  else:
    os.makedirs(CACHED_DIR)


class RemoveFileOnceGetHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
  """A HTTP request handler which removes the file once get."""

  def do_GET(self):
    """Responses the GET request."""
    SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
    os.remove(self.path[1:])


class CachingServer(multiprocessing.Process):
  """A caching server which starts in a new process"""

  def __init__(self, port):
    super(CachingServer, self).__init__()
    ClearCachedDir()
    os.chdir(CACHED_DIR)
    logging.info('Creating caching server on port %d...', port)
    self.httpd = SocketServer.TCPServer(('', port), RemoveFileOnceGetHandler)

  def run(self):
    try:
      logging.info('Caching server serves forever...')
      self.httpd.serve_forever()
    finally:
      logging.info('Close the server.')
      self.httpd.server_close()
