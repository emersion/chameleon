#!/usr/bin/env python
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Connect to Chameleond and capture screenshot."""

import argparse
import subprocess
import tempfile
import time
import xmlrpclib


def main():
  """The Main program, capture screenshot."""
  parser = argparse.ArgumentParser(
      description='Connect to Chameleond and capture screenshot.',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--chameleon_host', type=str, dest='host',
                      default='localhost', help='host address of Chameleond')
  parser.add_argument('--port', type=int, dest='port', default=9992,
                      help='port number of Chameleond')
  parser.add_argument('--replug', dest='replug', action='store_true',
                      help='unplug and plug before capturing screen')
  parser.add_argument('--output', type=str, dest='output', default='image.png',
                      help='output file name of screenshot')

  options = parser.parse_args()
  chameleon = xmlrpclib.ServerProxy(
      'http://%s:%d' % (options.host, options.port))
  inputs = chameleon.ProbeInputs()
  main_input = inputs[0]
  print 'Use the main port:', chameleon.GetInputName(main_input)
  if options.replug:
    print 'Replugging...'
    chameleon.FireHpdPulse(main_input, 1000000)
    time.sleep(1)
  width, height = chameleon.DetectResolution(main_input)
  print 'Detected screen size %dx%d' % (width, height)
  print 'Capturing the screen...'
  pixels = chameleon.DumpPixels(main_input).data
  print 'Got pixel size %d' % len(pixels)
  with tempfile.NamedTemporaryFile(suffix='.bgra') as f:
    f.write(pixels)
    f.flush()
    subprocess.check_call(['convert', '-size', '%dx%d' % (width, height),
        '-depth', '8', '-alpha', 'off', f.name, options.output])
    print 'Outputted to file:', options.output


if __name__ == '__main__':
  main()
