#include "daq_alert.hpp"

/* Pull in the C implementation; the extern "C" guard in daq_alert.h
   ensures correct linkage when compiled as C++. */
#include "daq_alert.h"

#include <string>
#include <stdexcept>

namespace mu2e {
namespace daq {

AlertSender::AlertSender(std::string broadcast_ip, uint16_t port)
    : broadcast_ip_(std::move(broadcast_ip)), port_(port)
{}

void AlertSender::send(const std::string &system_id,
                       const std::string &message) const
{
    DaqAlertResult rc = daq_alert_send(
        system_id.c_str(),
        message.c_str(),
        broadcast_ip_.c_str(),
        port_
    );
    if (rc != DAQ_ALERT_OK)
        throw AlertError(daq_alert_strerror(rc));
}

void AlertSender::send_once(const std::string &system_id,
                            const std::string &message,
                            const std::string &broadcast_ip,
                            uint16_t           port)
{
    AlertSender(broadcast_ip, port).send(system_id, message);
}

} // namespace daq
} // namespace mu2e
