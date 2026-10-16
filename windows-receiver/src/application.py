"""
Core Application Coordinator for PhoneToUSB Windows Receiver.
Orchestrates USB hardware detection, filesystem operations, cryptographic identity,
secure pairing, client dispatching, and background network signaling.
"""

import os
import sys
import json
import base64
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

try:
    from .logging_service import setup_logger, get_logger
    from .usb_manager import USBManager, USBStatus
    from .receiver_identity import ReceiverIdentity
    from .filesystem_service import FilesystemService, SecurityViolation
    from .authorization_service import AuthorizationService
    from .pairing_service import PairingService
    from .transfer_service import TransferService, TransferError
    from .signaling_client import SignalingClient
    from .update_service import UpdateService
    from .embedded_server import EmbeddedCoordinationServer
except (ImportError, ValueError):
    from logging_service import setup_logger, get_logger
    from usb_manager import USBManager, USBStatus
    from receiver_identity import ReceiverIdentity
    from filesystem_service import FilesystemService, SecurityViolation
    from authorization_service import AuthorizationService
    from pairing_service import PairingService
    from transfer_service import TransferService, TransferError
    from signaling_client import SignalingClient
    from update_service import UpdateService
    from embedded_server import EmbeddedCoordinationServer

logger = get_logger()

DEFAULT_BACKEND_URL = "ws://127.0.0.1:8000/ws/receiver"

class PhoneToUSBApp:
    def __init__(
        self,
        backend_url: str = DEFAULT_BACKEND_URL,
        usb_override_path: Optional[Path] = None,
        enable_embedded_server: bool = True
    ):
        self.backend_url = backend_url
        self.enable_embedded_server = enable_embedded_server
        self.embedded_server = EmbeddedCoordinationServer(host="0.0.0.0", port=8000)
        self.usb_manager = USBManager(override_path=usb_override_path)
        self.usb_root, self.usb_status = self.usb_manager.detect_usb_root()

        if not self.usb_root:
            logger.warning(f"USB drive not detected immediately. Status: {self.usb_status}")
            # Fallback to current working directory for initial setup if not on USB yet
            fallback_root = Path.cwd()
            self.identity = ReceiverIdentity.load_or_create(fallback_root)
            self.fs_service = FilesystemService(fallback_root)
            self.auth_service = AuthorizationService(fallback_root)
        else:
            setup_logger(self.usb_root)
            self.identity = ReceiverIdentity.load_or_create(self.usb_root)
            self.fs_service = FilesystemService(self.usb_root)
            self.auth_service = AuthorizationService(self.usb_root)

        self.pairing_service = PairingService(
            receiver_id=self.identity.receiver_id,
            receiver_pubkey_b64=self.identity.public_key_base64,
            backend_url=self.backend_url
        )
        self.transfer_service = TransferService(self.usb_manager, self.fs_service)
        self.update_service = UpdateService(self.usb_root or Path.cwd())

        # Callbacks for UI updates
        self.on_status_change_callback: Optional[Callable[[str], None]] = None
        self.on_usb_change_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_pairing_prompt_callback: Optional[Callable[[Dict[str, Any], asyncio.Future], None]] = None
        self.on_transfer_progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # If using the local port 8000 server, connect signaling client via 127.0.0.1
        # so VPNs (like Cloudflare WARP) never block local receiver registration,
        # while pairing_service advertises the LAN Wi-Fi IP in the QR code for the phone.
        signaling_url = self._resolve_signaling_url(self.backend_url)

        self.signaling_client = SignalingClient(
            backend_ws_url=signaling_url,
            identity=self.identity,
            pairing_service=self.pairing_service,
            auth_service=self.auth_service,
            on_status_change=self._handle_network_status_change,
            on_pairing_request=self._handle_pairing_prompt,
            on_data_message=self._handle_client_message
        )

        self._monitor_task: Optional[asyncio.Task] = None

    @staticmethod
    def _resolve_signaling_url(advertised_url: str) -> str:
        if ":8000" in advertised_url and advertised_url.startswith("ws://"):
            return "ws://127.0.0.1:8000/ws/receiver"
        return advertised_url

    def _handle_network_status_change(self, status: str):
        if self.on_status_change_callback:
            self.on_status_change_callback(status)

    def _handle_pairing_prompt(self, msg: Dict[str, Any], future: asyncio.Future):
        if self.on_pairing_prompt_callback:
            self.on_pairing_prompt_callback(msg, future)
        else:
            # If no GUI prompt registered, reject by default for security
            future.set_result(False)

    def _handle_client_message(self, client_id: str, msg: Dict[str, Any]):
        """Dispatches authenticated remote filesystem requests from paired Android phones."""
        asyncio.create_task(self._process_client_request(client_id, msg))

    async def _process_client_request(self, client_id: str, msg: Dict[str, Any]):
        command = msg.get("command")
        request_id = msg.get("request_id", "")
        params = msg.get("params", {})

        response: Dict[str, Any] = {
            "action": "DATA_FRAME",
            "command_response": command,
            "request_id": request_id,
            "success": False
        }

        try:
            # 1. Directory Listing
            if command == "FS_LIST":
                path = params.get("path", "")
                sort_by = params.get("sort_by", "name")
                sort_asc = params.get("sort_asc", True)
                search = params.get("search", "")
                page = params.get("page", 1)
                page_size = params.get("page_size", 200)

                result = self.fs_service.list_directory(
                    relative_path=path,
                    sort_by=sort_by,
                    sort_asc=sort_asc,
                    search_query=search,
                    page=page,
                    page_size=page_size
                )
                response.update({"success": True, "data": result})

            # 2. Create Directory
            elif command == "FS_MKDIR":
                path = params.get("path", "")
                result = self.fs_service.create_directory(path)
                response.update({"success": True, "data": result})

            # 3. Rename File / Folder
            elif command == "FS_RENAME":
                old_path = params.get("old_path", "")
                new_name = params.get("new_name", "")
                result = self.fs_service.rename_item(old_path, new_name)
                response.update({"success": True, "data": result})

            # 4. Move File / Folder
            elif command == "FS_MOVE":
                source = params.get("source", "")
                target_dir = params.get("target_dir", "")
                result = self.fs_service.move_item(source, target_dir)
                response.update({"success": True, "data": result})

            # 5. Delete File / Folder
            elif command == "FS_DELETE":
                path = params.get("path", "")
                recursive = params.get("recursive", False)
                result = self.fs_service.delete_item(path, recursive=recursive)
                response.update({"success": True, "data": result})

            # 6. Upload - Start
            elif command == "TRANSFER_START":
                transfer_id = params.get("transfer_id")
                rel_path = params.get("relative_path")
                file_size = params.get("file_size")
                sha256 = params.get("sha256")
                policy = params.get("conflict_policy", "RENAME")

                res = self.transfer_service.prepare_upload(
                    transfer_id=transfer_id,
                    relative_path=rel_path,
                    file_size=file_size,
                    expected_sha256=sha256,
                    conflict_policy=policy
                )
                response.update({"success": True, "data": res})

            # 7. Upload - Chunk
            elif command == "TRANSFER_CHUNK":
                transfer_id = params.get("transfer_id")
                chunk_index = params.get("chunk_index")
                chunk_data_b64 = params.get("chunk_data_b64", "")
                chunk_bytes = base64.b64decode(chunk_data_b64)

                res = self.transfer_service.write_upload_chunk(transfer_id, chunk_index, chunk_bytes)
                response.update({"success": True, "data": res})

                if self.on_transfer_progress_callback:
                    self.on_transfer_progress_callback(res)

            # 8. Upload - Finish
            elif command == "TRANSFER_FINISH":
                transfer_id = params.get("transfer_id")
                res = self.transfer_service.finish_upload(transfer_id)
                response.update({"success": True, "data": res})

            # 9. Upload - Cancel
            elif command == "TRANSFER_CANCEL":
                transfer_id = params.get("transfer_id")
                self.transfer_service.cancel_upload(transfer_id)
                response.update({"success": True, "data": {"status": "CANCELLED"}})

            # 10. Download - Start
            elif command == "TRANSFER_DOWNLOAD_START":
                rel_path = params.get("relative_path")
                res = self.transfer_service.prepare_download(rel_path)
                response.update({"success": True, "data": res})

            # 11. Download - Read Chunk
            elif command == "TRANSFER_DOWNLOAD_CHUNK":
                rel_path = params.get("relative_path")
                offset = params.get("offset", 0)
                length = params.get("length", 65536)

                target_file = self.fs_service.sanitize_and_resolve(rel_path)
                with open(target_file, "rb") as f:
                    f.seek(offset)
                    data_bytes = f.read(length)

                response.update({
                    "success": True,
                    "data": {
                        "offset": offset,
                        "length": len(data_bytes),
                        "chunk_data_b64": base64.b64encode(data_bytes).decode("ascii")
                    }
                })

            # 12. Storage Capacity Info
            elif command == "GET_STORAGE_INFO":
                stats = self.usb_manager.get_storage_stats()
                response.update({"success": True, "data": stats})

            else:
                response.update({"error": f"Unknown command: {command}"})

        except SecurityViolation as e:
            logger.warning(f"Security violation from client {client_id}: {e}")
            response.update({"error": f"SECURITY_VIOLATION: {str(e)}"})
        except TransferError as e:
            logger.warning(f"Transfer error: {e}")
            response.update({"error": f"TRANSFER_ERROR: {str(e)}"})
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            response.update({"error": str(e)})

        # Send response back to phone
        await self.signaling_client.send_to_client(client_id, response)

    async def start(self):
        """Starts background tasks: embedded server, USB monitor, and signaling client."""
        if self.enable_embedded_server:
            await self.embedded_server.start()
        self._monitor_task = asyncio.create_task(self._usb_monitor_loop())
        await self.signaling_client.start()

    async def stop(self):
        """Safely stops the application."""
        if self._monitor_task:
            self._monitor_task.cancel()
        self.signaling_client.stop()
        if self.enable_embedded_server:
            await self.embedded_server.stop()

    async def _usb_monitor_loop(self):
        """Periodically polls USB volume state to detect insertion or removal."""
        while True:
            try:
                await asyncio.sleep(3)
                root, status = self.usb_manager.detect_usb_root()
                if status != self.usb_status:
                    self.usb_status = status
                    self.usb_root = root
                    logger.info(f"USB status changed to: {status}")
                    if self.on_usb_change_callback:
                        self.on_usb_change_callback(self.usb_manager.get_storage_stats())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"USB monitor loop exception: {e}")
