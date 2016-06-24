// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* Chameleon Board driver
 *
 * It's a singleton instance.
 * Used to control chameleon board and get values.
 */

#include "chameleon_driver.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/*
 * The unit of the offset is 4 bytes for type uint32_t
 */
enum VideoDumpReg {
  kVideoRegControl = 0x0,
  kVideoRegOverflow = 0x1,
  kVideoRegStartAddress = 0x2,
  kVideoRegEndAddress = 0x3,
  kVideoRegDumpLoop = 0x4,
  kVideoRegDumpLimit = 0x5,
  kVideoRegFrameWidth = 0x6,
  kVideoRegFrameHeight = 0x7,
  kVideoRegFrameCount = 0x8,
  kVideoRegCropLeftRight = 0x9,
  kVideoRegCropTopBottom = 0xA,
  kVideoRegFrameHashBuffer = 0x100,
};

enum AudioDumpReg {
  kAudioRegControl = 0x0,
  kAudioRegOverflow = 0x1,
  kAudioRegStartAddress = 0x2,
  kAudioRegEndAddress = 0x3,
  kAudioRegDumpLoop = 0x4,
  kAudioRegPageCount = 0x5
};

enum RegVideoControlBitMask {
  kVideoControlBitMaskClock = 0x2,
  kVideoControlBitMaskRun = 0xC,
  kVideoControlBitMaskHashMode = 0x10,
  kVideoControlBitMaskCrop = 0x20,
};

enum RegVideoControlBitShift {
  kVideoControlBitShiftClock = 1,
  kVideoControlBitShiftRun = 2,
  kVideoControlBitShiftHashMode = 4,
  kVideoControlBitShiftCrop = 5,
};

/* Video dump controller address */
static const unsigned long kVideoDumpAddress1_ = 0xFF210000;
static const unsigned long kVideoDumpAddress2_ = 0xFF211000;
static const unsigned long kAudioDumpAddress_ = 0xFF212000;
static const unsigned long kVideoDumpRegSize_ = 0x400;
static const unsigned long kAudioDumpRegSize_ = 0x18;
static const unsigned long kARMMemoryOffset_ = 0xC0000000;

typedef struct {
  int dev_mem_fd;
  /* video dump registers */
  unsigned long *video_dump_regs[2];
  /* audio dump registers */
  unsigned long *audio_dump_regs;
} ChameleonDriver;

static int g_is_init_ = 0;
static ChameleonDriver g_chameleon_;

static inline uint32_t _read_video_register(int channel, int offset)
{
  return g_chameleon_.video_dump_regs[channel][offset];
}

static inline uint32_t _mask_shift_right(uint32_t value, int mask, int shift)
{
  return (value & mask) >> shift;
}

static void _InitVideoRegister(void)
{
  unsigned long *vdump_control_a, *vdump_control_b;

  vdump_control_a = mmap(0, kVideoDumpRegSize_, PROT_READ, MAP_SHARED,
                         g_chameleon_.dev_mem_fd, kVideoDumpAddress1_);
  vdump_control_b = mmap(0, kVideoDumpRegSize_, PROT_READ, MAP_SHARED,
                         g_chameleon_.dev_mem_fd, kVideoDumpAddress2_);
  if (vdump_control_a == MAP_FAILED) {
    perror("cannot mmap vdump_controla\n");
    exit(1);
  }
  if (vdump_control_b == MAP_FAILED) {
    perror("cannot mmap vdump_controlb\n");
    exit(1);
  }
  g_chameleon_.video_dump_regs[0] = vdump_control_a;
  g_chameleon_.video_dump_regs[1] = vdump_control_b;
}

static void _InitAudioRegister(void)
{
  char *adump_control;

  adump_control = mmap(0, kAudioDumpRegSize_, PROT_READ, MAP_SHARED,
                       g_chameleon_.dev_mem_fd, kAudioDumpAddress_);
  if (adump_control == MAP_FAILED) {
    perror("cannot mmap adump_control\n");
    exit(1);
  }

  g_chameleon_.audio_dump_regs = (unsigned long *)adump_control;
}

uint32_t ChameleonVideoGetClock(int channel)
{
  uint32_t control = _read_video_register(channel, kVideoRegControl);
  return _mask_shift_right(control, kVideoControlBitMaskClock,
                           kVideoControlBitShiftClock);
}

uint32_t ChameleonVideoGetRun(int channel)
{
  uint32_t control = _read_video_register(channel, kVideoRegControl);
  return _mask_shift_right(control, kVideoControlBitMaskRun,
                           kVideoControlBitShiftRun);
}

uint32_t ChameleonVideoGetHashMode(int channel)
{
  uint32_t control = _read_video_register(channel, kVideoRegControl);

  return _mask_shift_right(control, kVideoControlBitMaskHashMode,
                           kVideoControlBitShiftHashMode);
}

uint32_t ChameleonVideoGetCropEnable(int channel)
{
  uint32_t control = _read_video_register(channel, kVideoRegControl);

  return _mask_shift_right(control, kVideoControlBitMaskCrop,
                           kVideoControlBitShiftCrop);
}

uint32_t ChameleonVideoGetOverflow(int channel)
{
#define _OVERFLOW_BIT 0x1
  return _read_video_register(channel, kVideoRegOverflow) & _OVERFLOW_BIT;
#undef _OVERFLOW_BIT
}

uint32_t ChameleonVideoGetDumpStartAddress(int channel)
{
  return _read_video_register(channel, kVideoRegStartAddress) +
      kARMMemoryOffset_;
}

uint32_t ChameleonVideoGetDumpEndAddress(int channel)
{
  return _read_video_register(channel, kVideoRegEndAddress) + kARMMemoryOffset_;
}

uint32_t ChameleonVideoGetDumpLoop(int channel)
{
  return _read_video_register(channel, kVideoRegDumpLoop);
}

uint32_t ChameleonVideoGetDumpLimit(int channel)
{
  return _read_video_register(channel, kVideoRegDumpLimit);
}

uint32_t ChameleonVideoGetFrameWidth(int channel)
{
  return _read_video_register(channel, kVideoRegFrameWidth);
}

uint32_t ChameleonVideoGetFrameHeight(int channel)
{
  return _read_video_register(channel, kVideoRegFrameHeight);
}

uint32_t ChameleonVideoGetFrameCount(int channel)
{
  return _read_video_register(channel, kVideoRegFrameCount);
}

void ChameleonVideoGetCrop(int channel, int positions[4])
{
  uint32_t value;

  // Get Left and Right
  value = _read_video_register(channel, kVideoRegCropLeftRight);
  positions[kCropLeftIndex] = value & 0xFFFF;
  positions[kCropRightIndex] = value >> 16;

  // Get Top and Bottom
  value = _read_video_register(channel, kVideoRegCropTopBottom);
  positions[kCropTopIndex] = value & 0xFFFF;
  positions[kCropBottomIndex] = value >> 16;
}

uint32_t ChameleonAudioGetRun(void)
{
#define _RUN_BIT 0x2
  uint32_t control = g_chameleon_.audio_dump_regs[kAudioRegControl];
  return (control & _RUN_BIT);
#undef _RUN_BIT
}

uint32_t ChameleonAudioGetOverflow(void)
{
#define _OVERFLOW_BIT 0x1
  return g_chameleon_.audio_dump_regs[kAudioRegOverflow] & _OVERFLOW_BIT;
#undef _OVERFLOW_BIT
}

uint32_t ChameleonAudioGetDumpStartAddress(void)
{
  return g_chameleon_.audio_dump_regs[kAudioRegStartAddress] +
      kARMMemoryOffset_;
}

uint32_t ChameleonAudioGetDumpEndAddress(void)
{
  return g_chameleon_.audio_dump_regs[kAudioRegEndAddress] + kARMMemoryOffset_;
}

uint32_t ChameleonAudioGetDumpLoop(void)
{
  return g_chameleon_.audio_dump_regs[kAudioRegDumpLoop];
}

uint32_t ChameleonAudioGetPageCount(void)
{
  return g_chameleon_.audio_dump_regs[kAudioRegPageCount];
}

void ChameleonInit(void)
{
  if (g_is_init_)
    return;

  memset(&g_chameleon_, 0, sizeof(ChameleonDriver));

  g_chameleon_.dev_mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
  if (g_chameleon_.dev_mem_fd == -1) {
    perror("can't open /dev/mem\n");
    exit(1);
  }

  _InitVideoRegister();
  _InitAudioRegister();

  g_is_init_ = 1;
}

void ChameleonDestroy(void)
{
  if (!g_is_init_)
    return;
  g_is_init_ = 0;
  munmap(g_chameleon_.video_dump_regs[0], kVideoDumpRegSize_);
  munmap(g_chameleon_.video_dump_regs[1], kVideoDumpRegSize_);
  munmap(g_chameleon_.audio_dump_regs, kVideoDumpRegSize_);
  close(g_chameleon_.dev_mem_fd);
}
