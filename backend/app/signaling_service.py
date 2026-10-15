"""
WebRTC Signaling Service for PhoneToUSB backend.
Routes SDP offers, SDP answers, ICE candidates, and relayed data frames between
connected Android clients and USB receivers.
"""

import json
import logging
from typing import Dict, Any, Optional
from fastapi import WebSocket
from .receiver_registry import ReceiverRegistry

logger = logging.getLogger("PhoneToUSB.SignalingService")

class SignalingService:
    def __init__(self, registry: ReceiverRegistry):
        self.registry = registry

    async def route_client_to_receiver(self, client_id: str, msg: Dict[str, Any], client_ws: WebSocket):
        """Routes message from Android phone to the targeted Windows receiver."""
        receiver_id = msg.get("receiver_id")
        if not receiver_id:
            await client_ws.send_text(json.dumps({"error": "Missing receiver_id"}))
            return

        session = self.registry.get_session(receiver_id)
        if not session:
            await client_ws.send_text(json.dumps({
                "action": "ERROR",
                "receiver_id": receiver_id,
                "error": "RECEIVER_OFFLINE"
            }))
            return

        msg["client_id"] = client_id
        await session.websocket.send_text(json.dumps(msg))

    async def route_receiver_to_client(self, receiver_id: str, msg: Dict[str, Any], client_sockets: Dict[str, WebSocket]):
        """Routes message from Windows receiver back to the requesting Android phone."""
        client_id = msg.get("client_id")
        if not client_id:
            return

        client_ws = client_sockets.get(client_id)
        if client_ws:
            msg["receiver_id"] = receiver_id
            await client_ws.send_text(json.dumps(msg))
