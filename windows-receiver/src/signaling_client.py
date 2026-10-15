"""
Signaling Client for PhoneToUSB Windows Receiver.
Maintains persistent WebSocket connection to the Internet coordination backend,
handles challenge-response authentication, presence heartbeats, pairing requests,
and remote session routing.
"""

import os
import json
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
import websockets

try:
    from .receiver_identity import ReceiverIdentity
    from .pairing_service import PairingService
    from .authorization_service import AuthorizationService
except (ImportError, ValueError):
    from receiver_identity import ReceiverIdentity
    from pairing_service import PairingService
    from authorization_service import AuthorizationService

logger = logging.getLogger("PhoneToUSB.SignalingClient")

class SignalingClient:
    def __init__(
        self,
        backend_ws_url: str,
        identity: ReceiverIdentity,
        pairing_service: PairingService,
        auth_service: AuthorizationService,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_pairing_request: Optional[Callable[[Dict[str, Any], asyncio.Future], None]] = None,
        on_data_message: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        self.backend_ws_url = backend_ws_url
        self.identity = identity
        self.pairing_service = pairing_service
        self.auth_service = auth_service
        self.on_status_change = on_status_change
        self.on_pairing_request = on_pairing_request
        self.on_data_message = on_data_message

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._is_running = False
        self._is_connected = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts the persistent connection loop with automatic reconnection."""
        self._is_running = True
        while self._is_running:
            try:
                self._update_status("CONNECTING")
                logger.info(f"Connecting to signaling backend: {self.backend_ws_url}")
                async with websockets.connect(
                    self.backend_ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as ws:
                    self._ws = ws
                    # Step 1: Authenticate with Backend
                    authenticated = await self._perform_registration_handshake()
                    if not authenticated:
                        logger.error("Failed to authenticate receiver with backend. Retrying in 10s...")
                        await asyncio.sleep(10)
                        continue

                    self._is_connected = True
                    self._update_status("ONLINE")
                    logger.info("Receiver is registered and ONLINE")

                    # Start heartbeat task
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    # Listen for messages
                    await self._message_listener()

            except (websockets.ConnectionClosed, OSError, Exception) as e:
                self._is_connected = False
                self._update_status("OFFLINE")
                logger.warning(f"Signaling connection lost ({e}). Reconnecting in 5 seconds...")
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()
                await asyncio.sleep(5)

    def stop(self):
        """Stops the signaling client safely."""
        self._is_running = False
        self._is_connected = False
        if self._ws:
            asyncio.create_task(self._ws.close())
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._update_status("OFFLINE")

    def _update_status(self, status: str):
        if self.on_status_change:
            self.on_status_change(status)

    async def _send_json(self, data: Dict[str, Any]):
        if self._ws and self._is_connected:
            await self._ws.send(json.dumps(data))

    async def _perform_registration_handshake(self) -> bool:
        """Registers the receiver ID and proves ownership via Ed25519 signature."""
        reg_msg = {
            "action": "REGISTER_RECEIVER",
            "receiver_id": self.identity.receiver_id,
            "friendly_name": self.identity.friendly_name,
            "public_key": self.identity.public_key_base64
        }
        await self._ws.send(json.dumps(reg_msg))

        resp_text = await self._ws.recv()
        resp = json.loads(resp_text)

        if resp.get("action") == "CHALLENGE":
            nonce = resp["nonce"]
            sig_b64 = self.identity.sign_base64(nonce.encode("utf-8"))
            auth_msg = {
                "action": "AUTH_RESPONSE",
                "receiver_id": self.identity.receiver_id,
                "signature": sig_b64
            }
            await self._ws.send(json.dumps(auth_msg))

            final_resp = json.loads(await self._ws.recv())
            return final_resp.get("status") == "AUTHENTICATED"

        return False

    async def _heartbeat_loop(self):
        while self._is_running and self._is_connected:
            try:
                await asyncio.sleep(15)
                await self._send_json({"action": "HEARTBEAT", "receiver_id": self.identity.receiver_id})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
                break

    async def _message_listener(self):
        async for raw_msg in self._ws:
            try:
                msg = json.loads(raw_msg)
                action = msg.get("action")

                if action == "PAIRING_REQUEST":
                    await self._handle_pairing_request(msg)
                elif action in ("SDP_OFFER", "ICE_CANDIDATE", "DATA_FRAME"):
                    client_id = msg.get("client_id")
                    # Check authorization
                    if not self.auth_service.is_authorized(client_id):
                        logger.warning(f"Rejected message from unauthorized client: {client_id}")
                        await self._send_json({
                            "action": "ERROR",
                            "client_id": client_id,
                            "error": "UNAUTHORIZED_DEVICE"
                        })
                        continue

                    if self.on_data_message:
                        self.on_data_message(client_id, msg)

            except Exception as e:
                logger.error(f"Error processing signaling message: {e}")

    async def _handle_pairing_request(self, msg: Dict[str, Any]):
        client_id = msg.get("client_id")
        client_pubkey = msg.get("client_pubkey")
        client_name = msg.get("client_name", "Android Phone")
        token = msg.get("token")

        logger.info(f"Received pairing request from '{client_name}' ({client_id})")

        # Verify token validity
        if not self.pairing_service.is_token_valid(token):
            logger.warning("Pairing attempt with invalid or expired token")
            await self._send_json({
                "action": "PAIRING_RESULT",
                "client_id": client_id,
                "status": "REJECTED",
                "reason": "INVALID_OR_EXPIRED_TOKEN"
            })
            return

        # Prompt user on Windows GUI
        if self.on_pairing_request:
            loop = asyncio.get_running_loop()
            approval_future = loop.create_future()
            self.on_pairing_request(msg, approval_future)

            approved = await approval_future
            if approved:
                self.pairing_service.invalidate_token()
                self.auth_service.authorize_device(client_id, client_pubkey, client_name)
                logger.info(f"Approved pairing for device: {client_name} ({client_id})")
                await self._send_json({
                    "action": "PAIRING_RESULT",
                    "client_id": client_id,
                    "status": "APPROVED",
                    "receiver_friendly_name": self.identity.friendly_name,
                    "receiver_pubkey": self.identity.public_key_base64
                })
            else:
                self.pairing_service.invalidate_token()
                logger.info(f"Rejected pairing for device: {client_name}")
                await self._send_json({
                    "action": "PAIRING_RESULT",
                    "client_id": client_id,
                    "status": "REJECTED",
                    "reason": "USER_REJECTED"
                })

    async def send_to_client(self, client_id: str, payload: Dict[str, Any]):
        """Forwards data or signaling to a connected client via backend relay."""
        payload["action"] = payload.get("action", "DATA_FRAME")
        payload["client_id"] = client_id
        payload["receiver_id"] = self.identity.receiver_id
        await self._send_json(payload)
