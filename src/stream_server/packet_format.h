// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
#ifndef PACKET_FORMAT_H_
#define PACKET_FORMAT_H_

#include <stdint.h>

enum MessageVersion {
  kMajor = 1,
  kMinor = 0,
};

enum MessageMainType {
  kRequest = 0,
  kResponse = 1,
  kData = 2,
};

/* We will use a handler table to process these messages.
 * _g_handler[] in session.c
 */
enum MessageType {
  kReset = 0,
  kGetVersion = 1,
  kConfigVideoStream = 2,
  kConfigShrinkVideoStream = 3,
  kDumpVideoFrame = 4,
  kDumpRealtimeVideoFrame = 5,
  kStopDumpVideoFrame = 6,
  kDumpRealtimeAudioPage = 7,
  kStopDumpAudioPage = 8,
  kMaxMessageType
};

enum ErrorCode {
  kOK = 0,
  kNonSupportCommand = 1,
  kArgument = 2,
  kRealtimeStreamExists = 3,
  kVideoMemoryOverflowStop = 4,
  kVideoMemoryOverflowDrop = 5,
  kAudioMemoryOverflowStop = 6,
  kAudioMemoryOverflowDrop = 7,
  kMemoryAllocFail = 8,
};

typedef enum {
  kNonRealtime = 0,
  kStopWhenOverflow = 1,
  kBestEffort = 2,
} RealtimeMode;

typedef struct {
  uint16_t type;
  uint16_t error_code;
  uint32_t length;
  char content[];
} PacketHead;

typedef struct {
  uint8_t major;
  uint8_t minor;
} GetVersionResponse;

typedef struct {
  uint16_t screen_width;
  uint16_t screen_height;
} ConfigVideoStreamRequest;

typedef struct {
  uint8_t shrink_width;
  uint8_t shrink_height;
} ConfigShrinkVideoStreamRequest;

typedef struct {
  uint32_t memory_address1;
  uint32_t memory_address2;
  uint16_t number_of_frames;
} DumpVideoFrameRequest;

typedef struct {
  uint8_t is_dual;
  uint8_t mode;
} DumpRealtimeVideoRequest;

typedef struct {
  uint32_t frame_number;
  uint16_t width;
  uint16_t height;
  uint8_t channel;
  /* indicate padding explicitly.*/
  uint8_t padding[3];

  uint8_t rawdata[];
} VideoDataStream;

typedef struct {
  uint8_t mode;
} DumpRealtimeAudioRequest;

typedef struct {
  uint32_t page_count;
  uint8_t rawdata[];
} AudioDataStream;

typedef struct {
  PacketHead head;
  VideoDataStream data_head;
} VideoDataStreamHead;

typedef struct {
  PacketHead head;
  AudioDataStream data_head;
} AudioDataStreamHead;

typedef DumpVideoFrameRequest DumpRealtimeVideoFrameRequest;

#endif // PACKET_FORMAT_H_
