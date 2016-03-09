// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* Pixel Histogram Utility
 *
 * This is a command-line tool running on Chameleon board to compute the
 * histogram of sampled pixels from the Chameleon framebuffer.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define MAX_COMPUTE_NUM 1024

static char *prog = NULL;


void usage_exit()
{
  fprintf(stderr,
          "Usage:\t%s screen_width screen_height\\\n"
          "\t[-g grid_num] [-s grid_sample_num] [-a start_addr]...\n"
          "Compute the histogram of sampled pixels.\n",
          prog);
  exit(1);
}


unsigned int read_uint(char *s)
{
  char *endptr;
  unsigned int v;

  errno = 0;
  v = strtoul(s, &endptr, 0);

  if (errno || *endptr != '\0') {
    fprintf(stderr, "failed to parse argument: '%s'\n", s);
    usage_exit();
  }
  return v;
}


void compute_histogram(char *start_addr, int grid_sample_num,
                       unsigned long vstep, unsigned long hstep)
{
  int buckets[4] = {0};
  int i, j;

  for (i = 0; i < grid_sample_num; i++) {
    for (j = 0; j < grid_sample_num; j++) {
      buckets[*start_addr >> 6]++;
      start_addr += vstep;
    }
    start_addr += hstep - vstep * grid_sample_num;
  }
  printf("%d %d %d %d ", buckets[0], buckets[1], buckets[2], buckets[3]);
}


int main(int argc, char **argv)
{
  unsigned long fb_start[MAX_COMPUTE_NUM] = {0xc0000000, 0};
  unsigned long screen_width, screen_height;
  unsigned long screen_size, page_aligned_size;
  unsigned long grid_sample_width, grid_sample_height;
  unsigned long grid_width, grid_height;
  unsigned long first_sample_left, first_sample_top;
  unsigned long byte_per_pixel = 3;
  int ifd;
  char *src, *start_addr;
  int opt;
  int compute_num = 0;
  int grid_num = 3;
  int grid_sample_num = 10;
  int i, row, col, rgb;

  prog = argv[0];
  while ((opt = getopt(argc, argv, "a:g:s:")) != -1) {
    switch (opt) {
      case 'a':
        fb_start[compute_num] = read_uint(optarg);
        compute_num++;
        if (compute_num > MAX_COMPUTE_NUM) {
          fprintf(stderr, "too many addresses");
          usage_exit();
        }
        break;
      case 'g':
        grid_num = read_uint(optarg);
        break;
      case 's':
        grid_sample_num = read_uint(optarg);
        break;
      default:
        usage_exit();
    }
  }
  if (compute_num == 0) {
    compute_num = 1;
  }

  if (optind + 2 != argc) {
    usage_exit();
  }

  screen_width = read_uint(argv[optind]);
  screen_height = read_uint(argv[optind + 1]);
  screen_size = screen_width * screen_height;

  ifd = open("/dev/mem", O_RDWR | O_SYNC);
  if (ifd == -1) {
    perror("can't open /dev/mem\n");
    exit(1);
  }

  page_aligned_size = screen_size * byte_per_pixel;
  page_aligned_size += (-page_aligned_size % getpagesize());

  for (i = 0; i < compute_num; i++) {
    src = mmap(0, page_aligned_size, PROT_READ, MAP_SHARED, ifd, fb_start[i]);
    if (src == MAP_FAILED) {
      perror("cannot mmap\n");
      exit(1);
    }

    // To make the sample points evenly, instead of the grids evenly,
    // calculate the width of sample points first.
    grid_sample_width = screen_width / (grid_num * grid_sample_num);
    grid_width = grid_sample_width * grid_sample_num;
    // To make the group of sample points centralized to the screen.
    first_sample_left = (grid_sample_width / 2 +
                         (screen_width - grid_width * grid_num) / 2);

    grid_sample_height = screen_height / (grid_num * grid_sample_num);
    grid_height = grid_sample_height * grid_sample_num;
    first_sample_top = (grid_sample_height / 2 +
                        (screen_height - grid_height * grid_num) / 2);

    start_addr = (src + (first_sample_top - 1) * screen_width * byte_per_pixel +
                  first_sample_left * byte_per_pixel);
    for (row = 0; row < grid_num; row++) {
      for (col = 0; col < grid_num; col++) {
        for (rgb = 0; rgb < 3; rgb++) {
          compute_histogram(start_addr + rgb, grid_sample_num,
                            grid_sample_width * byte_per_pixel,
                            grid_sample_height * screen_width * byte_per_pixel);
        }
        start_addr += grid_width * byte_per_pixel;
      }
      start_addr += (grid_height * screen_width * byte_per_pixel -
                     grid_width * byte_per_pixel * grid_num);
    }
    munmap(src, page_aligned_size);
    printf("\n");
  }
  close(ifd);
  return 0;
}
