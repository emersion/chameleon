# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Library to set the correct path."""

import os, sys

top_dir = os.path.dirname(os.path.realpath(__file__.replace('.pyc', '.py')))
chameleon_dir = os.path.dirname(top_dir)
sys.path.append(chameleon_dir)
