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

#define FB_START 0xc0000000
#define BYTE_PER_PIXEL 4

int main(int argc, char **argv)
{
  int i;
  unsigned long int_args[9];
  unsigned long screen_width, screen_height, byte_per_pixel;
  unsigned long area_x, area_y, area_width, area_height;
  unsigned long screen_size, page_aligned_size, area_size;
  int ifd, ofd;
  void *src, *dst;
  int src_offset, dst_offset;
  const int region_dump = (argc == 9);

  if (argc != 5 && argc != 9) {
    fprintf(stderr,
            "Usage:\t%s filename screen_width screen_height byte_per_pixel \\\n"
            "\t[area_x area_y area_width area_height]\n"
            "Dump the pixels of a selected area from the screen to a file.\n",
            argv[0]);
    exit(1);
  }

  errno = 0;
  for (i = 2; i < argc; i++) {
    int_args[i] = strtoul(argv[i], NULL, 0);
    if (errno) {
      perror("failed to parse size\n");
      exit(1);
    }
  }
  byte_per_pixel = int_args[4];
  screen_width = int_args[2] * byte_per_pixel;
  screen_height = int_args[3];
  area_size = screen_size = screen_width * screen_height;
  if (region_dump) {
    area_x = int_args[5] * byte_per_pixel;
    area_y = int_args[6];
    area_width = int_args[7] * byte_per_pixel;
    area_height = int_args[8];
    area_size = area_width * area_height;
  }

  ifd = open("/dev/mem", O_RDWR | O_SYNC);
  if (ifd == -1) {
    perror("can't open /dev/mem\n");
    exit(1);
  }

  ofd = open(argv[1], O_RDWR | O_CREAT, 0644);
  if (ofd == -1) {
    perror("can't open dest file\n");
    exit(1);
  }

  page_aligned_size = screen_size + (-screen_size % getpagesize());
  src = mmap(0, page_aligned_size, PROT_READ | PROT_WRITE,
             MAP_SHARED, ifd, FB_START);
  if (src == MAP_FAILED) {
    perror("cannot mmap src\n");
    exit(1);
  }

  ftruncate(ofd, area_size);
  dst = mmap(0, area_size, PROT_READ | PROT_WRITE, MAP_SHARED, ofd, 0);
  if (dst == MAP_FAILED) {
    perror("cannot mmap dst\n");
    exit(1);
  }

  if (region_dump) {
    src_offset = area_y * screen_width + area_x;
    dst_offset = 0;
    for (i = 0; i < area_height; i++) {
      memcpy(dst + dst_offset, src + src_offset, area_width);
      src_offset += screen_width;
      dst_offset += area_width;
    }
  } else {
    memcpy(dst, src, area_size);
  }
  munmap(dst, area_size);
  munmap(src, page_aligned_size);
  close(ofd);
  close(ifd);
  return 0;
}
