# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Library to set the correct path."""

import os, sys

top_dir = os.path.dirname(os.path.realpath(__file__.replace('.pyc', '.py')))
sys.path.append(top_dir)

chameleon_dir = os.path.dirname(top_dir)
sys.path.append(chameleon_dir)

# Overlay the private Chameleon repo.
# TODO(waihong): Remove video-chameleon when all switched to chameleon-private.
for repo_name in ('chameleon-private', 'video-chameleon'):
  chameleon_private_dir = os.path.join(os.path.dirname(chameleon_dir),
                                       repo_name)
  if os.path.exists(chameleon_private_dir):
    sys.path.append(chameleon_private_dir)
