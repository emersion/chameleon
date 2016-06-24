// Copyright 2016 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/* Chameleon Board socket server
 *
 * This is TCP socket server running on Chameleon board to dump the
 * audio/video data.
 */

#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "chameleon_driver.h"
#include "log.h"
#include "session.h"

static const char *kServerLogfile_ = "stream_server.log";
static char *g_prog_ = NULL;
static LogHandle g_log_;
static int g_socket_;

static void _error(const char *msg)
{
  perror(msg);
  exit(1);
}

static void _usage_exit(void)
{
  fprintf(stderr, "Usage:\t%s port\n"
                  "Stream Server for dumping audio/video data.\n",
          g_prog_);
  exit(1);
}

static int _init_server_socket(int port)
{
  int sockfd;
  int sock_opt = 1;
  struct sockaddr_in serv_addr;

  sockfd = socket(AF_INET, SOCK_STREAM, 0);
  if (sockfd < 0)
    _error("ERROR opening socket");
  /* SET SOCKET REUSE Address
   * so we can reuse the same port when we leave program unexpectedly.
   */
  if (setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (void *)&sock_opt,
                 sizeof(sock_opt)) == -1) {
    _error("setsockopt fail");
  }

  bzero((char *)&serv_addr, sizeof(serv_addr));
  serv_addr.sin_family = AF_INET;
  serv_addr.sin_addr.s_addr = INADDR_ANY;
  serv_addr.sin_port = htons(port);
  if (bind(sockfd, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0)
    _error("ERROR on binding");

  return sockfd;
}

static int _accept_client(int sockfd)
{
  int client_sockfd;
  socklen_t clilen;
  struct sockaddr_in cli_addr;

  clilen = sizeof(cli_addr);
  client_sockfd = accept(sockfd, (struct sockaddr *)&cli_addr, &clilen);
  if (client_sockfd < 0)
    _error("ERROR on accept");
  LogPrint(&g_log_, kInfo, "Client from %s:%d, session %d",
           inet_ntoa(cli_addr.sin_addr), cli_addr.sin_port, client_sockfd);

  return client_sockfd;
}

/**
 * @brief thread_function
 * wrap function to call SessionEntry.
 * It will pass client socket to the SessionEntry
 *
 * @param argument client socket.
 *
 * @return dummy 0.
 */
static void *_thread_function(void *argument)
{
  SessionEntry((int)argument);

  return 0;
}

static void _exit_server(void)
{
  ChameleonDestroy();
  LogDestroy(&g_log_);
  close(g_socket_);
  exit(0);
}

static void _signal_handler(int sig)
{
  _exit_server();
}

int main(int argc, char **argv)
{
  int client_sock, port;
  pthread_t thread_id;

  g_prog_ = argv[0];
  if (argc < 2) {
    fprintf(stderr, "ERROR, no port provided\n");
    _usage_exit();
  }

  if (signal(SIGINT, _signal_handler) == SIG_ERR) {
    fprintf(stderr, "can't catch SIGINT\n");
    return -1;
  }

  if (LogInit(&g_log_, (char *)kServerLogfile_)) {
    fprintf(stderr, "ERROR, init log fail\n");
    return -1;
  }

  port = atoi(argv[1]);
  LogPrint(&g_log_, kInfo, "Start Stream Server with port %d", port);

  g_socket_ = _init_server_socket(port);

  /*
   * Support one audio and one video requests at the same time without client
   * handling retry.
   */
  listen(g_socket_, 2);

  ChameleonInit();

  // Server Loop
  while (1) {
    client_sock = _accept_client(g_socket_);

    if (pthread_create(&thread_id, NULL, _thread_function,
                       (void *)client_sock) < 0) {
      perror("could not create thread");
      LogPrint(&g_log_, kWarn, "could not create thread for socket %d",
               client_sock);
      close(client_sock);
    }
  }

  _exit_server();
  return 0;
}
