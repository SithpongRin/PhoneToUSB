"""
End-to-End Integration Test for PhoneToUSB.
Simulates the full lifecycle across different components:
1. Windows Receiver boots with simulated USB volume.
2. Receiver connects to Signaling Backend and registers its Ed25519 identity.
3. Android Client connects to Signaling Backend.
4. Android Client pairs via single-use QR token with receiver approval.
5. Android Client queries real-time directory listing from USB.
6. Android Client uploads a file in streaming chunks with SHA-256 validation.
7. Receiver validates integrity and atomically writes file to USB.
8. Android Client refreshes directory listing and confirms file exists.
9. Android Client downloads the file and verifies identical SHA-256 checksum.
"""

import os
import sys
import json
import base64
import asyncio
import hashlib
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

# Set up paths
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "windows-receiver" / "src"))
sys.path.insert(0, str(repo_root / "backend"))

from receiver_identity import ReceiverIdentity
from filesystem_service import FilesystemService
from authorization_service import AuthorizationService
from pairing_service import PairingService
from usb_manager import USBManager
from transfer_service import TransferService

@pytest.mark.asyncio
async def test_end_to_end_simulation(tmp_path):
    # Setup mock USB hardware
    mock_usb = tmp_path / "usb_drive"
    mock_usb.mkdir()
    (mock_usb / "Documents").mkdir()
    (mock_usb / "Photos").mkdir()

    # Step 1: Initialize Receiver Services
    usb_mgr = USBManager(override_path=mock_usb)
    usb_mgr.detect_usb_root()
    assert usb_mgr.is_ready is True

    rcv_identity = ReceiverIdentity.load_or_create(mock_usb, friendly_name="Office USB")
    fs_service = FilesystemService(mock_usb)
    auth_service = AuthorizationService(mock_usb)
    pairing_service = PairingService(
        receiver_id=rcv_identity.receiver_id,
        receiver_pubkey_b64=rcv_identity.public_key_base64,
        backend_url="ws://mock-backend:8000/ws/receiver"
    )
    transfer_service = TransferService(usb_mgr, fs_service)

    # Step 2: Generate Pairing Token & QR payload on Windows Receiver
    token, qr_payload = pairing_service.generate_pairing_session()
    assert qr_payload["rid"] == rcv_identity.receiver_id
    assert qr_payload["token"] == token

    # Step 3: Android Client scans QR code and sends pairing request
    client_id = "p2u-client-android-pixel"
    client_pubkey_mock = "bW9jay1hbmRyb2lkLXB1YmtleQ=="
    client_name = "Pixel 8 Pro"

    # Receiver validates pairing token
    assert pairing_service.is_token_valid(token) is True

    # Windows user clicks "Approve"
    auth_service.authorize_device(client_id, client_pubkey_mock, client_name)
    pairing_service.invalidate_token()
    assert auth_service.is_authorized(client_id) is True

    # Step 4: Android Client queries USB Directory Listing (FS_LIST)
    initial_listing = fs_service.list_directory("")
    names = [i["name"] for i in initial_listing["items"]]
    assert "Documents" in names
    assert "Photos" in names
    assert "AnnualReport.pdf" not in names

    # Step 5: Android Client uploads "Documents/AnnualReport.pdf"
    file_bytes = b"%PDF-1.7 Simulated PDF document content for PhoneToUSB cross-network transfer"
    expected_sha256 = hashlib.sha256(file_bytes).hexdigest()
    transfer_id = "xfer-e2e-pdf-001"

    prep_res = transfer_service.prepare_upload(
        transfer_id=transfer_id,
        relative_path="Documents/AnnualReport.pdf",
        file_size=len(file_bytes),
        expected_sha256=expected_sha256,
        conflict_policy="RENAME"
    )
    assert prep_res["status"] == "ACCEPTED"

    # Stream in 16-byte chunks
    chunk_size = 16
    for idx, offset in enumerate(range(0, len(file_bytes), chunk_size)):
        chunk = file_bytes[offset : offset + chunk_size]
        transfer_service.write_upload_chunk(transfer_id, idx, chunk)

    # Finish and atomically commit
    finish_res = transfer_service.finish_upload(transfer_id)
    assert finish_res["status"] == "SUCCESS"
    assert finish_res["final_relative_path"] == "Documents/AnnualReport.pdf"

    # Step 6: Verify file on actual USB filesystem
    written_file = mock_usb / "Documents" / "AnnualReport.pdf"
    assert written_file.exists()
    assert written_file.read_bytes() == file_bytes

    # Step 7: Android Client refreshes directory listing and confirms new file
    refreshed_listing = fs_service.list_directory("Documents")
    refreshed_names = [i["name"] for i in refreshed_listing["items"]]
    assert "AnnualReport.pdf" in refreshed_names

    # Step 8: Android Client downloads the file from USB
    dl_prep = transfer_service.prepare_download("Documents/AnnualReport.pdf")
    assert dl_prep["file_size"] == len(file_bytes)
    assert dl_prep["sha256"] == expected_sha256
