# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Audio utilities."""

class AudioDataFormat(object):
  """The class to represent audio data format.

  Properties:
    file_type: 'raw' or 'wav'.
    sample_format: 'S32_LE' for 32-bit signed integer in little-endian.
      Refer to aplay manpage for other formats.
    channel: channel number.
    rate: sampling rate.
  """
  def __init__(self, file_type, sample_format, channel, rate):
    """Initializes an AudioDataFormat object.

    Args:
      file_type: 'raw' or 'wav'.
      sample_format: 'S32_LE' for 32-bit signed integer in little-endian.
        Refer to aplay manpage for other formats.
      channel: channel number.
      rate: sampling rate.
    """
    self.file_type = file_type
    self.sample_format = sample_format
    self.channel = channel
    self.rate = rate

  def AsDict(self):
    """Returns data format in a dict.

    Returns:
      A dict containing file_type, sample_format, channel, rate.
    """
    return dict(
        file_type=self.file_type,
        sample_format=self.sample_format,
        channel=self.channel,
        rate=self.rate)
