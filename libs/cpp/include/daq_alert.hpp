#pragma once

#include <cstdint>
#include <stdexcept>
#include <string>

namespace mu2e {
namespace daq {

/** Thrown by AlertSender when a send operation fails. */
class AlertError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

/**
 * Sends DAQ alert messages via UDP broadcast.
 *
 * Constructs and reuses socket configuration across multiple sends.
 * Each call to send() opens a new socket (stateless at the OS level)
 * so instances are safe to share across threads as long as no mutation
 * occurs concurrently.
 *
 * Example:
 *   mu2e::daq::AlertSender sender("192.168.1.255");
 *   sender.send("DAQ-NODE-01", "Readout buffer overflow");
 */
class AlertSender {
public:
    /**
     * @param broadcast_ip  Destination broadcast address.
     *                      Defaults to 255.255.255.255 (subnet-wide).
     * @param port          UDP port.  Defaults to 37020.
     */
    explicit AlertSender(std::string broadcast_ip = "255.255.255.255",
                         uint16_t    port         = 37020);

    /**
     * Send a single alert.
     *
     * @param system_id  Identifier of the sending system.
     * @param message    Human-readable error description.
     * @throws AlertError on socket creation or send failure.
     */
    void send(const std::string &system_id,
              const std::string &message) const;

    /** Convenience wrapper — creates a temporary sender and sends once. */
    static void send_once(const std::string &system_id,
                          const std::string &message,
                          const std::string &broadcast_ip = "255.255.255.255",
                          uint16_t           port         = 37020);

    const std::string &broadcast_ip() const { return broadcast_ip_; }
    uint16_t           port()         const { return port_; }

private:
    std::string broadcast_ip_;
    uint16_t    port_;
};

} // namespace daq
} // namespace mu2e
