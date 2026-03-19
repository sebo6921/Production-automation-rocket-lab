#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include <arpa/inet.h>
#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/udp.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef __USE_MISC
struct ip_mreq
  {
    /* IP multicast address of group.  */
    struct in_addr imr_multiaddr;

    /* Local IP address of interface.  */
    struct in_addr imr_interface;
};
#endif

#define DEFAULT_MCAST_GROUP "224.3.11.15"
#define DEFAULT_MCAST_PORT  31115
#define DEFAULT_LISTEN_ADDR "0.0.0.0"
#define DEFAULT_LISTEN_PORT 0

#define MAXKVPAIRS 4
#define MAXREQSZ   512
#define MAXREPLYSZ 256

// The specification doesn't specify the format of the values, here we assume
// that they are floats, but you could change this to be MV=%.0lf for ints.
#define STATUS_FORMAT "STATUS;TIME=%.0lf;MV=%.1lf;MA=%.1lf;"

// Similarly, some candidates assume that model and serial are integers but
// in "the real world" these are usually (semi-)numeric strings, not numbers.
#define DEFAULT_MODEL_NUMBER  "M001"
#define DEFAULT_SERIAL_NUMBER "SN0123456"

#define DEFAULT_DUT_MV 4500.0
#define DEFAULT_DUT_MA 100.0

static volatile int g_keep_running = 1;

static void sighandler_done(int sig) { g_keep_running = 0; }

typedef enum {
  ERR = 0,
  OK = 1,
} result_t;

typedef enum {
  UNKNOWN = 0,
  ID = 1,
  TEST = 2,
} command_t;

typedef enum {
  IDLE = 0,
  RUNNING = 1,
} state_t;

typedef struct {
  int verbosity;
  char *mcast_addr;
  uint16_t mcast_port;
  char *listen_addr;
  uint16_t listen_port;
  char *modelnum;
  char *serialnum;
  double initial_dut_mv;
  double initial_dut_ma;
  bool deterministic;
} config_t;

typedef struct {
  double t0;
  double duration_s;
  double rate_ms;
  double next_update_s;
  double dut_mv;
  double dut_ma;
} test_t;

typedef struct {
  int verbosity;
  int mcast_fd;
  int fd;
  char *modelnum;
  char *serialnum;
  double initial_dut_mv;
  double initial_dut_ma;
  bool deterministic;
  state_t state;
  test_t test;
  struct sockaddr_in subscriber;
} app_t;

typedef struct {
  command_t cmd;
  size_t nargs;
  char *argkeys[MAXKVPAIRS];
  char *argvals[MAXKVPAIRS];
} request_t;

double get_timestamp(void) {
  struct timeval now;
  gettimeofday(&now, NULL);
  return ((double)now.tv_sec) + (((double)now.tv_usec) / 1e6);
}

result_t format_reply(char *response, size_t *rlen, const char *msg, ...) {
  va_list ap;

  va_start(ap, msg);
  vsprintf(response, msg, ap);
  va_end(ap);

  *rlen = strlen(response);

  return OK;
}

result_t send_message(app_t *app, char *buf, size_t n) {
  if (app->verbosity > 1) {
    printf("debug: send_message \"%s\"\n", buf);
  }

  if (buf == NULL) {
    return OK;
  }

  if (app->subscriber.sin_port != 0) {
    sendto(app->fd, buf, n, 0, (struct sockaddr *)&app->subscriber, sizeof(app->subscriber));
  }
  return OK;
}

result_t parse_command(request_t *req, char *buf, size_t n) {
  char *tok, *subtok;
  char *savep = NULL, *save2p = NULL;
  char *s1 = buf, *s2 = NULL;

  memset(req, 0, sizeof(*req));

  tok = strtok_r(s1, ";", &savep);
  if (tok == NULL) {
    return ERR;
  }

  if (strcmp(tok, "ID") == 0) {
    req->cmd = ID;
  } else if (strcmp(tok, "TEST") == 0) {
    req->cmd = TEST;
  } else {
    req->cmd = UNKNOWN;
    return OK;
  }

  s1 = NULL;
  subtok = NULL;
  while (1) {
    tok = strtok_r(s1, ";", &savep);
    if (tok == NULL) {
      break;
    } else if (req->nargs >= MAXKVPAIRS) {
      return ERR;
    }

    s2 = tok;
    subtok = strtok_r(s2, "=", &save2p);
    if (subtok == NULL) {
      break;
    }
    req->argkeys[req->nargs] = subtok;
    subtok = strtok_r(NULL, "=", &save2p);
    if (subtok == NULL) {
      break;
    }
    req->argvals[req->nargs] = subtok;
    req->nargs++;
  }

  return OK;
}

result_t handle_ID(app_t *app, const request_t req, char *response, size_t *rlen) {
  if (app->verbosity > 1) {
    printf("debug: ID cmd=%d nargs=%zd\n", req.cmd, req.nargs);
    for (size_t i = 0; i < req.nargs; i++) {
      printf("debug: ID arg[%zd] = { \"%s\": \"%s\" }\n", i, req.argkeys[i], req.argvals[i]);
    }
  }

  if (req.nargs == 0) {
    return format_reply(response, rlen, "ID;MODEL=%s;SERIAL=%s;", app->modelnum, app->serialnum);
  } else {
    return format_reply(response, rlen, "ERR;REASON=Unexpected argument to ID;");
  }
}

result_t handle_TEST_START(app_t *app, const request_t req, char *response, size_t *rlen) {
  // "TEST;CMD=START;DURATION=s;RATE=ms;"
  if (req.nargs != 3) {
    return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=\"CMD=START\" expects DURATION and RATE;");
  }

  double duration = 0.0;
  double rate = 0.0;

  for (size_t i = 1; i < 3; i++) {
    if (strcmp(req.argkeys[i], "DURATION") == 0) {
      if (sscanf(req.argvals[i], "%lf", &duration) != 1) {
        return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=Could not parse DURATION;");
      }
    } else if (strcmp(req.argkeys[i], "RATE") == 0) {
      if (sscanf(req.argvals[i], "%lf", &rate) != 1) {
        return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=Could not parse RATE;");
      }
    }
  }

  if (duration == 0.0 || rate == 0.0) {
    return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=Expected duration>0 and rate>0;");
  }

  if (app->state == IDLE) {
    double now = get_timestamp();
    app->state = RUNNING;
    app->test.t0 = now;
    app->test.duration_s = duration;
    app->test.next_update_s = now + ((double)rate / 1000.0);
    app->test.rate_ms = rate;
    app->test.dut_ma = app->initial_dut_ma;
    app->test.dut_mv = app->initial_dut_mv;
    printf("info: TEST STARTED t0=%.6lf next_update_s=%.6lf duration_s=%.2lf rate_ms=%.0lf\n", app->test.t0,
           app->test.next_update_s, app->test.duration_s, app->test.rate_ms);
    return format_reply(response, rlen, "TEST;RESULT=STARTED;");
  } else {
    return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=Already running;");
  }
}

result_t handle_TEST_STOP(app_t *app, const request_t req, char *response, size_t *rlen) {
  // "TEST;CMD=STOP;"
  if (app->state == RUNNING) {
    app->state = IDLE;
    // Not really needed:
    app->test.t0 = 0.0;
    app->test.duration_s = 0.0;
    app->test.next_update_s = 0.0;
    app->test.rate_ms = 0.0;
    app->test.dut_ma = 0.0;
    app->test.dut_mv = 0.0;
    printf("info: TEST STOPPED by user request\n");
    return format_reply(response, rlen, "TEST;RESULT=STOPPED;");
  } else {
    return format_reply(response, rlen, "TEST;RESULT=ERROR;MSG=No test was running;");
  }
}

result_t handle_TEST(app_t *app, const request_t req, char *response, size_t *rlen) {
  if (app->verbosity > 1) {
    printf("debug: TEST cmd=%d nargs=%zd\n", req.cmd, req.nargs);
    for (size_t i = 0; i < req.nargs; i++) {
      printf("debug: TEST arg[%zd] = { \"%s\": \"%s\" }\n", i, req.argkeys[i], req.argvals[i]);
    }
  }

  if (req.nargs < 1) {
    return format_reply(response, rlen, "ERR;REASON=Missing CMD argument to TEST;");
  }

  const char *subcmd = req.argvals[0];

  if (strcmp(req.argkeys[0], "CMD") != 0) {
    return format_reply(response, rlen, "ERR;REASON=Expected first argument to be CMD;");
  } else if (strcmp(subcmd, "START") == 0) {
    return handle_TEST_START(app, req, response, rlen);
  } else if (strcmp(subcmd, "STOP") == 0) {
    return handle_TEST_STOP(app, req, response, rlen);
  } else {
    return format_reply(response, rlen, "ERR;REASON=Unknown CMD expected START or STOP;");
  }
}

ssize_t update_subscribers(app_t *app, struct sockaddr_in *raddr) {
  memcpy(&app->subscriber, raddr, sizeof(app->subscriber));
  return 0;
}

result_t handle_message(app_t *app, struct sockaddr_in *raddr, char *buf, size_t n, command_t supported_commands) {
  buf[n] = 0x0;

  if (app->verbosity) {
    printf("debug: handle_message %s:%d %zd \"%s\"\n", inet_ntoa(raddr->sin_addr), ntohs(raddr->sin_port), n, buf);
  }

  if (update_subscribers(app, raddr) < 0) {
    fprintf(stderr, "warn: too many subscribers, dropping %s:%d\n", inet_ntoa(raddr->sin_addr), ntohs(raddr->sin_port));
    return ERR;
  }

  if (app->verbosity > 1) {
    printf("debug: subscriber is now %s:%d\n", inet_ntoa(app->subscriber.sin_addr), ntohs(app->subscriber.sin_port));
  }

  request_t cmd;
  if (!parse_command(&cmd, buf, n)) {
    if (app->verbosity) {
      fprintf(stderr, "debug: could not parse command \"%s\"\n", buf);
    }
    return ERR;
  }

  char response[MAXREPLYSZ] = {0};
  size_t rlen = 0;
  result_t ok = ERR;

  switch (cmd.cmd & supported_commands) {
  case ID:
    ok = handle_ID(app, cmd, (char *)&response, &rlen);
    break;
  case TEST:
    ok = handle_TEST(app, cmd, (char *)&response, &rlen);
    break;
  default:
    ok = format_reply((char *)&response, &rlen, "ERR;REASON=Bad message format;");
    break;
  }

  if (ok) {
    if (app->verbosity) {
      printf("debug: sendto %s:%hu \"%s\"\n", inet_ntoa(raddr->sin_addr), ntohs(raddr->sin_port), response);
    }
    sendto(app->fd, response, rlen, 0, (struct sockaddr *)raddr, sizeof(*raddr));
  } else if (!ok) {
    fprintf(stderr, "error: could not process command \"%s\"\n", buf);
  }

  return OK;
}

result_t bind_multicast(const config_t *cfg, app_t *app) {
  struct addrinfo *addresses = NULL, *ai = NULL;
  struct addrinfo hints = {
      .ai_family = AF_INET,
      .ai_socktype = SOCK_DGRAM,
      .ai_protocol = IPPROTO_UDP,
      .ai_flags = AI_PASSIVE,
  };

  char portnum[16];
  snprintf(portnum, 16, "%" PRIu16, cfg->mcast_port);

  int rc;
  if ((rc = getaddrinfo(cfg->listen_addr, portnum, &hints, &addresses)) != 0) {
    fprintf(stderr, "bind_server: %s\n", gai_strerror(rc));
    return ERR;
  }

  int yes = 1;
  int fd = -1;
  for (ai = addresses; ai != NULL; ai = ai->ai_next) {
    fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    if (fd == -1) {
      continue;
    }

    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes)) < 0) {
      perror("setsockopt: SO_REUSEADDR");
      close(fd);
      continue;
    }

    if (bind(fd, ai->ai_addr, ai->ai_addrlen) == -1) {
      perror("bind");
      close(fd);
      continue;
    }

    break; // bind was successful
  }

  freeaddrinfo(addresses);

  if (ai == NULL) {
    return ERR;
  }

  struct ip_mreq mreq = {
      .imr_multiaddr = {.s_addr = inet_addr(cfg->mcast_addr)},
      .imr_interface = {.s_addr = INADDR_ANY},
  };
  if (setsockopt(fd, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq)) < 0) {
    perror("setsockopt: IP_ADD_MEMBERSHIP");
    close(fd);
    return ERR;
  }

  if (setsockopt(fd, IPPROTO_IP, IP_MULTICAST_LOOP, &yes, sizeof(yes)) < 0) {
    perror("setsockopt: IP_MULTICAST_LOOP");
    close(fd);
    return ERR;
  }

  app->mcast_fd = fd;
  return OK;
}

result_t bind_server(const config_t *cfg, app_t *app) {
  struct addrinfo *addresses = NULL, *ai = NULL;
  struct addrinfo hints = {
      .ai_family = AF_INET,
      .ai_socktype = SOCK_DGRAM,
      .ai_flags = AI_PASSIVE,
  };

  char portnum[16];
  snprintf(portnum, 16, "%" PRIu16, cfg->listen_port);

  int rc;
  if ((rc = getaddrinfo(cfg->listen_addr, portnum, &hints, &addresses)) != 0) {
    fprintf(stderr, "bind_server: %s\n", gai_strerror(rc));
    return ERR;
  }

  int fd = -1;
  for (ai = addresses; ai != NULL; ai = ai->ai_next) {
    fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    if (fd == -1) {
      continue;
    }

    int optval = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval)) < 0) {
      perror("setsockopt");
      close(fd);
      continue;
    }

    if (bind(fd, ai->ai_addr, ai->ai_addrlen) == -1) {
      perror("bind");
      close(fd);
      continue;
    }

    break; // bind was successful
  }

  freeaddrinfo(addresses);

  if (ai == NULL) {
    return ERR;
  }

  app->fd = fd;
  return OK;
}

result_t mainloop_init(const config_t *cfg, app_t *app) {
  memset(app, 0, sizeof(*app));

  app->verbosity = cfg->verbosity;
  app->modelnum = cfg->modelnum;
  app->serialnum = cfg->serialnum;
  app->initial_dut_mv = cfg->initial_dut_mv;
  app->initial_dut_ma = cfg->initial_dut_ma;
  app->deterministic = cfg->deterministic;

  if (!bind_multicast(cfg, app)) {
    fprintf(stderr, "error: could not init multicast socket\n");
    return ERR;
  }

  if (!bind_server(cfg, app)) {
    fprintf(stderr, "error: could not bind server socket\n");
    return ERR;
  }

  struct sockaddr_storage addr;
  socklen_t addrlen = sizeof(addr);
  if (getsockname(app->fd, (struct sockaddr *)&addr, &addrlen) < 0) {
    perror("getsockname");
  }

  printf("info: device %s:%s listening on %s:%hu\n", app->modelnum, app->serialnum,
         inet_ntoa(((struct sockaddr_in *)&addr)->sin_addr), ntohs(((struct sockaddr_in *)&addr)->sin_port));

  return OK;
}

result_t mainloop_run(app_t *app) {
  char buf[MAXREQSZ];
  struct sockaddr_in addr;
  socklen_t addrlen = sizeof(addr);

  // process incoming commands/subscriptions
  const size_t nfds = 2;
  struct pollfd pfd[] = {
      {.fd = app->mcast_fd, .events = POLLIN | POLLHUP, .revents = 0},
      {.fd = app->fd, .events = POLLIN | POLLHUP, .revents = 0},
  };

  if (poll(pfd, nfds, 0) < 0) {
    if (errno != EINTR) {
      perror("poll");
    }
    return ERR;
  }

  for (size_t i = 0; i < nfds; ++i) {
    if (pfd[i].revents & POLLIN) {
      const ssize_t n = recvfrom(pfd[i].fd, buf, sizeof(buf), 0, (struct sockaddr *)&addr, &addrlen);
      if (n < 0) {
        fprintf(stderr, "warn: RX from %s:%d: %ld (%s)\n", inet_ntoa(addr.sin_addr), ntohs(addr.sin_port), n,
                strerror(errno));
      } else {
        if (pfd[i].fd == app->mcast_fd) {
          handle_message(app, &addr, buf, n, ID);
        } else {
          handle_message(app, &addr, buf, n, ID | TEST);
        }
      }
    }
  }

  result_t ok = OK;

  // process outgoing messages
  if (app->state == RUNNING) {
    char response[MAXREPLYSZ] = {0};
    size_t rlen = 0;

    const double now = get_timestamp();
    const double delta_t = (now - app->test.t0) < 0.0 ? 0.0 : (now - app->test.t0);

    if (now > app->test.next_update_s) {
      double time_ms = delta_t * 1000.0;
      if (!app->deterministic) {
        const double subsecond_part = ((int)(delta_t * 1000000) % 1000000) / 1e6;
        app->test.dut_mv += 56.789 * (subsecond_part - 0.5);
        app->test.dut_ma += 123.45 * (subsecond_part - 0.5);
      }
      ok = format_reply((char *)&response, &rlen, STATUS_FORMAT, time_ms, app->test.dut_mv, app->test.dut_ma);
      send_message(app, response, rlen);
      if (app->test.next_update_s == 0.0) {
        app->test.next_update_s = now;
      }
      app->test.next_update_s += (app->test.rate_ms / 1000.0);
      if (app->verbosity) {
        printf("debug: update, now=%lf next_update=%lf\n", now, app->test.next_update_s);
      }
    }

    if (delta_t > app->test.duration_s) {
      app->state = IDLE;
      ok = format_reply((char *)&response, &rlen, "STATUS;STATE=IDLE;");
      send_message(app, response, rlen);
      printf("info: TEST STOPPED by duration timeout\n");
    }
  }

  return ok;
}

void mainloop_stop(app_t *app) {
  if (app->fd) {
    close(app->fd);
  }
  if (app->mcast_fd) {
    close(app->mcast_fd);
  }
}

void usage(const char *errmsg, ...) {
  fprintf(stderr, "Usage: device [-H HOST] [-P PORT]\n");
  fprintf(stderr, "\nOptions:\n");
  fprintf(stderr, "  -H, --host <host>  Hostname/IP to bind (default: %s)\n", DEFAULT_LISTEN_ADDR);
  fprintf(stderr, "  -P, --port <u16>   UDP port to bind (default: %hu)\n", DEFAULT_LISTEN_PORT);
  fprintf(stderr, "  -M, --model <str>  Model number (default: %s)\n", DEFAULT_MODEL_NUMBER);
  fprintf(stderr, "  -S, --serial <str> Serial number (default: %s)\n", DEFAULT_SERIAL_NUMBER);
  fprintf(stderr, "  --mcast-addr <ip>  IP for multicast group to join (default: %s)\n", DEFAULT_MCAST_GROUP);
  fprintf(stderr, "  --mcast-port <u16> UDP port for multicast socket (default: %hu)\n", DEFAULT_MCAST_PORT);
  fprintf(stderr, "  --mv <float>       DUT reported mV (default: %lf)\n", DEFAULT_DUT_MV);
  fprintf(stderr, "  --ma <float>       DUT reported mA (default: %lf)\n", DEFAULT_DUT_MA);
  fprintf(stderr, "  --deterministic    Remove DUT mV/mA randomness (default: false)\n");
  fprintf(stderr, "  -v, --verbose      Debug logging\n");
  fprintf(stderr, "  -h, --help         Show this help text\n");

  if (errmsg) {
    va_list ap;
    fprintf(stderr, "\n");
    va_start(ap, errmsg);
    vfprintf(stderr, errmsg, ap);
    va_end(ap);
    exit(2);
  }

  exit(0);
}

void init_defaults(config_t *cfg) {
  memset(cfg, 0, sizeof(*cfg));
  cfg->mcast_addr = DEFAULT_MCAST_GROUP;
  cfg->mcast_port = DEFAULT_MCAST_PORT;
  cfg->listen_addr = DEFAULT_LISTEN_ADDR;
  cfg->listen_port = DEFAULT_LISTEN_PORT;
  cfg->modelnum = DEFAULT_MODEL_NUMBER;
  cfg->serialnum = DEFAULT_SERIAL_NUMBER;
  cfg->initial_dut_mv = DEFAULT_DUT_MV;
  cfg->initial_dut_ma = DEFAULT_DUT_MA;
  cfg->deterministic = false;
}

void parse_args(config_t *cfg, int argc, char *argv[]) {
  int opt;
  const char *shopts = ":hvM:S:H:P:";
  struct option longopts[] = {
      {"mcast-addr", required_argument, NULL, 0},
      {"mcast-port", required_argument, NULL, 1},
      {"mv", required_argument, NULL, 2},
      {"ma", required_argument, NULL, 3},
      {"deterministic", no_argument, NULL, 4},
      {"model", required_argument, NULL, 'M'},
      {"serial", required_argument, NULL, 'S'},
      {"host", required_argument, NULL, 'H'},
      {"port", required_argument, NULL, 'P'},
      {"help", no_argument, NULL, 'h'},
      {"verbose", no_argument, NULL, 'v'},
      {0},
  };

  opterr = 0;
  while ((opt = getopt_long(argc, argv, shopts, longopts, NULL)) != EOF) {
    switch (opt) {
    case 0:
      cfg->mcast_addr = optarg;
      break;

    case 1:
      if (sscanf(optarg, "%" SCNu16, &cfg->mcast_port) != 1) {
        usage("error: unable to parse port '%s'\n", optarg);
      }
      break;

    case 2:
      if (sscanf(optarg, "%lf", &cfg->initial_dut_mv) != 1) {
        usage("error: unable to float '%s'\n", optarg);
      }
      break;

    case 3:
      if (sscanf(optarg, "%lf", &cfg->initial_dut_ma) != 1) {
        usage("error: unable to float '%s'\n", optarg);
      }
      break;

    case 4:
      cfg->deterministic = true;
      break;

    case 'M':
      cfg->modelnum = optarg;
      break;

    case 'S':
      cfg->serialnum = optarg;
      break;

    case 'H':
      cfg->listen_addr = optarg;
      break;

    case 'P':
      if (sscanf(optarg, "%" SCNu16, &cfg->listen_port) != 1) {
        usage("error: unable to parse port '%s'\n", optarg);
      }
      break;

    case 'v':
      cfg->verbosity++;
      break;

    case 'h':
      usage(NULL);
      break;

    case ':':
      usage("error: missing required argument for option '%s'\n", argv[optind - 1]);
      break;

    case '?':
    default:
      usage("error: unknown option '%s'\n", argv[optind - 1]);
      break;
    }
  }
}

int main(int argc, char *argv[]) {
  const struct timespec delay = {
      .tv_sec = 0,
      .tv_nsec = 100000,
  };
  config_t cfg;
  app_t app;

  signal(SIGINT, sighandler_done);
  signal(SIGTERM, sighandler_done);

  init_defaults(&cfg);
  parse_args(&cfg, argc, argv);

  if (cfg.verbosity) {
    printf("debug: cfg.verbosity=%d\n", cfg.verbosity);
    printf("debug: cfg.mcast_addr=\"%s\"\n", cfg.mcast_addr);
    printf("debug: cfg.mcast_port=%hu\n", cfg.mcast_port);
    printf("debug: cfg.listen_addr=\"%s\"\n", cfg.listen_addr);
    printf("debug: cfg.listen_port=%hu\n", cfg.listen_port);
    printf("debug: cfg.modelnum=\"%s\"\n", cfg.modelnum);
    printf("debug: cfg.serialnum=\"%s\"\n", cfg.serialnum);
    printf("debug: cfg.initial_dut_mv=%lf\n", cfg.initial_dut_mv);
    printf("debug: cfg.initial_dut_ma=%lf\"\n", cfg.initial_dut_ma);
  }

  if (!mainloop_init(&cfg, &app)) {
    exit(1);
  }

  while (g_keep_running) {
    if (!mainloop_run(&app)) {
      break;
    }
    nanosleep(&delay, NULL);
  }

  mainloop_stop(&app);

  return 0;
}
