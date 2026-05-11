#include "daq_alert.h"

#include <stdio.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#  include <winsock2.h>
#  pragma comment(lib, "ws2_32.lib")
   typedef int socklen_t;
#  define CLOSE_SOCKET(s) closesocket(s)
   typedef SOCKET sock_t;
#else
#  include <sys/socket.h>
#  include <netinet/in.h>
#  include <arpa/inet.h>
#  include <unistd.h>
#  define INVALID_SOCKET (-1)
#  define SOCKET_ERROR   (-1)
#  define CLOSE_SOCKET(s) close(s)
   typedef int sock_t;
#endif

#define PAYLOAD_MAX 4096

/* Write src as a JSON-escaped string into dst (size dst_size).
   Returns 0 on success, -1 if the buffer is too small. */
static int json_escape(const char *src, char *dst, size_t dst_size)
{
    size_t j = 0;
    for (size_t i = 0; src[i] != '\0'; ++i) {
        unsigned char c = (unsigned char)src[i];
        if (j + 7 >= dst_size)
            return -1;
        switch (c) {
            case '"':  dst[j++] = '\\'; dst[j++] = '"';  break;
            case '\\': dst[j++] = '\\'; dst[j++] = '\\'; break;
            case '\n': dst[j++] = '\\'; dst[j++] = 'n';  break;
            case '\r': dst[j++] = '\\'; dst[j++] = 'r';  break;
            case '\t': dst[j++] = '\\'; dst[j++] = 't';  break;
            default:
                if (c < 0x20) {
                    j += (size_t)snprintf(dst + j, dst_size - j, "\\u%04x", c);
                } else {
                    dst[j++] = (char)c;
                }
                break;
        }
    }
    dst[j] = '\0';
    return 0;
}

static void iso8601_now(char *buf, size_t buf_size)
{
    time_t t = time(NULL);
    struct tm tm_val;
#ifdef _WIN32
    localtime_s(&tm_val, &t);
#else
    localtime_r(&t, &tm_val);
#endif
    if (strftime(buf, buf_size, "%Y-%m-%dT%H:%M:%S", &tm_val) == 0)
        snprintf(buf, buf_size, "1970-01-01T00:00:00");
}

DaqAlertResult daq_alert_send(const char *system_id,
                               const char *message,
                               const char *broadcast_ip,
                               uint16_t    port)
{
    if (!broadcast_ip || broadcast_ip[0] == '\0')
        broadcast_ip = DAQ_ALERT_BROADCAST_IP;
    if (port == 0)
        port = DAQ_ALERT_PORT;

    char ts[32];
    iso8601_now(ts, sizeof(ts));

    char esc_id[PAYLOAD_MAX / 2];
    char esc_msg[PAYLOAD_MAX / 2];
    if (json_escape(system_id, esc_id, sizeof(esc_id)) != 0 ||
        json_escape(message,   esc_msg, sizeof(esc_msg)) != 0)
        return DAQ_ALERT_ERR_FORMAT;

    char payload[PAYLOAD_MAX];
    int payload_len = snprintf(payload, sizeof(payload),
        "{\"system_id\":\"%s\",\"timestamp\":\"%s\",\"message\":\"%s\"}",
        esc_id, ts, esc_msg);
    if (payload_len < 0 || payload_len >= (int)sizeof(payload))
        return DAQ_ALERT_ERR_FORMAT;

#ifdef _WIN32
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
#endif

    sock_t sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
#ifdef _WIN32
        WSACleanup();
#endif
        return DAQ_ALERT_ERR_SOCKET;
    }

    int broadcast_opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST,
               (const char *)&broadcast_opt, sizeof(broadcast_opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(port);
    addr.sin_addr.s_addr = inet_addr(broadcast_ip);

    int sent = sendto(sock, payload, payload_len, 0,
                      (struct sockaddr *)&addr, sizeof(addr));
    CLOSE_SOCKET(sock);

#ifdef _WIN32
    WSACleanup();
#endif

    return (sent == SOCKET_ERROR) ? DAQ_ALERT_ERR_SEND : DAQ_ALERT_OK;
}

const char *daq_alert_strerror(DaqAlertResult result)
{
    switch (result) {
        case DAQ_ALERT_OK:         return "Success";
        case DAQ_ALERT_ERR_SOCKET: return "Failed to create UDP socket";
        case DAQ_ALERT_ERR_SEND:   return "Failed to send UDP datagram";
        case DAQ_ALERT_ERR_FORMAT: return "Payload too large or format error";
        default:                   return "Unknown error";
    }
}
