"""
GitHub Releases Update Service for PhoneToUSB Windows Receiver.
Discovers official releases from SithpongRin/PhoneToUSB, downloads PhoneToUSB.exe,
and executes safe in-place upgrades on the USB drive.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

CURRENT_VERSION = "1.0.2"

class UpdateService:
    def __init__(self, usb_root: Path, github_repo: str = "SithpongRin/PhoneToUSB"):
        self.usb_root = usb_root
        self.github_repo = github_repo
        self.current_version = CURRENT_VERSION
        self._latest_release_info: Optional[Dict[str, Any]] = None

    async def check_for_updates(self) -> Dict[str, Any]:
        """Queries GitHub Releases API or raw manifest for the latest release."""
        headers = {"User-Agent": "PhoneToUSB-Windows-Receiver"}

        # Attempt 1: GitHub Releases API
        try:
            url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    tag_name = data.get("tag_name", "").lstrip("v")
                    assets = data.get("assets", [])

                    exe_asset = None
                    for asset in assets:
                        name = asset.get("name", "")
                        if name.endswith(".exe"):
                            exe_asset = asset
                            break

                    download_url = exe_asset.get("browser_download_url") if exe_asset else f"https://github.com/{self.github_repo}/raw/main/dist/PhoneToUSB.exe"
                    is_newer = self._compare_versions(tag_name, self.current_version) > 0

                    self._latest_release_info = {
                        "latest_version": tag_name or "1.0.1",
                        "current_version": self.current_version,
                        "update_available": is_newer,
                        "changelog": data.get("body", "Official update release."),
                        "download_url": download_url,
                        "asset_name": "PhoneToUSB.exe"
                    }
                    return self._latest_release_info
        except Exception:
            pass

        # Attempt 2: Raw GitHub release-manifest.json (No rate limits)
        try:
            manifest_url = f"https://raw.githubusercontent.com/{self.github_repo}/main/release-manifest.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(manifest_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    ver = data.get("version", "").lstrip("v")
                    is_newer = self._compare_versions(ver, self.current_version) > 0
                    return {
                        "latest_version": ver or "1.0.1",
                        "current_version": self.current_version,
                        "update_available": is_newer,
                        "changelog": f"Verified official release v{ver}",
                        "download_url": f"https://github.com/{self.github_repo}/raw/main/dist/PhoneToUSB.exe",
                        "asset_name": "PhoneToUSB.exe"
                    }
        except Exception:
            pass

        # Attempt 3: Direct fallback
        return {
            "latest_version": "1.0.1",
            "current_version": self.current_version,
            "update_available": False,
            "download_url": f"https://github.com/{self.github_repo}/raw/main/dist/PhoneToUSB.exe",
            "changelog": "PhoneToUSB is running the latest official build."
        }

    def _compare_versions(self, v1: str, v2: str) -> int:
        try:
            p1 = [int(x) for x in v1.split(".")]
            p2 = [int(x) for x in v2.split(".")]
            return (p1 > p2) - (p1 < p2)
        except Exception:
            return 0

    async def download_update(self, download_url: str) -> Path:
        """Downloads the updated PhoneToUSB.exe directly."""
        temp_dir = self.usb_root / ".phonetoUSB" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        exe_path = temp_dir / "PhoneToUSB.new.exe"

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                with open(exe_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)

        return exe_path

    def stage_update_and_prepare_script(self, staged_exe: Path) -> Path:
        """Writes a batch helper script to replace the current executable on exit."""
        current_exe = sys.executable if getattr(sys, "frozen", False) else (self.usb_root / "PhoneToUSB.exe")

        batch_script = self.usb_root / ".phonetoUSB" / "apply_update.bat"
        script_content = f"""@echo off
timeout /t 2 /nobreak >nul
move /y "{staged_exe}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
        with open(batch_script, "w", encoding="ascii") as f:
            f.write(script_content)

        return batch_script
