#!/usr/bin/env python
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Network utilities."""

import logging
import re
import subprocess


def HasIp():
  """Checks if system has IP on eth0.

  Returns:
    True if system has IP, false otherwise.
  """
  ip_output = subprocess.check_output(['ip', 'addr', 'show', 'dev', 'eth0'])

  # Pattern is like " inet 100.102.7.163/25 scope global eth0"
  match = re.search(r'^\s+inet ([.0-9]+)/[0-9]+', ip_output, re.MULTILINE)
  if match:
    ip_address = match.group(1)
    logging.debug('Get IP %s', ip_address)
    return True
  else:
    logging.warning('Can not get IP. Should restart networking.')
    return False


def RestartNetwork():
  """Restarts networking daemon."""
  logging.warning('Restart networking.')
  try:
    subprocess.check_output(['/etc/init.d/networking', 'restart'])
    if HasIp():
      logging.info('Network is back')
  except subprocess.CalledProcessError as e:
    # This is expected in some network environment.
    logging.warning(e.output)
    if 'No lease, failing' in e.output:
      logging.warning('Can not get network, maybe try again later.')
    else:
      raise


def PossiblyRestartNetwork():
  """Checks network status and possibly restarts networking daemon."""
  if not HasIp():
    RestartNetwork()
