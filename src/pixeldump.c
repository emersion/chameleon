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

int main(int argc, char **argv)
{
  unsigned long size, page_aligned_size;
  int ifd, ofd;
  void *src, *dst;

  if (argc < 3) {
    fprintf(stderr, "Usage: %s size_in_byte filename\n", argv[0]);
    exit(1);
  }

  errno = 0;
  size = strtoul(argv[1], NULL, 0);
  if (errno) {
    perror("failed to parse size\n");
    exit(1);
  }

  ifd = open("/dev/mem", O_RDWR | O_SYNC);
  if (ifd == -1) {
    perror("can't open /dev/mem\n");
    exit(1);
  }

  ofd = open(argv[2], O_RDWR | O_CREAT, 0644);
  if (ofd == -1) {
    perror("can't open dest file\n");
    exit(1);
  }

  page_aligned_size = size + (-size % getpagesize());
  src = mmap(0, page_aligned_size, PROT_READ | PROT_WRITE,
             MAP_SHARED, ifd, FB_START);
  if (src == MAP_FAILED) {
    perror("cannot mmap src\n");
    exit(1);
  }

  ftruncate(ofd, size);
  dst = mmap(0, size, PROT_READ | PROT_WRITE, MAP_SHARED, ofd, 0);
  if (dst == MAP_FAILED) {
    perror("cannot mmap dst\n");
    exit(1);
  }

  memcpy(dst, src, size);
  munmap(dst, size);
  munmap(src, size);
  close(ofd);
  close(ifd);
  return 0;
}
