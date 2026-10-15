"""
Session Manager and Ephemeral TURN Credential Generator for PhoneToUSB backend.
Implements the Coturn REST API (HMAC-SHA1) ephemeral credential generation standard.
"""

import time
import hmac
import hashlib
import base64
from typing import Dict, Any, List
from .configuration import settings

class SessionManager:
    def __init__(self, turn_secret: str, turn_realm: str, stun_urls: List[str], turn_urls: List[str]):
        self.turn_secret = turn_secret
        self.turn_realm = turn_realm
        self.stun_urls = stun_urls
        self.turn_urls = turn_urls

    def generate_turn_credentials(self, client_id: str, ttl_seconds: int = 3600) -> Dict[str, Any]:
        """
        Generates ephemeral time-limited TURN credentials using HMAC-SHA1.
        Matches the standard Coturn 'use-auth-secret' specification.
        """
        expiry_timestamp = int(time.time() + ttl_seconds)
        username = f"{expiry_timestamp}:{client_id}"

        # HMAC-SHA1 calculation
        digest = hmac.new(
            self.turn_secret.encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha1
        ).digest()
        password = base64.b64encode(digest).decode("utf-8")

        ice_servers = [
            {"urls": self.stun_urls}
        ]

        if self.turn_urls:
            ice_servers.append({
                "urls": self.turn_urls,
                "username": username,
                "credential": password
            })

        return {
            "ttl": ttl_seconds,
            "expires_at": expiry_timestamp,
            "ice_servers": ice_servers
        }
