#!/usr/bin/env python2
# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""A simple utility to connect to Chameleond in an interactive shell."""

import argparse
import code
import logging
import os
import readline
import rlcompleter
import subprocess
import time
import xmlrpclib

from audio.audio_value_detector import AudioValueDetector


def ShowMessages(proxy):
  """Shows the messages for usage.

  Args:
    proxy: The xmlrpclib.ServerProxy to chameleond.
  """
  logging.info('In interactive shell, p is the proxy to chameleond server')
  supported_ports = proxy.GetSupportedPorts()
  linein_port = None
  hdmi_port = None
  port_messages = []
  for port in supported_ports:
    port_type = proxy.GetConnectorType(port)
    if port_type == 'LineIn':
      linein_port = port
    if port_type == 'HDMI':
      hdmi_port = port
    port_messages.append('Port %d is %s.' % (port, port_type))
  message = '''
      %s
      E.g.''' % '\n      '.join(port_messages)
  if linein_port:
    message += '''
      p.StartCapturingAudio(%d) to capture from LineIn.
      p.StopCapturingAudio(%d) to stop capturing from LineIn.''' % (
          linein_port, linein_port)

  if hdmi_port:
    message += '''
      p.Plug(%d) to plug HDMI.
      p.Unplug(%d) to unplug HDMI.''' % (hdmi_port, hdmi_port)

  logging.info(message)


def DetectAudioValue0(channels=None, margin=0.01, continuous_samples=5,
                      duration=3600, dump_samples=48000):
  """Detects if Chameleon captures continuous audio data close to 0.

  This function will get the audio streaming data from stream server and will
  check if the audio data is close to 0 by the margin parameter.
  -margin < value < margin will be considered to be close to 0.
  If there are continuous audio samples close to 0 in the streamed data,
  test_server will log it and save the audio data to a wav file.

  E.g.
  >>> ConnectCrosToLineIn()
  >>> p.StartCapturingAudio(6, False)
  >>> DetectAudioValue0(duration=24*3600, margin=0.001)

  Args:
    channels: Array of audio channels we want to check.
        E.g. [0, 1] means we only care about channel 0 and channel 1.
    margin: Used to decide if the value is closed to 0. Maximum value is 1.
    continuous_samples: When continuous_samples samples are closed to 0, trigger
        event.
    duration: The duration of monitoring in seconds.
    dump_samples: When event happens, how many audio samples we want to
        save to file.
  """
  if not channels:
    channels = [0, 1]
  detecter = AudioValueDetector(options.host)  # pylint: disable=undefined-variable
  detecter.Detect(channels, margin, continuous_samples, duration, dump_samples)
  return True


def StartInteractiveShell(p, options):  # pylint: disable=unused-argument
  """Starts an interactive shell.

  Args:
    p: The xmlrpclib.ServerProxy to chameleond.
    options: The namespace from argparse.
  """
  vars = globals()  # pylint: disable=redefined-builtin
  vars.update(locals())
  readline.set_completer(rlcompleter.Completer(vars).complete)
  readline.parse_and_bind("tab: complete")
  shell = code.InteractiveConsole(vars)
  shell.interact()


def ParseArgs():
  """Parses the arguments.

  Returns:
    the namespace containing parsed arguments.
  """
  parser = argparse.ArgumentParser(
      description='Connect to Chameleond and use interactive shell.',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--chameleon_host', type=str, dest='host', required=True,
                      help='host address of Chameleond')
  parser.add_argument('--port', type=int, dest='port', default=9992,
                      help='port number of Chameleond')
  return parser.parse_args()


def GetAndConvertRecordedFile(remote_path):
  """Gets recorded file and converts it into a wav file.

  A helper function to get recorded file from Chameleon host and do
  file format conversion from 32 bit, 48000 rate, 8 channel raw file
  to 2 channel wav file.

  E.g.
  >>> p.StartCapturingAudio(6)
  >>> s = p.StopCapturingAudio(6)
  >>> GetAndConvertRecordedFile(s[0])

  The recorded raw file and converted wav file will be in current
  directory.

  Args:
    remote_path: The file to copy from Chameleon host.
  """
  basename = os.path.basename(remote_path)
  # options is already in the namespace.
  subprocess.check_call(
      ['scp', 'root@%s:%s' % (options.host, remote_path), basename])  # pylint: disable=undefined-variable
  subprocess.check_call(
      ['sox', '-b', '32', '-r', '48000', '-c', '8', '-e', 'signed',
       basename, '-c', '2', basename + '.wav'])


def ConnectCrosToLineIn():
  """Connects a audio bus path from Cros headphone to Chameleon LineIn."""
  p.AudioBoardConnect(1, 'Cros device headphone') # pylint: disable=undefined-variable
  p.AudioBoardConnect(1, 'Chameleon FPGA line-in') # pylint: disable=undefined-variable


def TestMotors():
  """Test motors by touching and releasing each button once."""
  for func in ['Call', 'Hang Up', 'Mute', 'Vol Up', 'Vol Down']:
    PressOneFunc(func)


def PressOneFunc(func, time_sec=0):
  """Test motors by touching and releasing one button.

  Args:
    func: The motor function. One of 'Call', 'Hang Up', 'Mute', 'Vol Up',
          'Vol Down'.
    time_sec: Hold time in seconds after touch and before release.
  """
  logging.info('Testing %s button, press and hold for %f seconds',
               func, time_sec)
  p.motor_board.Touch(func)
  time.sleep(time_sec)
  p.motor_board.Release(func)


def Main():
  """The Main program."""
  logging.basicConfig(
      format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)

  options = ParseArgs()

  address = 'http://%s:%s' % (options.host, options.port)
  proxy = xmlrpclib.ServerProxy(address)
  logging.info('Connected to %s with MAC address %s',
               address, proxy.GetMacAddress())
  ShowMessages(proxy)
  StartInteractiveShell(proxy, options)


if __name__ == '__main__':
  Main()
