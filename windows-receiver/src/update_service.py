"""
GitHub Releases Update Service for PhoneToUSB Windows Receiver.
Discovers official releases, verifies package integrity via SHA-256,
and executes safe in-place upgrades on the USB drive.
"""

import os
import sys
import json
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

CURRENT_VERSION = "1.0.0"

class UpdateService:
    def __init__(self, usb_root: Path, github_repo: str = "phonetousb/phonetousb"):
        self.usb_root = usb_root
        self.github_repo = github_repo
        self.current_version = CURRENT_VERSION
        self._latest_release_info: Optional[Dict[str, Any]] = None

    async def check_for_updates(self) -> Dict[str, Any]:
        """Queries GitHub Releases API for the latest release."""
        url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
        headers = {"User-Agent": "PhoneToUSB-Windows-Receiver"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return {"update_available": False, "message": "No releases found"}
                resp.raise_for_status()
                data = resp.json()

            tag_name = data.get("tag_name", "").lstrip("v")
            assets = data.get("assets", [])

            # Find windows zip asset
            windows_asset = None
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith("-Windows.zip") or name.endswith("-win.zip"):
                    windows_asset = asset
                    break

            is_newer = self._compare_versions(tag_name, self.current_version) > 0
            self._latest_release_info = {
                "latest_version": tag_name,
                "current_version": self.current_version,
                "update_available": is_newer and (windows_asset is not None),
                "changelog": data.get("body", ""),
                "download_url": windows_asset.get("browser_download_url") if windows_asset else "",
                "asset_name": windows_asset.get("name") if windows_asset else "",
                "asset_size": windows_asset.get("size", 0) if windows_asset else 0
            }
            return self._latest_release_info

        except Exception as e:
            return {
                "update_available": False,
                "error": f"Failed to check updates: {str(e)}",
                "current_version": self.current_version
            }

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compares two semver version strings like '1.0.1' and '1.0.0'."""
        try:
            p1 = [int(x) for x in v1.split(".")]
            p2 = [int(x) for x in v2.split(".")]
            return (p1 > p2) - (p1 < p2)
        except Exception:
            return 0

    async def download_update(self, download_url: str, expected_sha256: Optional[str] = None) -> Path:
        """Downloads the update zip and verifies its checksum."""
        temp_dir = self.usb_root / ".phonetoUSB" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_path = temp_dir / "update.zip"

        hasher = hashlib.sha256()
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                with open(zip_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        hasher.update(chunk)
                        f.write(chunk)

        if expected_sha256:
            computed = hasher.hexdigest().lower()
            if computed != expected_sha256.lower():
                zip_path.unlink(missing_ok=True)
                raise ValueError("Downloaded update package failed SHA-256 integrity check")

        return zip_path

    def stage_update_and_prepare_script(self, zip_path: Path) -> Path:
        """
        Unzips the updated executable to .phonetoUSB/temp/PhoneToUSB.new.exe
        and writes a batch helper script to replace the current executable on exit.
        """
        temp_dir = self.usb_root / ".phonetoUSB" / "temp"
        extract_dir = temp_dir / "extracted_update"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Locate the new executable
        new_exe = None
        for p in extract_dir.rglob("PhoneToUSB.exe"):
            new_exe = p
            break

        if not new_exe or not new_exe.exists():
            raise FileNotFoundError("Could not find PhoneToUSB.exe in update package")

        staged_exe = temp_dir / "PhoneToUSB.new.exe"
        if staged_exe.exists():
            staged_exe.unlink()
        new_exe.replace(staged_exe)

        # Target executable path (the one currently running)
        current_exe = sys.executable if getattr(sys, "frozen", False) else (self.usb_root / "PhoneToUSB.exe")

        # Create batch script to perform the in-place replacement
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
