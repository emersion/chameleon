# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""IDs shared with Chameleond drivers."""

DP1 = 1
DP2 = 2
HDMI = 3
VGA = 4
MIC = 5
LINEIN = 6
LINEOUT = 7

# Input/output ports
INPUT_PORTS = [DP1, DP2, HDMI, VGA, MIC, LINEIN]
OUTPUT_PORTS = [LINEOUT]

# Ports that support audio/video.
AUDIO_PORTS = [HDMI, MIC, LINEIN, LINEOUT]
VIDEO_PORTS = [DP1, DP2, HDMI, VGA]

# Convenience methods
IsInputPort = lambda port_id: port_id in INPUT_PORTS
IsOutputPort = lambda port_id: port_id in OUTPUT_PORTS
IsAudioPort = lambda port_id: port_id in AUDIO_PORTS
IsVideoPort = lambda port_id: port_id in VIDEO_PORTS
