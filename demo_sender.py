#!/usr/bin/env python3
"""
demo_sender.py - Send a test DAQ critical error broadcast message.

Usage:
    python3 demo_sender.py
    python3 demo_sender.py --system-id "DAQ-NODE-03" --message "Readout buffer overflow"
    python3 demo_sender.py --ip 192.168.1.255 --port 37020
"""

import argparse
import json
import socket
from datetime import datetime

from config import BROADCAST_PORT

BROADCAST_IP = "255.255.255.255"


def send_alert(
    system_id: str,
    message: str,
    broadcast_ip: str = BROADCAST_IP,
    port: int = BROADCAST_PORT,
) -> None:
    payload = {
        "system_id": system_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "message": message,
    }

    data = json.dumps(payload).encode("utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(data, (broadcast_ip, port))

    print(f"Sent alert to {broadcast_ip}:{port}")
    print(f"  system_id : {payload['system_id']}")
    print(f"  timestamp : {payload['timestamp']}")
    print(f"  message   : {payload['message']}")


def main():
    parser = argparse.ArgumentParser(
        description="Send a test DAQ critical error broadcast message."
    )
    parser.add_argument(
        "--system-id",
        default="DAQ-NODE-01",
        help="System identifier included in the alert (default: DAQ-NODE-01)",
    )
    parser.add_argument(
        "--message",
        default="Critical error in the data acquisition pipeline. Immediate attention required.",
        help="Error message text",
    )
    parser.add_argument(
        "--ip",
        default=BROADCAST_IP,
        help=f"Broadcast IP address (default: {BROADCAST_IP})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=BROADCAST_PORT,
        help=f"UDP port (default: {BROADCAST_PORT})",
    )

    args = parser.parse_args()
    send_alert(args.system_id, args.message, args.ip, args.port)


if __name__ == "__main__":
    main()
