// Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* Pixel Dump Utility
 *
 * This is a command-line tool running on Chameleon board to dump the
 * pixels from the Chameleon framebuffer to a given file.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static char *prog = NULL;


void usage_exit()
{
  fprintf(stderr,
          "Usage:\t%s filename screen_width screen_height byte_per_pixel \\\n"
          "\t[area_x area_y area_width area_height] \\\n"
          "\t[-a start_addr_a] [-b start_addr_b]\n"
          "Dump the pixels of a selected area from the screen to a file.\n",
          prog);
  exit(1);
}


unsigned int read_uint(char *s)
{
  char *endptr;
  unsigned int v = strtoul(s, &endptr, 0);

  errno = 0;
  if (errno || *endptr != '\0') {
    fprintf(stderr, "failed to parse argument: '%s'\n", s);
    usage_exit();
  }
  return v;
}


int main(int argc, char **argv)
{
  unsigned long fb_start[2] = {0xc0000000, 0};
  unsigned long screen_width, screen_height, byte_per_pixel;
  unsigned long area_x, area_y, area_width = 0, area_height = 0;
  unsigned long screen_size, page_aligned_size, area_size;
  int ifd, ofd;
  char *src[2], *src_buf[2], *dst, *dst_buf;
  int src_offset, dst_offset;
  int region_dump = 0;
  int num_buffer = 1;
  char *filename;
  int opt;
  int i, j;

  prog = argv[0];
  while ((opt = getopt(argc, argv, "a:b:")) != -1) {
    switch (opt) {
      case 'a':
        fb_start[0] = read_uint(optarg);
        break;
      case 'b':
        fb_start[1] = read_uint(optarg);
        num_buffer = 2;
        break;
      default:
        usage_exit();
    }
  }

  if (optind + 4 != argc && optind + 8 != argc) {
    usage_exit();
  }

  filename = argv[optind];
  byte_per_pixel = read_uint(argv[optind + 3]);
  /* Use the term "screen" for the src while the term "area" for the dst. */
  screen_width = read_uint(argv[optind + 1]) * byte_per_pixel;
  screen_height = read_uint(argv[optind + 2]);
  screen_size = screen_width * screen_height;
  area_size = screen_size * num_buffer;

  if (optind + 4 < argc) {
    region_dump = 1;
    area_x = read_uint(argv[optind + 4]) * byte_per_pixel;
    area_y = read_uint(argv[optind + 5]);
    area_width = read_uint(argv[optind + 6]) * byte_per_pixel;
    area_height = read_uint(argv[optind + 7]);
    area_size = area_width * area_height;
  }

  ifd = open("/dev/mem", O_RDWR | O_SYNC);
  if (ifd == -1) {
    perror("can't open /dev/mem\n");
    exit(1);
  }

  ofd = open(filename, O_RDWR | O_CREAT, 0644);
  if (ofd == -1) {
    perror("can't open dest file\n");
    exit(1);
  }

  page_aligned_size = screen_size + (-screen_size % getpagesize());
  for (i = 0; i < num_buffer; i++) {
    src[i] = mmap(0, page_aligned_size, PROT_READ,
                  MAP_SHARED, ifd, fb_start[i]);
    if (src[i] == MAP_FAILED) {
      perror("cannot mmap src\n");
      exit(1);
    }
  }

  ftruncate(ofd, area_size);
  dst = mmap(0, area_size, PROT_WRITE, MAP_SHARED, ofd, 0);
  if (dst == MAP_FAILED) {
    perror("cannot mmap dst\n");
    exit(1);
  }

  if (region_dump) {
    /* Store to a buffer for selecting the area later. */
    dst_buf = malloc(screen_size * num_buffer);
  } else {
    /* Directly dump to the destination. */
    dst_buf = dst;
  }

  if (num_buffer == 2) {
    src_buf[0] = malloc(screen_size);
    src_buf[1] = malloc(screen_size);
    memcpy(src_buf[0], src[0], screen_size);
    memcpy(src_buf[1], src[1], screen_size);
    /* Copy 2 RGB pixels each loop */
    for (i = 0; i < screen_size; i += byte_per_pixel) {
      for (j = 0; j < byte_per_pixel; j++) {
        dst_buf[2 * i + j] = src_buf[0][i + j];
        dst_buf[2 * i + byte_per_pixel + j] = src_buf[1][i + j];
      }
    }
    free(src_buf[0]);
    free(src_buf[1]);
  } else {
    memcpy(dst_buf, src[0], screen_size);
  }

  if (region_dump) {
    src_offset = area_y * screen_width + area_x;
    dst_offset = 0;
    for (i = 0; i < area_height; i++) {
      memcpy(dst + dst_offset, dst_buf + src_offset, area_width);
      src_offset += screen_width;
      dst_offset += area_width;
    }
  }
  for (i = 0; i < num_buffer; i++)
    munmap(src[i], page_aligned_size);
  munmap(dst, area_size);
  close(ofd);
  close(ifd);
  return 0;
}
