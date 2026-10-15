"""
Receiver Registry and Presence Manager for PhoneToUSB backend.
Tracks connected Windows receivers, maintains active WebSocket handles,
and checks heartbeat leases to detect online/offline transitions.
"""

import time
import secrets
import base64
from typing import Dict, Any, Optional
from fastapi import WebSocket
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

class ReceiverSession:
    def __init__(self, receiver_id: str, friendly_name: str, public_key_b64: str, websocket: WebSocket):
        self.receiver_id = receiver_id
        self.friendly_name = friendly_name
        self.public_key_b64 = public_key_b64
        self.websocket = websocket
        self.last_heartbeat = time.time()
        self.is_authenticated = False
        self.pending_challenge: Optional[str] = None

class ReceiverRegistry:
    def __init__(self, heartbeat_timeout: int = 45):
        self.heartbeat_timeout = heartbeat_timeout
        self._receivers: Dict[str, ReceiverSession] = {}

    def initiate_registration(self, receiver_id: str, friendly_name: str, public_key_b64: str, ws: WebSocket) -> str:
        """Creates a pending session and returns a random challenge nonce."""
        nonce = secrets.token_hex(32)
        session = ReceiverSession(receiver_id, friendly_name, public_key_b64, ws)
        session.pending_challenge = nonce
        self._receivers[receiver_id] = session
        return nonce

    def complete_registration(self, receiver_id: str, signature_b64: str) -> bool:
        """Verifies that the receiver holds the private key corresponding to its declared public key."""
        session = self._receivers.get(receiver_id)
        if not session or not session.pending_challenge:
            return False

        try:
            pub_bytes = base64.b64decode(session.public_key_b64)
            sig_bytes = base64.b64decode(signature_b64)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_key.verify(sig_bytes, session.pending_challenge.encode("utf-8"))

            session.is_authenticated = True
            session.pending_challenge = None
            session.last_heartbeat = time.time()
            return True
        except (InvalidSignature, ValueError, Exception):
            self.remove_receiver(receiver_id)
            return False

    def update_heartbeat(self, receiver_id: str):
        session = self._receivers.get(receiver_id)
        if session and session.is_authenticated:
            session.last_heartbeat = time.time()

    def get_session(self, receiver_id: str) -> Optional[ReceiverSession]:
        session = self._receivers.get(receiver_id)
        if not session or not session.is_authenticated:
            return None
        # Check heartbeat freshness
        if time.time() - session.last_heartbeat > self.heartbeat_timeout:
            self.remove_receiver(receiver_id)
            return None
        return session

    def is_online(self, receiver_id: str) -> bool:
        return self.get_session(receiver_id) is not None

    def remove_receiver(self, receiver_id: str):
        self._receivers.pop(receiver_id, None)

    def active_count(self) -> int:
        now = time.time()
        return sum(1 for s in self._receivers.values() if s.is_authenticated and now - s.last_heartbeat <= self.heartbeat_timeout)
