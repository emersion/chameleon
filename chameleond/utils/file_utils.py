#!/usr/bin/env python
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""File utilities."""

def TruncateToZero(path):
  """Truncates a file size to 0.

  Args:
    path: Path to the file.
  """
  with open(path, 'w'):
    pass
