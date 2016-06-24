// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
#ifndef SESSION_H_
#define SESSION_H_

/**
 * @brief SessionEntry
 * The client TCP session main entry function.
 *
 * @param socket client socket
 */
void SessionEntry(int socket);

#endif // SESSION_H_
