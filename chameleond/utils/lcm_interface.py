# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""The interface finite state machine class for Chameleon standalone UI.

Brief instructions of each states:
START state:
    The initial state of showing boot screen.
    - Press up/down/left/right key to go to the MENU state.
MENU state:
    the state when use is walking around the menu tree.
    - Press up: go to the last item (cursor will move on display UI).
    - Press down: go to the next item (cursor will move on display UI).
    - Press right: enter current item, if this item has sub-items, show them on
                   display UI; if this item is a leaf node, execute the
                   function and go to PAGE state.
    - Press left: go back to the upper level of menu tree.
PAGE state:
    the state of showing information after executing function items.
    - Press up: scroll up the content.
    - Press down: scroll down the content.
    - Press right: (do nothing)
    - Press left: leave the page and go back to MENU state.
"""

from collections import OrderedDict
import logging
import math
import Queue

import chameleon_common  # pylint: disable=W0611
from chameleond.utils import gpio
from chameleond.utils import lcm_display
from chameleond.utils import lcm_font
from chameleond.utils import lcm_funcpool as FuncPool


# Create function callers for menu leaf nodes by function name and list of
# arguments (except chameleond).
# While usage, pass chameleond_proxy as an argument to the caller.
_BindToArgs = lambda func, args: (lambda chameleond: func(chameleond, *args))

# Use hierarchical OrderedDict to form the menu tree. Each tuple stands for a
# node: (node name, child), child=function caller for leaf node.
_MENU = OrderedDict([
    ('Video', OrderedDict([
        ('DP1', OrderedDict([
            ('Status', _BindToArgs(FuncPool.GetPortStatus, [1])),
            ('Plug', _BindToArgs(FuncPool.PlugPort, [1])),
            ('Unplug', _BindToArgs(FuncPool.UnplugPort, [1])),
            ('Edid', _BindToArgs(FuncPool.ApplyEdid, [1, 0]))])),
        ('DP2', OrderedDict([
            ('Status', _BindToArgs(FuncPool.GetPortStatus, [2])),
            ('Plug', _BindToArgs(FuncPool.PlugPort, [2])),
            ('Unplug', _BindToArgs(FuncPool.UnplugPort, [2])),
            ('Edid', _BindToArgs(FuncPool.ApplyEdid, [2, 0]))])),
        ('HDMI', OrderedDict([
            ('Status', _BindToArgs(FuncPool.GetPortStatus, [3])),
            ('Plug', _BindToArgs(FuncPool.PlugPort, [3])),
            ('Unplug', _BindToArgs(FuncPool.UnplugPort, [3])),
            ('Edid', _BindToArgs(FuncPool.ApplyEdid, [3, 0]))])),
        ('VGA', OrderedDict([
            ('Status', _BindToArgs(FuncPool.GetPortStatus, [4])),
            ('Plug', _BindToArgs(FuncPool.PlugPort, [4])),
            ('Unplug', _BindToArgs(FuncPool.UnplugPort, [4]))]))])),
    ('Audio', _BindToArgs(FuncPool.AudioMethod, [])),
    ('Chameleon', OrderedDict([
        ('IP/MAC Address', _BindToArgs(FuncPool.GetIpAndMacAddress, [])),
        ('Cham. Status', _BindToArgs(FuncPool.GetChameleondStatus, [])),
        ('Cham. Restart', _BindToArgs(FuncPool.RestartChameleond, []))]))
    ])


class LcmInterface(object):
  """The interface menu class of LCM display."""

  # Enumeration index of key direction events.
  _KEY_EVENT_UP = 1
  _KEY_EVENT_DOWN = 2
  _KEY_EVENT_RIGHT = 3
  _KEY_EVENT_LEFT = 4

  # Parameters for keys.
  # key_direction: (key_event_index, gpio_port)
  _KEY_PARAMS = {'up': (_KEY_EVENT_UP, 450),
                 'down': (_KEY_EVENT_DOWN, 449),
                 'right': (_KEY_EVENT_RIGHT, 448),
                 'left': (_KEY_EVENT_LEFT, 451)}

  # Parameters for leds.
  # led_name: gpio_port
  _LED_PARAMS = {'led0': 478,
                 'led1': 479,
                 'led2': 480,
                 'led3': 481}

  # Finite state machine state names.
  _STATE_START = 'start'
  _STATE_MENU = 'menu'
  _STATE_PAGE = 'page'

  def __init__(self, chameleond_proxy, event_queue):
    """Constructs a LcmInterface object.

    Args:
      chameleond_proxy: The ServerProxy object linked to chameleond.
      event_queue: The Queue object for consuming event.
    """
    self._chameleond = chameleond_proxy
    self._queue = event_queue
    self._state = self._STATE_START

    # Attributes to record current state in menu.
    self._cursor = [0]  # the hierarchical position in the menu tree.
    self._menu = _MENU  # the current sub-tree of menu.
    # For example, in this menu tree:
    # A0 ---> B0 ---> C0
    #    ---> B1 ---> D0 ---> E0
    #                    ---> E1
    #            ---> D1
    # A1 ---> F0
    #    ---> F1 ---> G0
    #            ---> G1
    # To indicate the position D0 (root->A0->B1->D0):
    #     self._cursor = [0, 1, 0]
    #     self._menu = The sub-tree which root is B1 (the parent of D0)
    # (The reason we store self._menu is to simply acquire all siblings of
    #  current position, ex. D0 -> D0, D1, since on UI we need to display them
    #  all and user can press up/down to walk through.)

    # Attributes to record page information.
    self._page_contents = None  # the contents needed to be shown on page.
    self._page_index = 0  # the current start line number to be shown on LCM.

    self._keys = {}
    self._leds = {}
    self._InitiatePeripherals()
    self._display = lcm_display.LcmDisplay()

    self._display_lines = self._display.GetMaxCharLines()
    self._page_scroll_lines = self._display_lines - 2

  def _InitiatePeripherals(self):
    """Initiate key and LED drivers."""
    for key in self._KEY_PARAMS.keys():
      self._keys[key] = gpio.Key(
          self._KEY_PARAMS[key][1], key, self._KEY_PARAMS[key][0], self._queue)
    for led in self._LED_PARAMS.keys():
      self._leds[led] = gpio.Led(self._LED_PARAMS[led])

  def Run(self):
    """Runs finite state machine of LCM display UI.

    This is the consuming loop of event queue to get and process events. Then
    execute the correspondent function through chameleond proxy and update UI
    on the LCM display.
    """
    while True:
      try:
        # Queue is keyboard interruptible only if timeout is set.
        lcm_event = self._queue.get(timeout=1000)
      except Queue.Empty:
        continue
      logging.info('LcmInterface gets event: %s', lcm_event.notice)
      key_index = lcm_event.GetKeyIndex()
      if self._state == self._STATE_START:
        self._MenuRender()
        self._state = self._STATE_MENU
      elif self._state == self._STATE_MENU:
        if key_index == self._KEY_EVENT_UP:
          self._MenuCursorUp()
        elif key_index == self._KEY_EVENT_DOWN:
          self._MenuCursorDown()
        elif key_index == self._KEY_EVENT_RIGHT:
          self._MenuCursorEnter()
        elif key_index == self._KEY_EVENT_LEFT:
          self._MenuCursorBack()
      elif self._state == self._STATE_PAGE:
        if key_index == self._KEY_EVENT_UP:
          self._PageCursorUp()
        elif key_index == self._KEY_EVENT_DOWN:
          self._PageCursorDown()
        elif key_index == self._KEY_EVENT_RIGHT:
          self._PageCursorEnter()
        elif key_index == self._KEY_EVENT_LEFT:
          self._PageCursorBack()
      self._display.RefreshDisplay()
      self._queue.task_done()

  def _MenuCursorUp(self):
    """Handles key up event in menu state."""
    if self._cursor[-1] == 0:
      return
    self._cursor[-1] -= 1
    self._MenuRender()

  def _MenuCursorDown(self):
    """Handles key down event in menu state."""
    if self._cursor[-1] == len(self._menu) - 1:
      return
    self._cursor[-1] += 1
    self._MenuRender()

  def _MenuCursorEnter(self):
    """Handles key right (enter) event in menu state."""
    if self._MenuIsLeafNode():
      # Go to page state.
      self._EnterPage()
      self._state = self._STATE_PAGE
    else:
      self._menu = self._menu.values()[self._cursor[-1]]
      self._cursor.append(0)
      self._MenuRender()

  def _MenuCursorBack(self):
    """Handles key left (back) event in menu state."""
    if len(self._cursor) == 1:
      return
    self._cursor.pop()
    self._MenuGetNode()
    self._MenuRender()

  def _MenuGetNode(self):
    """Gets current sub-tree of menu tree."""
    menu_walk = _MENU
    for depth in xrange(len(self._cursor) - 1):
      menu_walk = menu_walk.values()[self._cursor[depth]]
    self._menu = menu_walk

  def _MenuIsLeafNode(self, item=None):
    """Checks whether is leaf node of menu tree.

    Args:
      item: The cursor index of current item; if not given, use which stores in
          self._cursor as input.

    Returns:
      True if current item is leaf node; otherwise False.
    """
    if item is None:
      item = self._cursor[-1]
    return not isinstance(self._menu.values()[item], OrderedDict)

  def _MenuRender(self):
    """Renders the display image of LCM UI in menu state.

    Because there are only a few lines can be shown on LCM once, we need to
    find the suitable window of current position to show the content of menu.
    """
    self._display.CanvasClear()
    window_head = self._cursor[-1] / self._display_lines * self._display_lines
    # Prints the menu items inside the window.
    for line in xrange(self._display_lines):
      menu_line = window_head + line
      if menu_line >= len(self._menu):
        break
      self._display.CanvasPrintMenuItem(
          self._menu.keys()[menu_line], self._MenuIsLeafNode(menu_line), line)
    # Prints the moving cursor.
    self._display.CanvasPrintCursor(self._cursor[-1] - window_head, 0)

  def _PageCursorUp(self):
    """Handles key up event in page state."""
    if self._page_index == 0:
      return
    self._page_index -= self._page_scroll_lines
    self._PageRender()

  def _PageCursorDown(self):
    """Handles key down event in page state."""
    if (len(self._page_contents) <= self._display_lines - 1 or
        self._page_index >= len(self._page_contents) - 2):
      return
    self._page_index += self._page_scroll_lines
    self._PageRender()

  def _PageCursorEnter(self):
    """Handles key right (enter) event in page state."""
    return  # do nothing.

  def _PageCursorBack(self):
    """Handles key left (back) event in page state."""
    # Go back to menu state.
    self._MenuRender()
    self._state = self._STATE_MENU

  def _PageRender(self):
    """Renders the display image of LCM UI in page state.

    Because there are only a few lines can be shown on LCM once, we need to
    find the suitable window of current position to show the content of page.

    Page layout (assume LCM total display lines = 4, each line is 16-char long):

                0---------------15
        Line#0: Hello! This is th
        Line#1: e example of LCM
        Line#2: UI display. It is
        Line#3: <Exit    vMove    (highlighted)

    The last line is the prompt line to indicate the key functions. When we
    scroll up/down to browse the content, to gain readability we only scroll
    4-2=2 lines to keep one line is still showing. For example (scroll down):

                0---------------15
        Line#0: UI display. It is (this line is repeated)
        Line#1: amazing, isn't it
        Line#2: ?
        Line#3: <Exit   ^ Move    (highlighted)
    """
    self._display.CanvasClear()
    # Print the content lines.
    for line in xrange(self._display_lines - 1):
      current_line = self._page_index + line
      if current_line < len(self._page_contents):
        self._display.CanvasPrintLine(self._page_contents[current_line], line)

    # Print the prompt line (last line)
    prompt_exit = lcm_font.ARROW_LEFT + 'Exit   '
    if len(self._page_contents) <= self._display_lines - 1:
      prompt_scroll = '        '
    elif self._page_index == 0:
      prompt_scroll = ' ' + lcm_font.ARROW_DOWN + 'Move  '
    elif self._page_index >= len(self._page_contents) - 2:
      prompt_scroll = lcm_font.ARROW_UP + ' Move  '
    else:
      prompt_scroll = lcm_font.ARROW_UP + lcm_font.ARROW_DOWN + 'Move  '
    self._display.CanvasPrintLine(prompt_exit + prompt_scroll,
                                  self._display_lines - 1,
                                  highlight=True)

  def _EnterPage(self):
    """Enters the page state from the menu state."""
    logging.info('Entering page: cursor = %s', str(self._cursor))
    self._page_index = 0
    self._page_contents = ['Please wait...']
    self._PageRender()
    self._ExecuteFunction()  # execute correspondent function of the item.
    self._PageRender()

  def _ExecuteFunction(self):
    """Executes correspondent function of current menu item.

    All functions are defined in lcm_funcpool.py.
    """
    func_caller = self._menu.values()[self._cursor[-1]]
    output = func_caller(self._chameleond)
    logging.info('Display output: %s', output)

    def _SplitContent(content):
      """Splits input string into page content format.

      Args:
        content: Input string.

      Returns:
        An array of splitted string content, each piece has the same length of
        display.
      """
      piece_length = self._display.GetMaxCharLength()
      contents = content.splitlines()  # handles new line char.
      pieces = []
      for c in contents:
        total_pieces = int(math.ceil(float(len(c)) / piece_length))
        pieces += [c[i * piece_length:(i + 1) * piece_length] for i in xrange(
            total_pieces - 1)]
        pieces.append(c[(total_pieces - 1) * piece_length:])
      return pieces
    self._page_contents = _SplitContent(output)
