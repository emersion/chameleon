// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "log.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

/*
 * Turn on it to debug program crash.
 * In this situation, the log may not be flushed to log file.
 */
#define OUTPUT_STDERR_ 0

/*
 * The log root path.
 */
static const char *kRoot_ = "/var/log/";

/*
 * The index of the string must be matched to the LogLevel value.
 */
static const char *kLogLevelString_[] = {
    "[D] ", "[I] ", "[W] ", "[E] ",
};

static LogLevel g_level_ = kDebug;

void LogPrint(LogHandle *p_handle, LogLevel level, char *message, ...)
{
  struct tm *p_tm;
  struct timeval tv;
  char date_string[64];
  va_list args;

  if (level < g_level_) {
    return;
  }
  gettimeofday(&tv, NULL);
  p_tm = localtime(&tv.tv_sec);

  /*
   * Time format
   * 2015-08-05 09:12:44
   * We will output usec later, since strftime of C doesn't support it.
   */
  strftime(date_string, 64, "%Y-%m-%d %H:%M:%S", p_tm);
  va_start(args, message);

  /* output time 2015-08-05 09:12:44.xxxxxx */
  fprintf(p_handle->p_file, "%s.%06lu", date_string, tv.tv_usec);
  fprintf(p_handle->p_file, kLogLevelString_[level]);
  vfprintf(p_handle->p_file, message, args);
  fprintf(p_handle->p_file, "\n");
  /*
   * Flush buffered data to file, otherwise we may not see the log until stop
   * the server.
   */
  fflush(p_handle->p_file);

#if OUTPUT_STDERR_
  fprintf(stderr, "%s", date_string);
  fprintf(stderr, kLogLevelString_[level]);
  vfprintf(stderr, message, args);
  fprintf(stderr, "\n");
#endif

  va_end(args);
}

int LogInit(LogHandle *p_handle, char *path)
{
  /* Check if full_path space is enough */
  if (strlen(kRoot_) + strlen(path) >= kPathBufferSize) {
    return -1;
  }

  /* Clear handle first */
  memset(p_handle, 0, sizeof(LogHandle));

  strcpy(p_handle->path, kRoot_);
  strcat(p_handle->path, path);
  p_handle->p_file = fopen(p_handle->path, "a");
  if (p_handle->p_file == NULL) {
    perror("LogInit");
    return -1;
  }

  return 0;
}

int LogDestroy(LogHandle *p_handle)
{
  int error;

  if (p_handle->p_file) {
    error = fclose(p_handle->p_file);
    if (error) {
      perror("LogDestroy");
    }
  }

  return error;
}

void LogSetLevel(LogLevel level)
{
  g_level_ = level;
}
