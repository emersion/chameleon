/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

/* Session procedure
 *
 * This is TCP session main procedure.
 */

#include "chameleon_driver.h"
#include "log.h"
#include "packet_format.h"
#include "session.h"
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/* Used to measure the duration of copying shared memory */
#ifdef MEASURE_DUMP_DURATION
#include <sys/time.h>
#endif

/*
 * Use define here because of array declaration.
 */
#define MAX_SOCKETBUFFER_SIZE 2048
#define MAX_VIDEO_DUMP_CHANNEL 2

/*
 * Collect all sessions' log under sessions directory.
 */
static const char *kSessionLogfilePattern_ = "session_%d.log";

static const int kRetOK_ = 0;
static const int kRetFail_ = -1;
static const int kHW_CountWrap_ = 0x10000;
static const int kBytePerPixel_ = 3;
static const int kAudioPageSize_ = 4096;

static const char *kErrorMessageMMap = "Memory map fail";
static const char *kErrorMessageMemoryAlloc = "Memory allocate fail";
static const char *kErrorMessageRealtimeMode = "Realtime mode is wrong";
static const char *kErrorMessageRealtimeStream =
    "There is an existing realtime stream";
static const char *kErrorMessageRealtimeNonSame =
    "Width or height or limit is not the same";
static const char *kErrorMessageFrameNumberZero = "Frame number is 0";
static const char *kErrorMessage2ndChannelNotRun = "2nd channel is not running";
static const char *kErrorMessageNotRun = "Capture HW is not running";
static const char *kErrorMessageDumpMemoryNotEnough =
    "Dump memory is not enough";
static const char *kErrorMessageDropVideoFrame = "Drop realtime video frame %d";
static const char *kErrorMessageDropAudioPage = "Drop realtime audio page %d";
static const char *kErrorMessageMemoryOverflow =
    "Stop dump realtime audio/video due to memory overflow";


/*
 * We only support one realtime dump per session.
 * So some of the members will be shared between audio and video.
 */
typedef struct {
  /*
   * The socket descriptor of this session.
   */
  int socket;

  /*
   * The buffer used to receive from or send to socket.
   */
  char socketbuffer[MAX_SOCKETBUFFER_SIZE];

  LogHandle log;
  int dev_mem_fd;

  /*
   * The processing message type.
   */
  enum MessageType message_type;

  /*
   * Temporary buffer for audio/video dumping.
   * We will copy data from shared memory to this buffer first.
   * If we deal with the shared memory directly, the performance will be very
   * bad.
   */
  char *p_dump_buffer;

  /*
   * The indicator to stop dumping realtime video/audio stream.
   */
  uint8_t stop_dump;

  /* To indicate the current realtime stream is audio or video */
  uint8_t is_dump_audio;

  /*
   * Store the width and height pixels of the no-realtime video dump.
   */
  uint16_t screen_width;
  uint16_t screen_height;

  /*
   * To indicate if we need to shrink the video frame during the dumping.
   * If we don't need to shrink the video frame, we can just copy the data from
   * shared memory.
   */
  uint8_t is_shrink;
  uint8_t shrink_width;
  uint8_t shrink_height;

  /*
   * For realtime video dump.
   * We have 2 video dump controllers. And we may have data from any of them.
   * We will auto detect the dump controller by the Run bit and store the info
   * in realtime_check_channel.
   */
  uint8_t realtime_check_channel;

  /*
   * The max video frames/audio pages in the dump area.
   * The dump controller will reset dump pointer to Dump Start Address after
   * dump_limit is reached.
   * For video dump, we read from the Dump Limit register of video dump
   * controller.
   * For audio dump, we calculate it from Dump Start Address and
   * Dump End Address of audio Dump Controller.
   */
  uint32_t dump_limit;

  /*
   * Store the dump start addresses of audio/video.
   * For audio dump, only the first element is used.
   */
  uint32_t dump_addresses[MAX_VIDEO_DUMP_CHANNEL];

  /*
   * Paged size aligned of audio page size or video frame size.
   * We can use it to calculate each audio/video start address.
   */
  int unit_aligned_size;

  /*
   * Store the size of mmap. So we can do munmap later.
   */
  int mmap_size;

  /*
   * The pointer of the shared memory by mmap.
   */
  char *p_mmap_sources[MAX_VIDEO_DUMP_CHANNEL];

  RealtimeMode realtime_mode;
} Session;

typedef int (*MessageHandler)(Session *);

static int _ReadFromSocket(Session *p_session, int size);
static int _SendToSocket(Session *p_session, char *p_buffer, int size);
static int _SendWholePacketToSocket(Session *p_session);
static int _ProcessReset(Session *p_session);
static int _ProcessGetVersion(Session *p_session);
static int _ProcessConfigVideoStream(Session *p_session);
static int _ProcessConfigShrinkVideoStream(Session *p_session);
static int _ProcessDumpVideoFrame(Session *p_session);
static int _ProcessDumpRealtimeVideoFrame(Session *p_session);
static int _ProcessStopDump(Session *p_session);
static int _ProcessDumpRealtimeAudioPage(Session *p_session);
static int _ProcessMessage(Session *p_session);

/*
 * Message handler table for each message type.
 * The position of the handler must be the same as the message type.
 */
static const MessageHandler _g_handlers[] = {
    _ProcessReset,
    _ProcessGetVersion,
    _ProcessConfigVideoStream,
    _ProcessConfigShrinkVideoStream,
    _ProcessDumpVideoFrame,
    _ProcessDumpRealtimeVideoFrame,
    _ProcessStopDump,
    _ProcessDumpRealtimeAudioPage,
    _ProcessStopDump,
};

static inline PacketHead *_get_packet_head(Session *p_session)
{
  return (PacketHead *)p_session->socketbuffer;
}

static unsigned _calculate_page_aligned_size(int size)
{
  int pagesize = getpagesize();

  if (size % pagesize) {
    size += pagesize;
    size -= size % pagesize;
  }

  return size;
}

/**
 * @brief _CleanDumpVariable
 * Clean the variables of the dump process.
 *
 * @param p_session Session instance.
 */
static void _CleanDumpVariable(Session *p_session)
{
  int i;

  if (p_session->p_dump_buffer) {
    free(p_session->p_dump_buffer);
    p_session->p_dump_buffer = NULL;
  }

  for (i = 0; i < MAX_VIDEO_DUMP_CHANNEL; i++) {
    if (!p_session->dump_addresses[i]) {
      continue;
    }
    p_session->dump_addresses[i] = 0;
    if (p_session->p_mmap_sources[i]) {
      munmap(p_session->p_mmap_sources[i], p_session->mmap_size);
      p_session->p_mmap_sources[i] = NULL;
    }
  }
  p_session->mmap_size = 0;
  p_session->realtime_mode = kNonRealtime;
  p_session->is_dump_audio = 0;
}

/**
 * @brief _CleanSession
 * Clean all the resources of the session.
 *
 * @param p_session Session instance
 */
static void _CleanSession(Session *p_session)
{
  LogPrint(&p_session->log, kInfo, "Cleaning Session...");

  _CleanDumpVariable(p_session);
  if (p_session->dev_mem_fd && p_session->dev_mem_fd != -1) {
    close(p_session->dev_mem_fd);
    p_session->dev_mem_fd = 0;
  }

  LogPrint(&p_session->log, kInfo, "Cleaned session.");
  LogDestroy(&p_session->log);
}

/**
 * @brief _ReadFromSocket
 * Read size of data from socket. The data will be stored in the socketbuffer.
 *
 * @param p_session Session instance.
 * @param size The size of the read data.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ReadFromSocket(Session *p_session, int size)
{
  int read_bytes;

  if (size > MAX_SOCKETBUFFER_SIZE) {
    LogPrint(&p_session->log, kWarn, "Reading size %d > buffer size %d", size,
             MAX_SOCKETBUFFER_SIZE);
    return kRetFail_;
  }

  read_bytes = read(p_session->socket, p_session->socketbuffer, size);

  if (read_bytes < 0) {
    LogPrint(&p_session->log, kWarn, "Error reading from socket");
    return kRetFail_;
  }
  if (read_bytes == 0) {
    LogPrint(&p_session->log, kInfo, "Client disconnected");
    return kRetFail_;
  }
  if (read_bytes != size) {
    LogPrint(&p_session->log, kWarn,
             "Read error: read bytes %d, expected bytes %d", read_bytes, size);
    return kRetFail_;
  }

  return kRetOK_;
}

/**
 * @brief _SendToSocket
 * Send size of data to socket.
 *
 * @param p_session Session instance
 * @param p_buffer The data to be sent.
 * @param size bytes of the data.
 *
 * @return kRetFail_, kRetOK_
 */
static int _SendToSocket(Session *p_session, char *p_buffer, int size)
{
  int write_bytes;

  write_bytes = write(p_session->socket, p_buffer, size);
  if (write_bytes < 0) {
    LogPrint(&p_session->log, kWarn, "Write error code %d", errno);
    return kRetFail_;
  }
  if (write_bytes == 0) {
    LogPrint(&p_session->log, kInfo, "Client disconnected");
    return kRetFail_;
  }
  if (write_bytes != size) {
    LogPrint(&p_session->log, kWarn, "Write bytes %d, expected bytes %d",
             write_bytes, size);
    return kRetFail_;
  }

  return kRetOK_;
}

/**
 * @brief _SendWholePacketToSocket
 * It will read length from the packet head, and send whole packet to socket.
 * The data is from the socketbuffer in the session.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _SendWholePacketToSocket(Session *p_session)
{
  PacketHead *p_head = _get_packet_head(p_session);
  int length = htonl(p_head->length);

  return _SendToSocket(p_session, (char *)p_head, sizeof(PacketHead) + length);
}

static void _InitResponseHead(Session *p_session, int error_code, int length,
                              char *p_message)
{
  PacketHead *p_head = _get_packet_head(p_session);

  p_head->type = htons(kResponse << 8 | p_session->message_type);
  p_head->error_code = htons(error_code);
  p_head->length = htonl(length);
  if (p_message) {
    memcpy(p_head->content, p_message, length);
  }
}

static int _SendResponse(Session *p_session, int error_code, int length,
                         char *p_message) {
  _InitResponseHead(p_session, error_code, length, p_message);
  return _SendWholePacketToSocket(p_session);
}

/**
 * @brief _CheckRealtimeStream
 * Check if we have realtime streaming in this session.
 * If we have the streaming, also reply an error response.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _CheckRealtimeStream(Session *p_session)
{
  if (p_session->realtime_mode == kNonRealtime) {
    return kRetOK_;
  }

  LogPrint(&p_session->log, kWarn, (char *)kErrorMessageRealtimeStream);
  _SendResponse(p_session, kRealtimeStreamExists,
                strlen(kErrorMessageRealtimeStream),
                (char *)kErrorMessageRealtimeStream);

  return kRetFail_;
}

/**
 * @brief _DumpVideoFrameToClient
 * Dump video frame data to client without header.
 * It will also do shrink process if user requires it.
 *
 * @param p_session Session instance.
 * @param p_source The video frame start address of the shared memory.
 *
 * @return kRetFail_, kRetOK_
 */
static int _DumpVideoFrameToClient(Session *p_session, char *p_source)
{
  int width, height, pixel, size;
  int shrink_width, shrink_height;
  int screen_width, screen_height;
  char *p_dump_buffer;
  char *p_width;
#ifdef MEASURE_DUMP_DURATION
  struct timeval start, stop, diff;

  gettimeofday(&start, NULL);
#endif

  p_dump_buffer = p_session->p_dump_buffer;
  screen_width = p_session->screen_width;
  screen_height = p_session->screen_height;

  if (p_session->is_shrink) {
    shrink_width = p_session->shrink_width;
    shrink_height = p_session->shrink_height;

    /*
     * For 1920x1080 video frame. memcpy takes 152 ms.
     * For loop without shirnk takes 3.06 seconds.
     * For loop with shink width 4 and shrink height 4 takes 121 ms.
     * This memcpy will copy the whole frame from shared memory to internal
     * memory. And then we use the internal memory to do the shrink thing.
     * If we use the shared memory to do the shrink thing, it will take a long
     * time to do it if we only shrink a little pixels.
     */
    if (shrink_width < 4 || shrink_height < 4) {
      size = screen_width * screen_height * kBytePerPixel_;
      memcpy(p_dump_buffer, p_source, size);
      p_source = p_dump_buffer;
    }

    /*
     * Process data pixel by pixel.
     */
    size = 0;
    for (height = 0; height < screen_height; height++) {
      /*
       * assign start width to p_width.
       */
      p_width = p_source + screen_width * kBytePerPixel_ * height;
      for (width = 0; width < screen_width; width++) {
        // Copy pixel
        for (pixel = 0; pixel < kBytePerPixel_; pixel++) {
          p_dump_buffer[size++] = *p_width++;
        }
        // skip shrinked width
        p_width += shrink_width * kBytePerPixel_;
        width += shrink_width;
      }
      // skip shrinked height.
      height += shrink_height;
    }
  } else {
    /* Non shrink case, only copy whole video frame.*/
    size = screen_width * screen_height * kBytePerPixel_;
    memcpy(p_dump_buffer, p_source, size);
  }

#ifdef MEASURE_DUMP_DURATION
  gettimeofday(&stop, NULL);
  timersub(&stop, &start, &diff);
  LogPrint(&p_session->log, kInfo, "copy memory took %ld.%06ld",
           (long int)diff.tv_sec, (long int)diff.tv_usec);
#endif

  return _SendToSocket(p_session, p_dump_buffer, size);
}

/**
 * @brief _DoMMAP
 * Do mmap by the address and size.
 *
 * @param p_session Session instance.
 * @param address address of the mmap.
 * @param size size of the mmap.
 *
 * @return NULL - mmap failed.
 *         Pointer to the mapped area.
 */
static char *_DoMMAP(Session *p_session, uint32_t address, int size)
{
  char *p_source;

  p_source =
      mmap(0, size, PROT_READ, MAP_SHARED, p_session->dev_mem_fd, address);
  if (p_source != MAP_FAILED) {
    LogPrint(&p_session->log, kInfo, "MMAP address 0x%x, size %d bytes",
             address, size);
    return p_source;
  }

  perror("cannot mmap source\n");
  LogPrint(&p_session->log, kError, "Cannot mmap source 0x%x", address);
  _SendResponse(p_session, kArgument, strlen(kErrorMessageMMap),
                (char *)kErrorMessageMMap);
  return NULL;
}

/**
 * @brief _PrepareMMAP
 * Prepare mmap by the session's dump_addresses, dump_limit and
 * unit_aligned_size state variables.
 * The mapped pointer will be stored in p_mmap_sources.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _PrepareMMAP(Session *p_session)
{
  int i;
  int mmap_size;

  mmap_size = p_session->dump_limit * p_session->unit_aligned_size;
  p_session->mmap_size = mmap_size;

  for (i = 0; i < MAX_VIDEO_DUMP_CHANNEL; i++) {
    if (!p_session->dump_addresses[i]) {
      continue;
    }
    p_session->p_mmap_sources[i] =
        _DoMMAP(p_session, p_session->dump_addresses[i], mmap_size);
    if (p_session->p_mmap_sources[i] == NULL) {
      return kRetFail_;
    }
  }

  return kRetOK_;
}

/**
 * @brief _PrepareDumpBuffer
 * Allocate memory to the p_dump_buffer.
 * The size will be equal to the unit_aligned_size.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
int _PrepareDumpBuffer(Session *p_session)
{
  p_session->p_dump_buffer = malloc(p_session->unit_aligned_size);

  LogPrint(&p_session->log, kInfo, "Allocate frame buffer %d bytes",
           p_session->unit_aligned_size);
  if (!p_session->p_dump_buffer) {
    _SendResponse(p_session, kMemoryAllocFail, strlen(kErrorMessageMemoryAlloc),
                  (char *)kErrorMessageMemoryAlloc);
    return kRetFail_;
  }

  return kRetOK_;
}

/**
 * @brief _InitDumpVideoHead
 * Init the video dump head and packet head's content.
 *
 * @param p_session Session instance.
 * @param p_stream_head The video stream head to be inited.
 */
static void _InitDumpVideoHead(Session *p_session,
                               VideoDataStreamHead *p_stream_head)
{
  PacketHead *p_head = &p_stream_head->head;
  VideoDataStream *p_data_head = &p_stream_head->data_head;
  unsigned width, height;
  int dump_frame_size;

  p_head->type = htons(kData << 8 | p_session->message_type);
  p_head->error_code = 0;
  // Calculate length after shrinked frame
  width = p_session->screen_width / (p_session->shrink_width + 1);
  height = p_session->screen_height / (p_session->shrink_height + 1);
  dump_frame_size = width * height * kBytePerPixel_;
  p_head->length = htonl(sizeof(VideoDataStream) + dump_frame_size);
  LogPrint(&p_session->log, kInfo,
           "Start Dump, screen(%d, %d), dump(%d, %d), dump length %d",
           p_session->screen_width, p_session->screen_height, width, height,
           dump_frame_size);
  p_data_head->width = htons(width);
  p_data_head->height = htons(height);
}

/**
 * @brief _InitDumpAudioHead
 * Init the audio dump head's and packet head's content.
 *
 * @param p_session Session instance.
 * @param p_stream_head The audio stream head to be inited.
 */
static void _InitDumpAudioHead(Session *p_session,
                               AudioDataStreamHead *p_stream_head)
{
  PacketHead *p_head = &p_stream_head->head;

  p_head->type = htons(kData << 8 | p_session->message_type);
  p_head->error_code = 0;
  p_head->length = htonl(sizeof(AudioDataStream) + kAudioPageSize_);
}

/**
 * @brief _DumpAllChannelVideoFrame
 * Used to dump video frame from both dump controllers.
 *
 * @param p_session Session instance.
 * @param p_stream_head The pre-inited video stream header.
 * @param offset memory offset of the video frame.
 *
 * @return kRetFail_, kRetOK_
 */
static int _DumpAllChannelVideoFrame(Session *p_session,
                                     VideoDataStreamHead *p_stream_head,
                                     int offset)
{
  int i;
  char *p_source;
  VideoDataStream *p_data_head = &p_stream_head->data_head;

  for (i = 0; i < MAX_VIDEO_DUMP_CHANNEL; i++) {
    p_source = p_session->p_mmap_sources[i];
    // Check if we need to dump data from this channel.
    if (!p_source) {
      continue;
    }
    p_data_head->channel = i;
    /* Send video data header first */
    if (_SendToSocket(p_session, (char *)p_stream_head,
                      sizeof(VideoDataStreamHead))) {
      return kRetFail_;
    }
    /* Send remain video frame data */
    if (_DumpVideoFrameToClient(p_session, p_source + offset)) {
      return kRetFail_;
    }
  }

  return kRetOK_;
}

/**
 * @brief _DoDumpVideoFrame
 * Dump non-realtime video frames. It only dump specified number of video
 * frames to client.
 *
 * @param p_session Session instance
 * @param number_of_frames Number of the video frames.
 *
 * @return kRetFail_, kRetOK_
 */
static int _DoDumpVideoFrame(Session *p_session, int number_of_frames)
{
  VideoDataStreamHead head;
  VideoDataStream *p_data_head = &head.data_head;
  unsigned long unit_aligned_size;
  int i;

  unit_aligned_size = p_session->unit_aligned_size;

  _InitDumpVideoHead(p_session, &head);
  LogPrint(&p_session->log, kDebug, "Dump number of frame %d",
           number_of_frames);

  for (i = 0; i < number_of_frames; i++) {
    p_data_head->frame_number = htonl(i);
    if (_DumpAllChannelVideoFrame(p_session, &head, i * unit_aligned_size)) {
      return kRetFail_;
    }
  }

  return kRetOK_;
}

/**
 * @brief _GetRealtimeVideoParameters
 * Get the realtime video stream parameters from the chameleon and p_request.
 * This function will also check the chameleon status.
 *
 * @param p_session Session instance.
 * @param p_request DumpRealtimeVideoRequest
 *
 * @return kRetFail_, kRetOK_
 */
static int _GetRealtimeVideoParameters(Session *p_session,
                                       DumpRealtimeVideoRequest *p_request)
{
  int positions[4];
  int width, height;
  uint32_t dump_end_address;
  int check_channel;

  /* Auto detect the video dump channel */
  if (ChameleonVideoGetRun(0)) {
    p_session->dump_addresses[0] = ChameleonVideoGetDumpStartAddress(0);
    check_channel = 0;
  } else if (ChameleonVideoGetRun(1)) {
    p_session->dump_addresses[0] = ChameleonVideoGetDumpStartAddress(1);
    check_channel = 1;
  } else {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessageNotRun);
    _SendResponse(p_session, kArgument, strlen(kErrorMessageNotRun),
                  (char *)kErrorMessageNotRun);
    return kRetFail_;
  }

  /* Get the width and height of the video frame */
  if (ChameleonVideoGetCropEnable(check_channel)) {
    ChameleonVideoGetCrop(check_channel, positions);
    width = positions[kCropRightIndex] - positions[kCropLeftIndex];
    height = positions[kCropBottomIndex] - positions[kCropTopIndex];
  } else {
    width = ChameleonVideoGetFrameWidth(check_channel);
    height = ChameleonVideoGetFrameHeight(check_channel);
  }

  p_session->dump_limit = ChameleonVideoGetDumpLimit(check_channel);
  p_session->screen_width = width;
  p_session->screen_height = height;
  p_session->realtime_check_channel = check_channel;
  p_session->unit_aligned_size =
      _calculate_page_aligned_size(width * height * kBytePerPixel_);
  p_session->realtime_mode = p_request->mode;

  /*
   * Check memory spaces first. to prevent memory overflow due to
   * wrong chameleon config.
   */
  dump_end_address = ChameleonVideoGetDumpEndAddress(check_channel);
  LogPrint(&p_session->log, kInfo,
           "Realtime Video address[0] = 0x%x, end address = 0x%x, "
           "minimum memory space %d bytes",
           p_session->dump_addresses[0], dump_end_address,
           p_session->unit_aligned_size * p_session->dump_limit);
  if (dump_end_address - p_session->dump_addresses[0] <=
      p_session->unit_aligned_size * p_session->dump_limit) {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessageDumpMemoryNotEnough);
    _SendResponse(p_session, kArgument,
                  strlen(kErrorMessageDumpMemoryNotEnough),
                  (char *)kErrorMessageDumpMemoryNotEnough);
    return kRetFail_;
  }

  if (!p_request->is_dual) {
    // Setup 2nd channel address to 0 to indicate we only dump from one channel.
    p_session->dump_addresses[1] = 0;
    goto function_exit;
  }

  /*
   * Reply error if we want to dump from 2nd channel but the channel is
   * not running.
   */
  if (!ChameleonVideoGetRun(!check_channel)) {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessage2ndChannelNotRun);
    _SendResponse(p_session, kArgument, strlen(kErrorMessage2ndChannelNotRun),
                  (char *)kErrorMessage2ndChannelNotRun);
    return kRetFail_;
  }

  /*
   * For dual channel mode.
   * We only support same parameters on both channels now.
   * It doesn't make sense to use different parameters of 2 channels.
   */
  if (ChameleonVideoGetCropEnable(!check_channel)) {
    ChameleonVideoGetCrop(!check_channel, positions);
    width = positions[kCropRightIndex] - positions[kCropLeftIndex];
    height = positions[kCropBottomIndex] - positions[kCropTopIndex];
  } else {
    width = ChameleonVideoGetFrameWidth(!check_channel);
    height = ChameleonVideoGetFrameHeight(!check_channel);
  }
  if (p_session->screen_width != width || p_session->screen_height != height ||
      p_session->dump_limit != ChameleonVideoGetDumpLimit(!check_channel)) {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessageRealtimeNonSame);
    _SendResponse(p_session, kArgument, strlen(kErrorMessageRealtimeNonSame),
                  (char *)kErrorMessageRealtimeNonSame);
    return kRetFail_;
  }

  p_session->dump_addresses[1] =
      ChameleonVideoGetDumpStartAddress(!check_channel);
  dump_end_address = ChameleonVideoGetDumpEndAddress(!check_channel);
  LogPrint(&p_session->log, kInfo,
           "Realtime Video address[1] = 0x%x, end address = 0x%x, "
           "minimum memory space %d bytes",
           p_session->dump_addresses[1], dump_end_address,
           p_session->unit_aligned_size * p_session->dump_limit);
  if (dump_end_address - p_session->dump_addresses[1] <=
      p_session->unit_aligned_size * p_session->dump_limit) {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessageDumpMemoryNotEnough);
    _SendResponse(p_session, kArgument,
                  strlen(kErrorMessageDumpMemoryNotEnough),
                  (char *)kErrorMessageDumpMemoryNotEnough);
    return kRetFail_;
  }

function_exit:

  LogPrint(&p_session->log, kInfo, "Screen width %d, height %d, dump limit %d",
           p_session->screen_width, p_session->screen_height,
           p_session->dump_limit);

  return kRetOK_;
}

/**
 * @brief _GetRealtimeAudioParameters
 * Get the realtime audio stream parameters from the chameleon and p_request.
 * This function will also check the chameleon status.
 *
 * @param p_session Session instance.
 * @param p_request DumpRealtimeAudioRequest
 *
 * @return kRetFail_, kRetOK_
 */
static int _GetRealtimeAudioParameters(Session *p_session,
                                       DumpRealtimeAudioRequest *p_request)
{
  uint32_t dump_end_address;

  if (!ChameleonAudioGetRun()) {
    LogPrint(&p_session->log, kWarn, (char *)kErrorMessageNotRun);
    _SendResponse(p_session, kArgument, strlen(kErrorMessageNotRun),
                  (char *)kErrorMessageNotRun);
    return kRetFail_;
  }
  p_session->dump_addresses[0] = ChameleonAudioGetDumpStartAddress();
  dump_end_address = ChameleonAudioGetDumpEndAddress();
  /*
   * There is no dump limit register of audio dump controller. We calculate it
   * from the total memory spaces and audio page size.
   */
  p_session->dump_limit =
      (dump_end_address - p_session->dump_addresses[0]) / kAudioPageSize_;
  p_session->unit_aligned_size = kAudioPageSize_;
  p_session->realtime_mode = p_request->mode;

  LogPrint(&p_session->log, kInfo,
           "Realtime audio start_address = 0x%x, stop_address = 0x%x, "
           "limit %d",
           p_session->dump_addresses[0], dump_end_address,
           p_session->dump_limit);

  return kRetOK_;
}

/**
 * @brief _CheckRequestRealtimeMode
 * Check if the requested realtime mode is acceptiable.
 *
 * @param p_session Session instance.
 * @param mode The requested realtime mode.
 *
 * @return kRetFail_, kRetOK_
 */
static int _CheckRequestRealtimeMode(Session *p_session, RealtimeMode mode)
{
  if (kStopWhenOverflow <= mode && mode <= kBestEffort) {
    return kRetOK_;
  }

  LogPrint(&p_session->log, kWarn, "Realtime mode %d is not acceptable", mode);

  _SendResponse(p_session, kArgument, strlen(kErrorMessageRealtimeMode),
                (char *)kErrorMessageRealtimeMode);

  return kRetFail_;
}

/**
 * @brief _GetCountDifference
 * This funciton calculate the difference between current count with the
 * hardware count of chameleon.
 * The hardware count always goes in advance.
 * So we use hw_count to subtract count to get difference.
 *
 * @param hw_count The count from chameleon.
 * @param count The count in this session.
 *
 * @return Difference between hardware count and software count.
 */
static int _GetCountDifference(int hw_count, int count)
{
  int difference;

  difference = hw_count - (count % kHW_CountWrap_);
  if (difference < 0) {
    difference += kHW_CountWrap_;
  }

  return difference;
}

/**
 * @brief _GetNextDumpCount
 * Get the next count of the next dump.
 * This function will check if we can dump in time.
 * If not, it will decide to drop data or stop dumping by the realtime_mode.
 *
 * @param p_session Session instance.
 * @param current_count The session's current count.
 * @param hw_count The count from chameleon.
 *
 * @return Next count, kRetFail_
 *         If next count is 0, means we will stop dumping process.
 */
static uint32_t _GetNextDumpCount(Session *p_session, uint32_t current_count,
                                  uint32_t hw_count)
{
  int difference;
  char buffer[128];
  char *p_error;

  difference = _GetCountDifference(hw_count, current_count);
  if (difference == 0) {
    return current_count;
  }
  // Overflow happens
  if (difference > p_session->dump_limit) {
    switch (p_session->realtime_mode) {
    case kStopWhenOverflow:
      LogPrint(&p_session->log, kWarn, (char *)kErrorMessageMemoryOverflow);
      if (_SendResponse(p_session,
                        p_session->is_dump_audio ? kAudioMemoryOverflowStop
                                                 : kVideoMemoryOverflowStop,
                        strlen(kErrorMessageMemoryOverflow),
                        (char *)kErrorMessageMemoryOverflow)) {
        return kRetFail_;
      }
      return 0;

    case kBestEffort:
      p_error =
          (char *)(p_session->is_dump_audio ? kErrorMessageDropAudioPage
                                            : kErrorMessageDropVideoFrame);
      sprintf(buffer, p_error, difference);
      LogPrint(&p_session->log, kWarn, buffer);
      if (_SendResponse(p_session,
                        p_session->is_dump_audio ? kAudioMemoryOverflowDrop
                                                 : kVideoMemoryOverflowDrop,
                        strlen(buffer), buffer)) {
        return kRetFail_;
      }
      // Drop frames, jump to the latest one.
      current_count += difference;
      break;

    default:
      LogPrint(&p_session->log, kError, "Can't reach here");
      return kRetFail_;
    }
  } else {
    current_count++;
  }

  return current_count;
}

/**
 * @brief _DoDumpRealtimeVideoFrame
 * Dump realtime video frame function.
 * This function will also receive the request message from client.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _DoDumpRealtimeVideoFrame(Session *p_session)
{
  /*
   * Use dedicated stack memory for the head.
   * So we can use socketbuffer to receive new messages.
   */
  VideoDataStreamHead head;
  VideoDataStream *p_data_head = &head.data_head;
  unsigned long unit_aligned_size;
  uint32_t frame_number, next_frame_number, hw_frame_count;
  int i;
  int poll_ret;
  struct pollfd ufds[1];

  ufds[0].fd = p_session->socket;
  ufds[0].events = POLLIN | POLLPRI;

  unit_aligned_size = p_session->unit_aligned_size;
  _InitDumpVideoHead(p_session, &head);

  frame_number = 0;
  while (1) {
    poll_ret = poll(ufds, 1, 0);
    if (poll_ret == -1) {
      perror("poll");
      return kRetFail_;
    } else if (poll_ret) {
      if (_ProcessMessage(p_session)) {
        LogPrint(&p_session->log, kError,
                 "Process message fail during dump realtime video");
        return kRetFail_;
      }
      if (!p_session->stop_dump) {
        /*
         * we may change the state variables during the _ProcessMessage,
         * So we reinit the video head here.
         */
        _InitDumpVideoHead(p_session, &head);
      }
    }

    if (p_session->stop_dump) {
      p_session->stop_dump = 0;
      return kRetOK_;
    }

    /*
     * We assume chameleon board can get new frame on both channels at the same
     * time. So only check the frame count of one channel.
     */
    hw_frame_count =
        ChameleonVideoGetFrameCount(p_session->realtime_check_channel);
    next_frame_number =
        _GetNextDumpCount(p_session, frame_number, hw_frame_count);
    if (next_frame_number == frame_number) {
      continue;
    }
    if (next_frame_number <= 0) {
      return next_frame_number;
    }

    p_data_head->frame_number = htonl(frame_number);
    i = frame_number % p_session->dump_limit;
    if (_DumpAllChannelVideoFrame(p_session, &head, i * unit_aligned_size)) {
      return kRetFail_;
    }

    frame_number = next_frame_number;
  }

  return kRetOK_;
}

/**
 * @brief _DoDumpRealtimeAudioPage
 * Dump realtime audio page function.
 * This function will also receive the request message from client.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _DoDumpRealtimeAudioPage(Session *p_session)
{
  /*
   * Use dedicated stack memory for the head.
   * So we can use socketbuffer to receive new messages.
   */
  AudioDataStreamHead head;
  AudioDataStream *p_data_head = &head.data_head;
  uint32_t page_count, next_page_count, hw_page_count;
  char *p_source, *p_dump_buffer;
  int i;
  int poll_ret;
  struct pollfd ufds[1];
  enum MessageType message_type;

  ufds[0].fd = p_session->socket;
  ufds[0].events = POLLIN | POLLPRI;

  _InitDumpAudioHead(p_session, &head);

  page_count = 0;
  p_source = p_session->p_mmap_sources[0];
  p_dump_buffer = p_session->p_dump_buffer;
  while (1) {
    poll_ret = poll(ufds, 1, 0);
    if (poll_ret == -1) {
      perror("poll");
      return kRetFail_;
    } else if (poll_ret) {
      /* backup message type */
      message_type = p_session->message_type;
      if (_ProcessMessage(p_session)) {
        LogPrint(&p_session->log, kError,
                 "Process message fail during dump realtime audio");
        return kRetFail_;
      }
      /* restore message type */
      p_session->message_type = message_type;
    }

    if (p_session->stop_dump) {
      p_session->stop_dump = 0;
      return kRetOK_;
    }

    hw_page_count = ChameleonAudioGetPageCount();
    next_page_count = _GetNextDumpCount(p_session, page_count, hw_page_count);
    if (next_page_count == page_count) {
      continue;
    }
    if (next_page_count <= 0) {
      return next_page_count;
    }

    p_data_head->page_count = htonl(page_count);
    i = page_count % p_session->dump_limit;
    if (_SendToSocket(p_session, (char *)&head, sizeof(AudioDataStreamHead))) {
      return kRetFail_;
    }
    memcpy(p_dump_buffer, p_source + i * kAudioPageSize_, kAudioPageSize_);
    if (_SendToSocket(p_session, p_dump_buffer, kAudioPageSize_)) {
      return kRetFail_;
    }
    page_count = next_page_count;
  }

  return kRetOK_;
}

static void _ResetSession(Session *p_session)
{
  p_session->screen_width = 0;
  p_session->screen_height = 0;
  p_session->is_shrink = 0;
  p_session->shrink_width = 0;
  p_session->shrink_height = 0;

  p_session->stop_dump = 0;
  p_session->is_dump_audio = 0;
  p_session->dump_limit = 0;

  p_session->realtime_mode = kNonRealtime;
}

/**
 * @brief _ProcessReset
 * Message handler of kReset.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessReset(Session *p_session)
{
  LogPrint(&p_session->log, kInfo, "Process Reset");

  /*
   * If we have realtime stream, we can't do reset thing.
   */
  if (_CheckRealtimeStream(p_session)) {
    return kRetFail_;
  }

  _ResetSession(p_session);

  return _SendResponse(p_session, kOK, 0, NULL);
}

/**
 * @brief _ProcessGetVersion
 * Message handler of kGetVersion.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessGetVersion(Session *p_session)
{
  GetVersionResponse response;

  LogPrint(&p_session->log, kInfo, "GetVersion %d.%d", kMajor, kMinor);

  // Send response back.
  response.major = kMajor;
  response.minor = kMinor;
  _InitResponseHead(p_session, kOK, sizeof(GetVersionResponse),
                    (char *)&response);
  return _SendWholePacketToSocket(p_session);
}

/**
 * @brief _ProcessConfigVideoStream
 * Message handler of kConfigVideoStream.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessConfigVideoStream(Session *p_session)
{
  ConfigVideoStreamRequest *p_request =
      (ConfigVideoStreamRequest *)p_session->socketbuffer;

  p_session->screen_width = ntohs(p_request->screen_width);
  p_session->screen_height = ntohs(p_request->screen_height);

  LogPrint(&p_session->log, kInfo,
           "ConfigVideoStreamRequest width %d, height %d",
           p_session->screen_width, p_session->screen_height);

  return _SendResponse(p_session, kOK, 0, NULL);
}

/**
 * @brief _ProcessConfigShrinkVideoStream
 * Message handler of kConfigShrinkVideoStream.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessConfigShrinkVideoStream(Session *p_session)
{
  ConfigShrinkVideoStreamRequest *p_request =
      (ConfigShrinkVideoStreamRequest *)p_session->socketbuffer;

  p_session->shrink_width = p_request->shrink_width;
  p_session->shrink_height = p_request->shrink_height;

  p_session->is_shrink = p_session->shrink_width || p_session->shrink_height;
  LogPrint(&p_session->log, kInfo,
           "ConfigShrinkVideoStreamRequest shrink_width %u, shrink_height %u",
           p_session->shrink_width, p_session->shrink_height);

  return _SendResponse(p_session, kOK, 0, NULL);
}

/**
 * @brief _ProcessDumpVideoFrame
 * Message handler of kDumpVideoFrame.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessDumpVideoFrame(Session *p_session)
{
  DumpVideoFrameRequest *p_request =
      (DumpVideoFrameRequest *)p_session->socketbuffer;
  uint16_t number_of_frames;
  uint32_t memory_addresses[MAX_VIDEO_DUMP_CHANNEL];
  unsigned long frame_size, screen_width, screen_height;

  number_of_frames = ntohs(p_request->number_of_frames);
  memory_addresses[0] = ntohl(p_request->memory_address1);
  memory_addresses[1] = ntohl(p_request->memory_address2);

  LogPrint(&p_session->log, kInfo,
           "DumpVideoFrameRequest frames %d, memory1: 0x%x, memory2: 0x%x",
           number_of_frames, memory_addresses[0], memory_addresses[1]);

  screen_width = p_session->screen_width;
  screen_height = p_session->screen_height;
  frame_size = screen_width * screen_height * kBytePerPixel_;
  p_session->unit_aligned_size = _calculate_page_aligned_size(frame_size);

  p_session->dump_addresses[0] = memory_addresses[0];
  p_session->dump_addresses[1] = memory_addresses[1];

  if (number_of_frames == 0) {
    _SendResponse(p_session, kArgument, strlen(kErrorMessageFrameNumberZero),
                  (char *)kErrorMessageFrameNumberZero);
    return kRetFail_;
  }

  if (_PrepareDumpBuffer(p_session)) {
    return kRetFail_;
  }

  p_session->dump_limit = number_of_frames;
  if (_PrepareMMAP(p_session)) {
    return kRetFail_;
  }

  if (_SendResponse(p_session, kOK, 0, NULL)) {
    return kRetFail_;
  }

  if (_DoDumpVideoFrame(p_session, number_of_frames)) {
    return kRetFail_;
  }

  _CleanDumpVariable(p_session);
  return kRetOK_;
}

/**
 * @brief _ProcessDumpRealtimeVideoFrame
 * Message handler of kDumpRealtimeVideoFrame.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessDumpRealtimeVideoFrame(Session *p_session)
{
  DumpRealtimeVideoRequest *p_request =
      (DumpRealtimeVideoRequest *)p_session->socketbuffer;

  LogPrint(&p_session->log, kInfo, "DumpRealtimeVideo is_dual %d, mode %d",
           p_request->is_dual, p_request->mode);

  if (_CheckRealtimeStream(p_session)) {
    return kRetFail_;
  }

  if (_CheckRequestRealtimeMode(p_session, p_request->mode)) {
    return kRetFail_;
  }

  if (_GetRealtimeVideoParameters(p_session, p_request)) {
    return kRetFail_;
  }

  if (_PrepareDumpBuffer(p_session)) {
    return kRetFail_;
  }

  if (_PrepareMMAP(p_session)) {
    return kRetFail_;
  }

  if (_SendResponse(p_session, kOK, 0, NULL)) {
    return kRetFail_;
  }

  if (_DoDumpRealtimeVideoFrame(p_session)) {
    return kRetFail_;
  }

  _CleanDumpVariable(p_session);
  return kRetOK_;
}

/**
 * @brief _ProcessStopDump
 * Message handler of kStopDump.
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessStopDump(Session *p_session)
{
  LogPrint(&p_session->log, kInfo, "Process stop dump, current mode %d",
           p_session->realtime_mode);

  if (p_session->realtime_mode != kNonRealtime) {
    p_session->stop_dump = 1;
  }

  return _SendResponse(p_session, kOK, 0, NULL);
}

/**
 * @brief _ProcessDumpRealtimeAudioPage
 * Message handler of kDumpRealtimeAudioPage
 *
 * @param p_session Session instance.
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessDumpRealtimeAudioPage(Session *p_session)
{
  DumpRealtimeAudioRequest *p_request =
      (DumpRealtimeAudioRequest *)p_session->socketbuffer;

  LogPrint(&p_session->log, kInfo, "DumpRealtimeAudio");
  p_session->is_dump_audio = 1;

  if (_CheckRealtimeStream(p_session)) {
    return kRetFail_;
  }

  if (_CheckRequestRealtimeMode(p_session, p_request->mode)) {
    return kRetFail_;
  }

  if (_GetRealtimeAudioParameters(p_session, p_request)) {
    return kRetFail_;
  }

  if (_PrepareDumpBuffer(p_session)) {
    return kRetFail_;
  }

  if (_PrepareMMAP(p_session)) {
    return kRetFail_;
  }

  if (_SendResponse(p_session, kOK, 0, NULL)) {
    return kRetFail_;
  }

  if (_DoDumpRealtimeAudioPage(p_session)) {
    return kRetFail_;
  }

  _CleanDumpVariable(p_session);
  return kRetOK_;
}

/**
 * @brief _ProcessMessage
 * Main message process handler. It will read whole packet and dispatch to
 * related message handler by the message type.
 *
 * @param p_session Session instance
 *
 * @return kRetFail_, kRetOK_
 */
static int _ProcessMessage(Session *p_session)
{
  PacketHead *p_head = _get_packet_head(p_session);
  int type;
  int length;

  // Read packet common header
  if (_ReadFromSocket(p_session, sizeof(PacketHead))) {
    return kRetFail_;
  }
  type = ntohs(p_head->type);

  // Check main type, it only can has request type since it is a server.
  if ((type >> 8) != kRequest) {
    LogPrint(&p_session->log, kError, "Type Error 0x%x != 0x%x ", type >> 8,
             kRequest);
    return kRetFail_;
  }

  type = type & 0xFF;
  if (type >= kMaxMessageType) {
    LogPrint(&p_session->log, kError, "Type Error %d >= %d ", type,
             kMaxMessageType);
    return kRetFail_;
  }

  // read remain content.
  length = ntohl(p_head->length);
  if (length && _ReadFromSocket(p_session, length)) {
    return kRetFail_;
  }

  p_session->message_type = type;
  LogPrint(&p_session->log, kInfo, "Receive Type %d, length %d ", type, length);

  return _g_handlers[type](p_session);
}

void SessionEntry(int socket)
{
  Session *p_session = NULL;
  char log_path[kPathBufferSize];

  p_session = malloc(sizeof(Session));
  if (p_session == NULL) {
    perror("Can't allocate memory for session\n");
    goto function_exit;
  }
  memset(p_session, 0, sizeof(Session));

  p_session->socket = socket;

  /* Prepare log of this session */
  sprintf(log_path, kSessionLogfilePattern_, socket);
  if (LogInit(&p_session->log, log_path)) {
    goto function_exit;
  }

  /* Prepare /dev/mem */
  p_session->dev_mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
  if (p_session->dev_mem_fd == -1) {
    perror("can't open /dev/mem\n");
    LogPrint(&p_session->log, kError, "Can't open /dev/mem");
    goto function_exit;
  }

  _ResetSession(p_session);

  LogPrint(&p_session->log, kDebug, "Session %d start", socket);

  /* The main loop of the session. */
  while (1) {
    if (_ProcessMessage(p_session)) {
      LogPrint(&p_session->log, kError, "Process message %d fail",
               p_session->message_type);
      break;
    }
  }

function_exit:

  if (p_session) {
    _CleanSession(p_session);
    free(p_session);
  }
  close(socket);
}
