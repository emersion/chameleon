# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Setup script to distribute and install Chameleond library and scripts."""

from distutils.core import setup

setup(
  name = 'chameleond',
  version = '0.0.2',
  packages = ['chameleond', 'chameleond.drivers', 'chameleond.utils'],
  package_data = {'chameleond': ['data/*.bin']},
  url = 'http://www.chromium.org',
  maintainer = 'chromium os',
  maintainer_email = 'chromium-os-dev@chromium.org',
  license = 'Chromium',
  description = 'Server to communicate and control Chameleon board.',
  long_description = 'Server to communicate and control Chameleon board.',
  scripts = ['utils/run_chameleond']
)
