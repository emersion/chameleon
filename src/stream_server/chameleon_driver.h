// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
#ifndef CHAMELEON_DRIVER_H_
#define CHAMELEON_DRIVER_H_

#include <stdint.h>

void ChameleonInit(void);
void ChameleonDestroy(void);

/**
 * @param channel Used to choose video dump controller.
 *  0 - video dump controller A
 *  1 - video dump controller B
 */
uint32_t ChameleonVideoGetClock(int channel);
uint32_t ChameleonVideoGetRun(int channel);
uint32_t ChameleonVideoGetHashMode(int channel);
uint32_t ChameleonVideoGetCropEnable(int channel);
uint32_t ChameleonVideoGetOverflow(int channel);
uint32_t ChameleonVideoGetDumpStartAddress(int channel);
uint32_t ChameleonVideoGetDumpEndAddress(int channel);
uint32_t ChameleonVideoGetDumpLoop(int channel);
uint32_t ChameleonVideoGetDumpLimit(int channel);
uint32_t ChameleonVideoGetFrameWidth(int channel);
uint32_t ChameleonVideoGetFrameHeight(int channel);
uint32_t ChameleonVideoGetFrameCount(int channel);

/**
 * @brief ChameleonVideoGetCrop
 * Get Crop Left, Right, Top and Bottom
 *
 * @param channel Video dump controller channel. (0/1)
 * @param positions[4] Returned values indexed by CropPosition
 *   0 - Crop Left
 *   1 - Crop Right
 *   2 - Crop Top
 *   3 - Crop Bottom
 */
enum CropPosition {
  kCropLeftIndex = 0,
  kCropRightIndex = 1,
  kCropTopIndex = 2,
  kCropBottomIndex = 3,
};
void ChameleonVideoGetCrop(int channel, int positions[4]);

uint32_t ChameleonAudioGetRun(void);
uint32_t ChameleonAudioGetOverflow(void);
uint32_t ChameleonAudioGetDumpStartAddress(void);
uint32_t ChameleonAudioGetDumpEndAddress(void);
uint32_t ChameleonAudioGetDumpLoop(void);
uint32_t ChameleonAudioGetPageCount(void);

#endif // CHAMELEON_DRIVER_H_
