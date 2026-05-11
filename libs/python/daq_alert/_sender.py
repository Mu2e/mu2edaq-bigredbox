"""
Core implementation of the DAQ alert sender.
"""

import json
import socket
from datetime import datetime

DEFAULT_PORT: int = 37020
DEFAULT_BROADCAST_IP: str = "255.255.255.255"


def send_alert(
    system_id: str,
    message: str,
    broadcast_ip: str = DEFAULT_BROADCAST_IP,
    port: int = DEFAULT_PORT,
) -> None:
    """Send a single DAQ alert via UDP broadcast.

    Args:
        system_id:    Identifier of the sending system, e.g. "DAQ-NODE-01".
        message:      Human-readable error description.
        broadcast_ip: UDP broadcast destination (default: subnet-wide broadcast).
        port:         UDP port (default: 37020).

    Raises:
        OSError: If the socket cannot be created or the datagram cannot be sent.
    """
    payload = json.dumps(
        {
            "system_id": system_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "message": message,
        }
    ).encode("utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(payload, (broadcast_ip, port))


class AlertSender:
    """Reusable sender that keeps broadcast_ip and port as instance state.

    Example::

        sender = AlertSender("192.168.1.255")
        sender.send("DAQ-NODE-01", "Readout buffer overflow")
    """

    def __init__(
        self,
        broadcast_ip: str = DEFAULT_BROADCAST_IP,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.broadcast_ip = broadcast_ip
        self.port = port

    def send(self, system_id: str, message: str) -> None:
        """Send a single alert using this sender's broadcast address and port."""
        send_alert(system_id, message, self.broadcast_ip, self.port)
