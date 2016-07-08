# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Synchronization of time with the chameleon mirror server."""

import datetime

import chameleon_common #pylint: disable=W0611
from chameleond.utils import system_tools


class SyncTimeException(Exception):
  """A dummpy exception class for the sync_time module."""
  pass


class Datetime(object):
  """Get and set date time.

  This class provides a simple way to synchronize time on a chameleon board
  with the chameleon mirror server.

  This class is required because of the rather limited date/time utilities
  on a chameleon board.

  Google servers provide time in GMT, i.e., UTC.

  Note: this class does not take daylight saving time into consideration.
  Should support it later if higher clock precision is needed.

  """

  CHAMELEON_MIRROR_URL = (
      "http://commondatastorage.googleapis.com/chromeos-localmirror")

  MONTH = {'Jan': '01',
           'Feb': '02',
           'Mar': '03',
           'Apr': '04',
           'May': '05',
           'Jun': '06',
           'Jul': '07',
           'Aug': '08',
           'Sep': '09',
           'Oct': '10',
           'Nov': '11',
           'Dec': '12'}

  def get_timezone_offset(self):
    """Get the timezone offset with respect to UTC.

    Returns:
      a timedelta object representing the timezone offset.

    Raises:
      SyncTimeException if there is an error in executing the date command.
    """
    command = 'date +%z'.split()
    # an offset looks like '+0800' or '-0700'
    try:
      offset = system_tools.SystemTools.Output(*command).strip()
    except Exception as e:
      raise SyncTimeException('Failed to get timezone offset: %s.', e)
    sign = -1 if offset[0] == '-' else 1
    offset_hrs = sign * int(offset[1:3])
    offset_mins = sign * int(offset[3:5])
    return datetime.timedelta(hours=offset_hrs, minutes=offset_mins)

  def chameleon_mirror_server_time(self):
    """Get current time from the chameleon mirror server.

    Current time queried from CHAMELEON_MIRROR_URL looks like
      Date: Thu, 07 Jul 2016 07:54:42 GMT

    Returns:
      the datetime object representing current time like
      datetime.datetime(2016, 7, 1, 15, 20, 50)

    Raises:
      SyncTimeException if there is an error in getting the server time.
    """
    command = ('wget -S %s' % self.CHAMELEON_MIRROR_URL).split()
    for line in system_tools.SystemTools.Output(*command).splitlines():
      if 'Date' in line:
        _, _, day, month, year, hrs_mins_secs, _ = line.split()
        month = self.MONTH.get(month, '')
        if month:
          hrs, mins, secs = hrs_mins_secs.split(':')
          return datetime.datetime(int(year), int(month), int(day),
                                   int(hrs), int(mins), int(secs))
    raise SyncTimeException('Failed to get chameleon mirror server time.')

  def get_time(self):
    """Get current time.

    Returns:
      the current time string in the timezone which the chameleon is currently
      using. The time format looks like '2016-07-01 15:20:50'
    """
    curr_time = self.chameleon_mirror_server_time() + self.get_timezone_offset()
    return curr_time.strftime('%Y-%m-%d %H:%M:%S')


if __name__ == '__main__':
  # Print the chameleon mirror server time when running as a script.
  print Datetime().get_time()
