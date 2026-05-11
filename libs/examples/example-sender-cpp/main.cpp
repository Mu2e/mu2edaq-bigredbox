#include <cstdlib>
#include <getopt.h>
#include <iostream>
#include <stdexcept>
#include <string>

#include "daq_alert.hpp"

static void usage(const char *prog, std::ostream &out)
{
    out <<
        "Usage: " << prog << " [OPTIONS]\n"
        "\n"
        "Send a Mu2e DAQ alert via UDP broadcast using the C++ library.\n"
        "\n"
        "Options:\n"
        "  -s, --system-id ID    System identifier  (default: DAQ-NODE-01)\n"
        "  -m, --message TEXT    Alert message text  (default: Test alert from example-sender-cpp)\n"
        "  -i, --ip ADDRESS      Broadcast IP address (default: 255.255.255.255)\n"
        "  -p, --port NUM        UDP port             (default: 37020)\n"
        "  -h, --help            Show this help and exit\n";
}

int main(int argc, char *argv[])
{
    std::string system_id    = "DAQ-NODE-01";
    std::string message      = "Test alert from example-sender-cpp";
    std::string broadcast_ip = "255.255.255.255";
    int         port         = 37020;

    static const struct option long_opts[] = {
        {"system-id", required_argument, nullptr, 's'},
        {"message",   required_argument, nullptr, 'm'},
        {"ip",        required_argument, nullptr, 'i'},
        {"port",      required_argument, nullptr, 'p'},
        {"help",      no_argument,       nullptr, 'h'},
        {nullptr, 0, nullptr, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "s:m:i:p:h", long_opts, nullptr)) != -1) {
        switch (opt) {
            case 's': system_id    = optarg; break;
            case 'm': message      = optarg; break;
            case 'i': broadcast_ip = optarg; break;
            case 'p': {
                char *end;
                long v = std::strtol(optarg, &end, 10);
                if (*end != '\0' || v < 1 || v > 65535) {
                    std::cerr << "error: invalid port '" << optarg << "'\n";
                    return 1;
                }
                port = static_cast<int>(v);
                break;
            }
            case 'h':
                usage(argv[0], std::cout);
                return 0;
            default:
                usage(argv[0], std::cerr);
                return 1;
        }
    }

    std::cout << "Sending alert to " << broadcast_ip << ":" << port << "\n"
              << "  system_id : " << system_id << "\n"
              << "  message   : " << message   << "\n";

    try {
        mu2e::daq::AlertSender sender(broadcast_ip, static_cast<uint16_t>(port));
        sender.send(system_id, message);
    } catch (const mu2e::daq::AlertError &e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }

    std::cout << "Alert sent.\n";
    return 0;
}
