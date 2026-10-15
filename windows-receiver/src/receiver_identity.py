"""
Receiver identity and cryptographic operations for PhoneToUSB Windows Receiver.
Uses Ed25519 (RFC 8032) for high-performance, collision-resistant digital signatures.
"""

import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

class ReceiverIdentity:
    def __init__(self, key_path: Path):
        self.key_path = key_path
        self._private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self._public_key: Optional[ed25519.Ed25519PublicKey] = None
        self.receiver_id: str = ""
        self.friendly_name: str = "My PhoneToUSB Drive"

    @classmethod
    def load_or_create(cls, usb_root: Path, friendly_name: Optional[str] = None) -> "ReceiverIdentity":
        app_dir = usb_root / ".phonetoUSB"
        app_dir.mkdir(parents=True, exist_ok=True)
        key_file = app_dir / "receiver_identity.json"

        identity = cls(key_file)
        if key_file.exists():
            identity._load()
        else:
            identity._generate(friendly_name or "PhoneToUSB Drive")
            identity._save()
        return identity

    def _generate(self, friendly_name: str):
        self._private_key = ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.receiver_id = f"p2u-rcv-{hashlib.sha256(pub_bytes).hexdigest()[:16]}"
        self.friendly_name = friendly_name

    def _save(self):
        if not self._private_key or not self._public_key:
            raise ValueError("Keys not initialized")

        priv_bytes = self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

        data = {
            "receiver_id": self.receiver_id,
            "friendly_name": self.friendly_name,
            "public_key": base64.b64encode(pub_bytes).decode("ascii"),
            "private_key": base64.b64encode(priv_bytes).decode("ascii"),
            "version": 1
        }

        # Write safely
        temp_file = self.key_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, self.key_path)

    def _load(self):
        with open(self.key_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.receiver_id = data["receiver_id"]
        self.friendly_name = data.get("friendly_name", "PhoneToUSB Drive")

        priv_bytes = base64.b64decode(data["private_key"])
        pub_bytes = base64.b64decode(data["public_key"])

        self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        self._public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

    @property
    def public_key_base64(self) -> str:
        if not self._public_key:
            raise ValueError("Public key not available")
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(pub_bytes).decode("ascii")

    def sign(self, message: bytes) -> bytes:
        """Signs a message using the receiver's private key."""
        if not self._private_key:
            raise ValueError("Private key not available")
        return self._private_key.sign(message)

    def sign_base64(self, message: bytes) -> str:
        return base64.b64encode(self.sign(message)).decode("ascii")

    @staticmethod
    def verify_client_signature(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
        """Verifies a signature using a client's Ed25519 public key."""
        try:
            pub_bytes = base64.b64decode(public_key_b64)
            sig_bytes = base64.b64decode(signature_b64)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_key.verify(sig_bytes, message)
            return True
        except (InvalidSignature, ValueError, Exception):
            return False
