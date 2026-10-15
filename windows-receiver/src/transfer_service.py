"""
Transfer Service for PhoneToUSB Windows Receiver.
Manages chunked streaming uploads and downloads, incremental SHA-256 validation,
atomic commits via .part files, and USB removal guards.
"""

import os
import json
import time
import hashlib
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable

try:
    from .filesystem_service import FilesystemService, SecurityViolation
    from .usb_manager import USBManager, USBStatus
except (ImportError, ValueError):
    from filesystem_service import FilesystemService, SecurityViolation
    from usb_manager import USBManager, USBStatus

class TransferError(Exception):
    pass

class TransferService:
    def __init__(self, usb_manager: USBManager, fs_service: FilesystemService):
        self.usb_manager = usb_manager
        self.fs_service = fs_service
        self._active_uploads: Dict[str, Dict[str, Any]] = {}
        self._active_downloads: Dict[str, Dict[str, Any]] = {}
        self.history_file = fs_service.usb_root / ".phonetoUSB" / "transfer_history.json"
        self._history: list = []
        self._load_history()

    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
            except Exception:
                self._history = []

    def _save_history(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self._history[-200:], f, indent=2)  # Keep last 200 items
        except Exception:
            pass

    def record_history(self, transfer_id: str, direction: str, filename: str, size: int, status: str, error: str = ""):
        entry = {
            "transfer_id": transfer_id,
            "direction": direction,
            "filename": filename,
            "size": size,
            "status": status,
            "error": error,
            "timestamp": int(time.time())
        }
        self._history.append(entry)
        self._save_history()

    def prepare_upload(
        self,
        transfer_id: str,
        relative_path: str,
        file_size: int,
        expected_sha256: str,
        conflict_policy: str = "RENAME"
    ) -> Dict[str, Any]:
        """
        Validates target destination, ensures USB is writable with sufficient free space,
        and initializes the temporary .part file.
        """
        if not self.usb_manager.is_ready:
            raise TransferError("USB volume is not ready or has been ejected")

        # Sanitize target path
        target_path = self.fs_service.sanitize_and_resolve(relative_path)
        target_dir = target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        # Check free disk space
        stats = self.usb_manager.get_storage_stats()
        if stats.get("free_bytes", 0) < (file_size + 10 * 1024 * 1024):  # 10MB safety margin
            raise TransferError("Insufficient USB storage space")

        temp_dir = self.fs_service.usb_root / ".phonetoUSB" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        part_file = temp_dir / f"{transfer_id}.part"

        # Open file for binary writing
        file_handle = open(part_file, "wb")

        self._active_uploads[transfer_id] = {
            "transfer_id": transfer_id,
            "relative_path": relative_path,
            "target_path": target_path,
            "file_size": file_size,
            "expected_sha256": expected_sha256.lower(),
            "conflict_policy": conflict_policy,
            "part_file": part_file,
            "file_handle": file_handle,
            "hasher": hashlib.sha256(),
            "bytes_written": 0,
            "chunks_received": 0,
            "start_time": time.time()
        }

        return {
            "transfer_id": transfer_id,
            "status": "ACCEPTED",
            "allocated_temp": str(part_file.name)
        }

    def write_upload_chunk(self, transfer_id: str, chunk_index: int, chunk_bytes: bytes) -> Dict[str, Any]:
        """Writes a chunk of bytes to the temporary file and updates SHA-256."""
        if not self.usb_manager.is_ready:
            self.cancel_upload(transfer_id, "USB volume was unmounted during transfer")
            raise TransferError("USB hardware disconnected")

        upload = self._active_uploads.get(transfer_id)
        if not upload:
            raise TransferError(f"No active upload found for transfer_id: {transfer_id}")

        handle = upload["file_handle"]
        handle.write(chunk_bytes)
        handle.flush()

        upload["hasher"].update(chunk_bytes)
        upload["bytes_written"] += len(chunk_bytes)
        upload["chunks_received"] += 1

        return {
            "transfer_id": transfer_id,
            "chunks_received": upload["chunks_received"],
            "bytes_written": upload["bytes_written"]
        }

    def finish_upload(self, transfer_id: str) -> Dict[str, Any]:
        """
        Validates total length and SHA-256 checksum, then atomically commits
        the .part file to its final destination on the USB drive.
        """
        upload = self._active_uploads.get(transfer_id)
        if not upload:
            raise TransferError("Upload session not found")

        handle = upload["file_handle"]
        handle.close()

        part_file = upload["part_file"]
        computed_sha256 = upload["hasher"].hexdigest().lower()

        # Integrity Check
        if upload["bytes_written"] != upload["file_size"]:
            part_file.unlink(missing_ok=True)
            del self._active_uploads[transfer_id]
            self.record_history(transfer_id, "UPLOAD", upload["relative_path"], upload["file_size"], "FAILED", "Size mismatch")
            raise TransferError(f"File size mismatch: expected {upload['file_size']}, got {upload['bytes_written']}")

        if computed_sha256 != upload["expected_sha256"]:
            part_file.unlink(missing_ok=True)
            del self._active_uploads[transfer_id]
            self.record_history(transfer_id, "UPLOAD", upload["relative_path"], upload["file_size"], "FAILED", "SHA-256 mismatch")
            raise TransferError(f"Integrity check failed: SHA-256 mismatch")

        # Conflict Resolution
        target_path = upload["target_path"]
        policy = upload["conflict_policy"]

        if target_path.exists():
            if policy == "RENAME":
                target_path = self._resolve_unique_name(target_path)
            elif policy == "SKIP":
                part_file.unlink(missing_ok=True)
                del self._active_uploads[transfer_id]
                return {"status": "SKIPPED", "relative_path": upload["relative_path"]}
            # If OVERWRITE, proceed to overwrite

        # Atomic commit
        shutil.move(str(part_file), str(target_path))
        del self._active_uploads[transfer_id]

        final_rel = str(target_path.relative_to(self.fs_service.user_root)).replace("\\", "/")
        self.record_history(transfer_id, "UPLOAD", final_rel, upload["file_size"], "SUCCESS")

        return {
            "transfer_id": transfer_id,
            "status": "SUCCESS",
            "final_relative_path": final_rel,
            "sha256": computed_sha256
        }

    def cancel_upload(self, transfer_id: str, reason: str = "User cancelled"):
        upload = self._active_uploads.pop(transfer_id, None)
        if upload:
            try:
                upload["file_handle"].close()
            except Exception:
                pass
            upload["part_file"].unlink(missing_ok=True)
            self.record_history(transfer_id, "UPLOAD", upload["relative_path"], upload["file_size"], "CANCELLED", reason)

    def prepare_download(self, relative_path: str, chunk_size: int = 65536) -> Dict[str, Any]:
        """Prepares a file for download from the USB to the phone."""
        if not self.usb_manager.is_ready:
            raise TransferError("USB volume not ready")

        file_path = self.fs_service.sanitize_and_resolve(relative_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")

        file_size = file_path.stat().st_size

        # Compute SHA-256 in chunks to avoid memory spikes
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        file_sha256 = hasher.hexdigest()

        return {
            "relative_path": relative_path,
            "filename": file_path.name,
            "file_size": file_size,
            "sha256": file_sha256,
            "chunk_size": chunk_size,
            "total_chunks": (file_size + chunk_size - 1) // chunk_size if file_size > 0 else 0
        }

    def _resolve_unique_name(self, path: Path) -> Path:
        parent = path.parent
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while path.exists():
            path = parent / f"{stem} ({counter}){suffix}"
            counter += 1
        return path

    def get_history(self) -> list:
        return list(reversed(self._history))
