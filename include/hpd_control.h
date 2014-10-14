// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHAMELEON_HPD_CONTROL_H__
#define CHAMELEON_HPD_CONTROL_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>

/* Types */
typedef int (*cmd_func)(const int argc, const char **argv);
struct cmd {
  const char *name;
  cmd_func func;
  int argc;
};

/* Constants */
#define MEM_DEV_FILE "/dev/mem"
#define MEM_ADDR_GPIO 0xff21a000
#define BIT_HPD_MASK 0x1

/* Function declarations */
int cmd_status(const int argc, const char **argv);
int cmd_plug(const int argc, const char **argv);
int cmd_unplug(const int argc, const char **argv);
int cmd_repeat_pulse(const int argc, const char **argv);
int cmd_pulse(const int argc, const char **argv);

#ifdef __cplusplus
}
#endif

#endif  // CHAMELEON_HPD_CONTROL_H__
