# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Setup script to distribute and install Chameleond library and scripts."""

# Needs to import setup from setuptools instead of distutils.core
# in order to use the install_requires argument.
from setuptools import setup

setup(
    name='chameleond',
    version='0.0.2',
    packages=['chameleond', 'chameleond.devices', 'chameleond.drivers',
              'chameleond.utils'],
    package_data={'chameleond': ['data/*.bin', 'data/*.bitmap']},
    url='http://www.chromium.org',
    maintainer='chromium os',
    maintainer_email='chromium-os-dev@chromium.org',
    license='Chromium',
    description='Server to communicate and control Chameleon board.',
    long_description='Server to communicate and control Chameleon board.',
    # Uses pyserial version 2.7. The newer 3.x version is not compatible
    # with chameleond/utils/serial_utils.py
    install_requires=['pyserial==2.7', 'schedule'],
    scripts=['utils/run_chameleond', 'utils/run_displayd',
             'utils/run_stream_server', 'chameleond/utils/server_time',
             'utils/run_scheduler']
)
