#include <getopt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "daq_alert.h"

static void usage(const char *prog, FILE *out)
{
    fprintf(out,
        "Usage: %s [OPTIONS]\n"
        "\n"
        "Send a Mu2e DAQ alert via UDP broadcast using the C library.\n"
        "\n"
        "Options:\n"
        "  -s, --system-id ID    System identifier  (default: DAQ-NODE-01)\n"
        "  -m, --message TEXT    Alert message text  (default: Test alert from example-sender-c)\n"
        "  -i, --ip ADDRESS      Broadcast IP address (default: 255.255.255.255)\n"
        "  -p, --port NUM        UDP port             (default: 37020)\n"
        "  -h, --help            Show this help and exit\n",
        prog);
}

int main(int argc, char *argv[])
{
    const char *system_id    = "DAQ-NODE-01";
    const char *message      = "Test alert from example-sender-c";
    const char *broadcast_ip = DAQ_ALERT_BROADCAST_IP;
    int         port         = DAQ_ALERT_PORT;

    static const struct option long_opts[] = {
        {"system-id", required_argument, NULL, 's'},
        {"message",   required_argument, NULL, 'm'},
        {"ip",        required_argument, NULL, 'i'},
        {"port",      required_argument, NULL, 'p'},
        {"help",      no_argument,       NULL, 'h'},
        {NULL, 0, NULL, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "s:m:i:p:h", long_opts, NULL)) != -1) {
        switch (opt) {
            case 's': system_id    = optarg; break;
            case 'm': message      = optarg; break;
            case 'i': broadcast_ip = optarg; break;
            case 'p': {
                char *end;
                long v = strtol(optarg, &end, 10);
                if (*end != '\0' || v < 1 || v > 65535) {
                    fprintf(stderr, "error: invalid port '%s'\n", optarg);
                    return 1;
                }
                port = (int)v;
                break;
            }
            case 'h':
                usage(argv[0], stdout);
                return 0;
            default:
                usage(argv[0], stderr);
                return 1;
        }
    }

    printf("Sending alert to %s:%d\n", broadcast_ip, port);
    printf("  system_id : %s\n", system_id);
    printf("  message   : %s\n", message);

    DaqAlertResult rc = daq_alert_send(system_id, message, broadcast_ip, (uint16_t)port);
    if (rc != DAQ_ALERT_OK) {
        fprintf(stderr, "error: %s\n", daq_alert_strerror(rc));
        return 1;
    }

    puts("Alert sent.");
    return 0;
}
