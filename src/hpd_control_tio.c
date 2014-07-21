// Copyright 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* HPD Control Utility.
 *
 * This is a command-line tool running on Chameleon board to control the
 * HPD signal, like emulating a plug, an unplug, or multiple HPD pulse.
 */

static const char *USAGE =

"command\n"
"\n"
"Commands:\n"
"  status OFFSET             - Shows the HPD status.\n"
"  plug OFFSET               - Assert HPD line to high, emulating a plug.\n"
"  unplug OFFSET             - Deassert HPD line to low, emulating an unplug.\n"

"  repeat_pulse OFFSET TD TA C EL \n"
"                        - Repeat multiple HPD pulse (L->H->L->...->L->H).\n"
"                      TD: The time in usec of the deassert pulse.\n"
"                      TA: The time in usec of the assert pulse.\n"
"                       C: The repeat count.\n"
"                      EL: End level: 0 for LOW or 1 for HIGH.\n"
"\n"
"OFFSET:\n"
"   DP1:  4\n"
"   DP2:  8\n"
"  HDMI: 12\n";

#include <fcntl.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include <hpd_control_tio.h>

/* The time in usec. If required HPD pulse is smaller than this duration.
 * Set the process scheduling to the highest real-time priority.
 */
#define DURATION_NEED_RT 50000  // 50 msec

/* Commands and their dispatch functions */
static const struct cmd COMMAND_LIST[] = {
  { "status", cmd_status, 0 },
  { "plug", cmd_plug, 0 },
  { "unplug", cmd_unplug, 0 },
  { "repeat_pulse", cmd_repeat_pulse, 4 },
  { NULL, NULL, 0 }  // end-of-list
};

/* Pointer to the first argument, i.e. the program name. */
static const char *g_argv0 = NULL;

/* Global varible for accessing the GPIO register */
static unsigned char *g_gpio_ptr = NULL;

/* Global varible for HPD offset in g_gpio_ptr */
static unsigned int hpd_offset = 0;

/* Prints the usage. */
static void usage(void)
{
  fprintf(stderr, "Usage: %s %s", g_argv0, USAGE);
}

/* Initializes the memory map for the gpio register. */
void init(void)
{
  int fd;
  size_t page_size = sysconf(_SC_PAGESIZE);
  unsigned char *mmap_addr;

  // Memory-map the page which contains the GPIO register.
  fd = open(MEM_DEV_FILE, O_RDWR | O_SYNC);
  mmap_addr = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
                   MAP_SHARED, fd, MEM_ADDR_GPIO / page_size * page_size);
  if (mmap_addr == (void *)-1) {
    perror("mmap");
    exit(EXIT_FAILURE);
  }
  // Add the offset in the page to address the GPIO register.
  g_gpio_ptr = mmap_addr + MEM_ADDR_GPIO % page_size;
}

/* Sets the current process to run in the highest real-time priority. */
static void set_rt_scheduler(void)
{
  struct sched_param sp;

  sp.sched_priority = sched_get_priority_max(SCHED_FIFO);
  if (sched_setscheduler(getpid(), SCHED_FIFO, &sp) != 0) {
    perror("sched_setscheduler");
    exit(EXIT_FAILURE);
  }
}

/* Function to show the HPD status */
int cmd_status(const int argc, const char **argv)
{
  printf("HPD=%d\n", (g_gpio_ptr[hpd_offset] & BIT_HPD_MASK) ? 1 : 0);
  return 0;
}

/* Function to assert HPD line to high, emulating a plug */
int cmd_plug(const int argc, const char **argv)
{
  // Set to plug
  g_gpio_ptr[hpd_offset] |= BIT_HPD_MASK;
  return 0;
}

/* Function to deassert HPD line to low, emulating an unplug */
int cmd_unplug(const int argc, const char **argv)
{
  // Clear to unplug.
  g_gpio_ptr[hpd_offset] &= ~BIT_HPD_MASK;
  return 0;
}

/* Function to repeat multiple HPD pulse (H->L->H->...->H) */
int cmd_repeat_pulse(const int argc, const char **argv)
{
  int deassert_usec, assert_usec, count, end_level;
  int i;

  deassert_usec = atoi(argv[0]);
  assert_usec = atoi(argv[1]);
  count = atoi(argv[2]);
  end_level = atoi(argv[3]);
  if (deassert_usec <= 0 || assert_usec <= 0 || count <= 0 ||
      (end_level != 0 && end_level != 1)) {
    fprintf(stderr, "Wrong paramenters.\n\n");
    usage();
    return 1;
  }

  // Only set real-time scheduling when the duration is too short.
  if (deassert_usec <= DURATION_NEED_RT || assert_usec <= DURATION_NEED_RT)
    set_rt_scheduler();

  for (i = 0; i < count; i++) {
    g_gpio_ptr[hpd_offset] &= ~BIT_HPD_MASK;
    usleep(deassert_usec);
    g_gpio_ptr[hpd_offset] |= BIT_HPD_MASK;
    usleep(assert_usec);
  }

  //End with HPD low
  if (!end_level) {
    g_gpio_ptr[hpd_offset] &= ~BIT_HPD_MASK;
  }
  return 0;
}

/* Main program */
int main(const int argc, const char **argv)
{
  const char *command = NULL;
  const struct cmd *cur_cmd = NULL;

  g_argv0 = argv[0];

  // Print usage and quit if no argument command or no hpd_offset.
  if (argc <= 2) {
    usage();
    return 1;
  }

  init();
  command = argv[optind++];
  hpd_offset = atoi(argv[optind++]);
  if (hpd_offset != 4 && hpd_offset != 8 && hpd_offset != 12) {
    fprintf(stderr, "Unsupported HPD offset: %u.\n\n", hpd_offset);
    usage();
    return 1;
  }
  // Hand off to the proper function.
  for (cur_cmd = COMMAND_LIST; cur_cmd->name; ++cur_cmd) {
    if (!strcmp(command, cur_cmd->name)) {
      if (argc - optind != cur_cmd->argc) {
        fprintf(stderr, "Number of parameters not correct.\n\n");
        usage();
        return 1;
      }
      return cur_cmd->func(argc - optind, &argv[optind]);
    }
  }

  // No matched command. Print an error.
  fprintf(stderr, "Unrecognized command.\n\n");
  usage();
  return 1;
}
