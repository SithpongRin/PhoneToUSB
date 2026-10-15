"""
Pairing Coordinator for PhoneToUSB backend.
Brokers single-use pairing requests between mobile clients and online USB receivers.
"""

import json
import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket
from .receiver_registry import ReceiverRegistry
from .rate_limiter import RateLimiter

logger = logging.getLogger("PhoneToUSB.PairingCoordinator")

class PairingCoordinator:
    def __init__(self, registry: ReceiverRegistry, rate_limiter: RateLimiter):
        self.registry = registry
        self.rate_limiter = rate_limiter

    async def forward_pairing_request(self, client_ws: WebSocket, request_data: Dict[str, Any], client_ip: str) -> bool:
        """
        Validates rate limit, locates receiver session, and forwards the pairing request.
        """
        receiver_id = request_data.get("receiver_id")
        client_id = request_data.get("client_id")
        token = request_data.get("token")

        if not self.rate_limiter.is_allowed(f"pair:{client_ip}"):
            await client_ws.send_text(json.dumps({
                "action": "PAIRING_RESULT",
                "status": "REJECTED",
                "reason": "RATE_LIMIT_EXCEEDED"
            }))
            return False

        receiver_session = self.registry.get_session(receiver_id)
        if not receiver_session:
            await client_ws.send_text(json.dumps({
                "action": "PAIRING_RESULT",
                "status": "REJECTED",
                "reason": "RECEIVER_OFFLINE"
            }))
            return False

        # Forward request to Windows Receiver
        forward_msg = {
            "action": "PAIRING_REQUEST",
            "client_id": client_id,
            "client_name": request_data.get("client_name", "Android Phone"),
            "client_pubkey": request_data.get("client_pubkey"),
            "token": token
        }
        await receiver_session.websocket.send_text(json.dumps(forward_msg))
        return True
