# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""IDs shared with Chameleond drivers."""

# IDs of ports
DP1 = 1
DP2 = 2
HDMI = 3
VGA = 4
MIC = 5
LINEIN = 6
LINEOUT = 7
USB_AUDIO_IN = 8
USB_AUDIO_OUT = 9

# Input/output ports
INPUT_PORTS = [DP1, DP2, HDMI, VGA, MIC, LINEIN, USB_AUDIO_IN]
OUTPUT_PORTS = [LINEOUT, USB_AUDIO_OUT]

# Ports that support audio/video.
AUDIO_PORTS = [HDMI, MIC, LINEIN, LINEOUT, USB_AUDIO_IN, USB_AUDIO_OUT]
VIDEO_PORTS = [DP1, DP2, HDMI, VGA]

# Ports that support USB audio
USB_AUDIO_PORTS = [USB_AUDIO_IN, USB_AUDIO_OUT]

# Convenience methods
IsInputPort = lambda port_id: port_id in INPUT_PORTS
IsOutputPort = lambda port_id: port_id in OUTPUT_PORTS
IsAudioPort = lambda port_id: port_id in AUDIO_PORTS
IsVideoPort = lambda port_id: port_id in VIDEO_PORTS
IsUSBAudioPort = lambda port_id: port_id in USB_AUDIO_PORTS

# IDs of EDIDs
EDID_ID_DEFAULT = 0
EDID_ID_DISABLE = -1
