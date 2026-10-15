"""
Authorization Service for PhoneToUSB Windows Receiver.
Manages the registry of trusted, paired Android devices and verifies client identities.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

class AuthorizationService:
    def __init__(self, usb_root: Path):
        self.usb_root = usb_root
        self.registry_file = usb_root / ".phonetoUSB" / "paired_devices.json"
        self._devices: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        """Loads paired devices from .phonetoUSB/paired_devices.json."""
        if not self.registry_file.exists():
            self._devices = {}
            return

        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._devices = data.get("devices", {})
        except Exception:
            self._devices = {}

    def save(self):
        """Safely saves paired devices to disk using atomic rename."""
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.registry_file.with_suffix(".tmp")
        data = {"version": 1, "devices": self._devices}
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, self.registry_file)

    def is_authorized(self, client_id: str) -> bool:
        """Checks if a client device is in the authorized registry."""
        return client_id in self._devices

    def get_client_pubkey(self, client_id: str) -> Optional[str]:
        device = self._devices.get(client_id)
        return device.get("client_pubkey") if device else None

    def authorize_device(self, client_id: str, client_pubkey: str, friendly_name: str) -> Dict[str, Any]:
        """Registers a new authorized phone after user approval."""
        device_entry = {
            "client_id": client_id,
            "client_pubkey": client_pubkey,
            "friendly_name": friendly_name,
            "paired_at": int(time.time()),
            "last_seen": int(time.time())
        }
        self._devices[client_id] = device_entry
        self.save()
        return device_entry

    def update_last_seen(self, client_id: str):
        if client_id in self._devices:
            self._devices[client_id]["last_seen"] = int(time.time())
            self.save()

    def revoke_device(self, client_id: str) -> bool:
        """Revokes an individual phone's authorization."""
        if client_id in self._devices:
            del self._devices[client_id]
            self.save()
            return True
        return False

    def revoke_all(self):
        """Revokes all paired phones."""
        self._devices = {}
        self.save()

    def list_devices(self) -> List[Dict[str, Any]]:
        """Returns the list of all currently authorized phones."""
        return list(self._devices.values())
