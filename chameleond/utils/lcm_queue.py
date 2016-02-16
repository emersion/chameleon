# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The Queue object of key-press events and chameleon events to display UI."""

from Queue import Queue
import threading

# Global queue object for LCM UI finite state machine.
LcmEventQueue = Queue()


class LcmEventError(Exception):
  """Exception raise when any unexpected behavior happened on LcmEvent."""
  pass


class LcmEvent(object):
  """A event class of LcmEventQueue for LcmFsm processing."""
  def __init__(self, notice, key_index=None):
    """Constructs a LcmEvent object.

    Args:
      notice: The string of notice.
      key_index: The index of pressed key event. None if this event is not a
          key-press event.
    """
    self.notice = notice
    self._key_index = key_index
    self._event = threading.Event()

  def Clear(self):
    """Resets the internal flag to false of event."""
    self._event.clear()

  def Set(self):
    """Sets the internal flag to true of event."""
    self._event.set()

  def Wait(self):
    """Waits until the internal flag of event is true."""
    self._event.wait()

  def IsKeyPressed(self):
    """Checks whether this is key-press event.

    Reutrns:
      True if this is key-press event; otherwise False.
    """
    return bool(self._key_index)

  def GetKeyIndex(self):
    """Gets key index and Sets the event internal flag to true."""
    if not self.IsKeyPressed():
      raise LcmEventError('GetKeyIndex() error, this is not key event!!')
    self.Set()
    return self._key_index
