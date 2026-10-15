"""
Pairing Service for PhoneToUSB Windows Receiver.
Generates single-use expiring pairing tokens, renders pairing QR codes,
and validates initial pairing requests with explicit user authorization.
"""

import os
import time
import json
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import qrcode
from PIL import Image

PAIRING_TOKEN_TTL = 180  # 3 minutes

class PairingService:
    def __init__(self, receiver_id: str, receiver_pubkey_b64: str, backend_url: str):
        self.receiver_id = receiver_id
        self.receiver_pubkey_b64 = receiver_pubkey_b64
        self.backend_url = backend_url
        self._active_token: Optional[str] = None
        self._token_created_at: float = 0.0

    def generate_pairing_session(self) -> Tuple[str, Dict[str, Any]]:
        """
        Generates a new single-use pairing token and returns the QR code data payload.
        """
        self._active_token = secrets.token_urlsafe(32)
        self._token_created_at = time.time()

        payload = {
            "v": 1,
            "rid": self.receiver_id,
            "token": self._active_token,
            "pub": self.receiver_pubkey_b64,
            "backend": self.backend_url,
            "expires_at": int(self._token_created_at + PAIRING_TOKEN_TTL)
        }
        qr_string = json.dumps(payload, separators=(',', ':'))
        return self._active_token, payload

    def render_qr_image(self, payload: Dict[str, Any], output_path: Optional[Path] = None) -> Image.Image:
        """Renders QR code image for display in GUI or export to file."""
        qr_data = json.dumps(payload, separators=(',', ':'))
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0D1117", back_color="#FFFFFF")

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_path))
        return img

    def is_token_valid(self, token: str) -> bool:
        """Validates if the token matches the active token and has not expired."""
        if not self._active_token or not token:
            return False
        if time.time() - self._token_created_at > PAIRING_TOKEN_TTL:
            self.invalidate_token()
            return False
        # Constant-time comparison
        return secrets.compare_digest(self._active_token, token)

    def invalidate_token(self):
        """Immediately destroys the active pairing token."""
        self._active_token = None
        self._token_created_at = 0.0

    @property
    def remaining_seconds(self) -> int:
        if not self._active_token:
            return 0
        rem = int(PAIRING_TOKEN_TTL - (time.time() - self._token_created_at))
        return max(0, rem)
