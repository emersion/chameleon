/* Copyright 2016 The Chromium OS Authors. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */
#ifndef LOG_H_
#define LOG_H_

#include <stdio.h>

#define kPathBufferSize 128

typedef struct {
  FILE *p_file;
  char path[kPathBufferSize];
} LogHandle;

typedef enum {
  kDebug = 0,
  kInfo = 1,
  kWarn = 2,
  kError = 3,
} LogLevel;

/**
 * @brief LogInit
 * Init the log handle.
 * The log handle memory is from caller.
 *
 * @param p_handle LogHandle instance
 * @param path Relative log path
 *
 * @return 0 - Success
 *         not 0 - error happens.
 */
int LogInit(LogHandle *p_handle, char *path);

/**
 * @brief LogDestroy
 * Destroy the log instance.
 *
 * @param p_handle LogHandle instance.
 *
 * @return 0 - Success
 *         not 0 - error happens.
 */
int LogDestroy(LogHandle *p_handle);

/**
 * @brief LogPrint
 * Print log to log file.
 *
 * @param p_handle LogHandle instance.
 * @param level LogLevel of this log.
 * @param message log message. We can use the format as printf.
 * @param ... variable arguments.
 */
void LogPrint(LogHandle *p_handle, LogLevel level, char *message, ...);

/**
 * @brief LogSetLevel
 * Set log level filter globally.
 *
 * @param level enum log_level type
 */
void LogSetLevel(LogLevel level);

#endif // LOG_H_
