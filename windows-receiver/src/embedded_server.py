"""
Embedded Coordination WebSocket Server for PhoneToUSB Windows Receiver.
Runs automatically on 0.0.0.0:8000 inside PhoneToUSB.exe so that smartphones
can pair and transfer files immediately without requiring a separate server process.
"""

import json
import secrets
import asyncio
import logging
from typing import Dict, Any, Optional
import websockets

try:
    from .receiver_identity import ReceiverIdentity
except (ImportError, ValueError):
    from receiver_identity import ReceiverIdentity

logger = logging.getLogger("PhoneToUSB.EmbeddedServer")


class EmbeddedCoordinationServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self._server = None
        self.receivers: Dict[str, Dict[str, Any]] = {}
        self.clients: Dict[str, Any] = {}

    async def start(self) -> bool:
        """Starts the embedded WebSocket coordination server on 0.0.0.0:8000."""
        try:
            self._server = await websockets.serve(
                self._handle_connection,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=15,
                max_size=16 * 1024 * 1024  # 16 MB max frame size for fast file chunks
            )
            logger.info(f"Embedded Coordination Server listening on ws://{self.host}:{self.port}")
            return True
        except OSError as e:
            # Port 8000 may already be bound by another instance or external backend
            logger.info(f"Port {self.port} already in use ({e}); using existing server.")
            return False
        except Exception as e:
            logger.warning(f"Could not start embedded server: {e}")
            return False

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_connection(self, websocket, *args):
        """Unified connection handler for both /ws/receiver and /ws/client."""
        role = None
        peer_id = None

        try:
            raw_first = await asyncio.wait_for(websocket.recv(), timeout=15.0)
            first_msg = json.loads(raw_first)

            # 1. Windows Receiver Connection
            if first_msg.get("action") == "REGISTER_RECEIVER":
                role = "receiver"
                peer_id = first_msg.get("receiver_id", "")
                friendly_name = first_msg.get("friendly_name", "PhoneToUSB Drive")
                pubkey_b64 = first_msg.get("public_key", "")

                nonce = secrets.token_hex(32)
                await websocket.send(json.dumps({"action": "CHALLENGE", "nonce": nonce}))

                auth_raw = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                auth_msg = json.loads(auth_raw)
                sig_b64 = auth_msg.get("signature", "")

                if not ReceiverIdentity.verify_client_signature(pubkey_b64, nonce.encode("utf-8"), sig_b64):
                    await websocket.send(json.dumps({"status": "AUTH_FAILED"}))
                    return

                self.receivers[peer_id] = {
                    "ws": websocket,
                    "friendly_name": friendly_name,
                    "public_key": pubkey_b64
                }
                await websocket.send(json.dumps({"status": "AUTHENTICATED", "receiver_id": peer_id}))
                logger.info(f"Embedded Server: Receiver '{friendly_name}' ({peer_id}) authenticated.")

                async for raw in websocket:
                    msg = json.loads(raw)
                    action = msg.get("action")
                    if action == "HEARTBEAT":
                        continue
                    elif action in ("PAIRING_RESULT", "SDP_ANSWER", "ICE_CANDIDATE", "DATA_FRAME", "ERROR"):
                        target_client_id = msg.get("client_id")
                        client_ws = self.clients.get(target_client_id)
                        if client_ws:
                            await client_ws.send(json.dumps(msg))

            # 2. Android Mobile Client Connection
            elif "client_id" in first_msg:
                role = "client"
                peer_id = first_msg.get("client_id", "")
                if not peer_id:
                    return

                self.clients[peer_id] = websocket
                await websocket.send(json.dumps({"status": "READY", "client_id": peer_id}))
                logger.info(f"Embedded Server: Android client ({peer_id}) connected.")

                # If the very first message already was a PAIRING_REQUEST or DATA_FRAME, process it immediately
                if first_msg.get("action") in ("QUERY_PRESENCE", "PAIRING_REQUEST", "SDP_OFFER", "ICE_CANDIDATE", "DATA_FRAME"):
                    await self._process_client_action(peer_id, first_msg, websocket)

                async for raw in websocket:
                    msg = json.loads(raw)
                    await self._process_client_action(peer_id, msg, websocket)

        except Exception as e:
            logger.debug(f"Embedded Server connection closed ({role}={peer_id}): {e}")
        finally:
            if role == "receiver" and peer_id:
                if self.receivers.get(peer_id, {}).get("ws") is websocket:
                    self.receivers.pop(peer_id, None)
            elif role == "client" and peer_id:
                if self.clients.get(peer_id) is websocket:
                    self.clients.pop(peer_id, None)

    def _resolve_receiver(self, requested_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if requested_id and requested_id in self.receivers:
            return self.receivers[requested_id]
        if len(self.receivers) == 1:
            return next(iter(self.receivers.values()))
        return None

    async def _process_client_action(self, client_id: str, msg: Dict[str, Any], client_ws):
        action = msg.get("action")

        if action == "QUERY_PRESENCE":
            rids = msg.get("receiver_ids", [])
            presence = {rid: (self._resolve_receiver(rid) is not None) for rid in rids}
            await client_ws.send(json.dumps({
                "action": "PRESENCE_RESPONSE",
                "presence": presence
            }))

        elif action == "PAIRING_REQUEST":
            request_id = msg.get("request_id", "")
            receiver_id = msg.get("receiver_id")
            rcv = self._resolve_receiver(receiver_id)
            if not rcv:
                await client_ws.send(json.dumps({
                    "action": "PAIRING_RESULT",
                    "request_id": request_id,
                    "status": "REJECTED",
                    "reason": "RECEIVER_OFFLINE"
                }))
                return

            forward_msg = {
                "action": "PAIRING_REQUEST",
                "request_id": request_id,
                "client_id": client_id,
                "client_name": msg.get("client_name", "Android Phone"),
                "client_pubkey": msg.get("client_pubkey"),
                "token": msg.get("token")
            }
            await rcv["ws"].send(json.dumps(forward_msg))

        elif action in ("SDP_OFFER", "ICE_CANDIDATE", "DATA_FRAME"):
            receiver_id = msg.get("receiver_id")
            rcv = self._resolve_receiver(receiver_id)
            if not rcv:
                await client_ws.send(json.dumps({
                    "action": "DATA_FRAME",
                    "request_id": msg.get("request_id", ""),
                    "success": False,
                    "error": "RECEIVER_OFFLINE"
                }))
                return

            msg["client_id"] = client_id
            await rcv["ws"].send(json.dumps(msg))
