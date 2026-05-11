#ifndef MU2E_DAQ_ALERT_H
#define MU2E_DAQ_ALERT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

/** Default UDP port used by the daq_alert daemon. */
#define DAQ_ALERT_PORT 37020

/** Default broadcast address (subnet-wide broadcast). */
#define DAQ_ALERT_BROADCAST_IP "255.255.255.255"

typedef enum {
    DAQ_ALERT_OK         =  0,
    DAQ_ALERT_ERR_SOCKET = -1,  /* could not create or configure UDP socket */
    DAQ_ALERT_ERR_SEND   = -2,  /* sendto() failed */
    DAQ_ALERT_ERR_FORMAT = -3,  /* payload too large or strings contain NUL */
} DaqAlertResult;

/**
 * Send a DAQ alert via UDP broadcast.
 *
 * Builds the JSON payload
 *   {"system_id":"...","timestamp":"<ISO-8601>","message":"..."}
 * and broadcasts it to broadcast_ip:port.
 *
 * @param system_id     Identifier of the sending system, e.g. "DAQ-NODE-01".
 * @param message       Human-readable error description.
 * @param broadcast_ip  Destination address, or NULL to use DAQ_ALERT_BROADCAST_IP.
 * @param port          UDP port, or 0 to use DAQ_ALERT_PORT.
 * @return DAQ_ALERT_OK on success, or a negative DaqAlertResult error code.
 */
DaqAlertResult daq_alert_send(const char *system_id,
                               const char *message,
                               const char *broadcast_ip,
                               uint16_t    port);

/** Return a static human-readable string for a result code. */
const char *daq_alert_strerror(DaqAlertResult result);

#ifdef __cplusplus
}
#endif

#endif /* MU2E_DAQ_ALERT_H */
