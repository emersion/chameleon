// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* Audio Video Capturing synchronization utility
 *
 * This is a command-line tool running on chameleon board to monitor the
 * changes of the audio page count and the video page count, and calcuate the
 * time interval between the first audio/video data captured.
 */

#include <assert.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>

const int controller_addr = 0xff210000;
const int controller_size = 0x10000;

char* mem;

inline int read_mem(int addr)
{
  return *(int*)(mem + (addr - controller_addr));
}

inline int audio_page_count()
{
  const int audio_regs_base = 0xff212000;
  const int audio_reg_page_count = 0x14;

  return read_mem(audio_regs_base + audio_reg_page_count);
}

inline int video_field_count()
{
  const int video_regs_base = 0xff210000;
  const int video_reg_frame_count = 0x20;

  return read_mem(video_regs_base + video_reg_frame_count);
}

int main()
{
  const int fd = open("/dev/mem", O_RDONLY | O_SYNC);
  if (fd == -1) {
    perror("open");
    exit(1);
  }

  mem = mmap(NULL, controller_size, PROT_READ, MAP_SHARED, fd, controller_addr);
  if (mem == MAP_FAILED) {
    perror("mmap");
    exit(1);
  }

  int last_audio_page_count = audio_page_count();
  int last_video_frame_count = video_field_count();

  struct timeval ta, tv;
  bool done_audio = false, done_video = false;
  time_t timeout = time(NULL) + 20;
  while ((!done_audio || !done_video) && time(NULL) < timeout) {
    if (!done_audio) {
      const int current_audio_page_count = audio_page_count();
      if (current_audio_page_count > last_audio_page_count) {
        gettimeofday(&ta, NULL);
        done_audio = true;
      }
      last_audio_page_count = current_audio_page_count;
    }
    /*
     * In chameleond, VideoDumper will capture 1 frame when it selects a new
     * input, so the change of the frame count from 0 to 1 may be originated
     * from that frame, and the second captured frame is always the frame
     * we care about.
     */
    if (!done_video) {
      const int current_video_frame_count = video_field_count();
      if (current_video_frame_count > last_video_frame_count &&
          current_video_frame_count >= 2) {
        gettimeofday(&tv, NULL);
        done_video = true;
      }
      last_video_frame_count = current_video_frame_count;
    }
    usleep(100);
  }

  if (!done_audio || !done_video) {
    return -1;
  }

  /*
   * Because tv is the time when the second frame was captured, to estimate
   * the time when the first frame was captured, we need to shift it by -1/60
   * second.
   */
  const double diff = (tv.tv_sec - ta.tv_sec) +
                      (tv.tv_usec - ta.tv_usec) * 1e-6 -
                      1.0 / 60;

  printf("%.8f\n", diff);

  munmap(mem, controller_size);
  close(fd);

  return 0;
}
