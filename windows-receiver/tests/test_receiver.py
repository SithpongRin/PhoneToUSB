"""
Automated unit tests for PhoneToUSB Windows Receiver.
Tests cryptographic identities, sandboxed filesystem access, path traversal prevention,
chunked streaming transfers, atomic commits, pairing tokens, and device authorization.
"""

import os
import sys
import json
import time
import shutil
import hashlib
from pathlib import Path
import pytest

# Ensure receiver src is in path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from receiver_identity import ReceiverIdentity
from usb_manager import USBManager, USBStatus
from filesystem_service import FilesystemService, SecurityViolation
from authorization_service import AuthorizationService
from pairing_service import PairingService, PAIRING_TOKEN_TTL
from transfer_service import TransferService, TransferError

@pytest.fixture
def temp_usb_dir(tmp_path):
    """Simulates a mounted USB drive root directory."""
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    # Create sample user directories
    (usb_dir / "Documents").mkdir()
    (usb_dir / "Photos").mkdir()
    (usb_dir / "Documents" / "notes.txt").write_text("Secret notes on USB", encoding="utf-8")
    return usb_dir

# ==========================================
# 1. Receiver Identity Tests
# ==========================================
def test_receiver_identity_generation_and_persistence(temp_usb_dir):
    identity1 = ReceiverIdentity.load_or_create(temp_usb_dir, friendly_name="Test Office USB")
    assert identity1.receiver_id.startswith("p2u-rcv-")
    assert len(identity1.public_key_base64) > 20
    assert identity1.friendly_name == "Test Office USB"

    # Reload from disk
    identity2 = ReceiverIdentity.load_or_create(temp_usb_dir)
    assert identity2.receiver_id == identity1.receiver_id
    assert identity2.public_key_base64 == identity1.public_key_base64

def test_receiver_digital_signature_verification(temp_usb_dir):
    identity = ReceiverIdentity.load_or_create(temp_usb_dir)
    message = b"Challenge-Nonce-2026-Security-Token"

    signature_b64 = identity.sign_base64(message)
    assert ReceiverIdentity.verify_client_signature(identity.public_key_base64, message, signature_b64) is True

    # Tampered message must fail
    tampered = b"Challenge-Nonce-2026-Security-Tampered"
    assert ReceiverIdentity.verify_client_signature(identity.public_key_base64, tampered, signature_b64) is False

# ==========================================
# 2. Filesystem Sandboxing & Traversal Prevention Tests
# ==========================================
def test_filesystem_directory_listing(temp_usb_dir):
    fs = FilesystemService(temp_usb_dir)
    listing = fs.list_directory("")
    items = listing["items"]
    names = [item["name"] for item in items]

    assert "Documents" in names
    assert "Photos" in names
    assert ".phonetoUSB" not in names  # Hidden app internal directory must not appear

def test_filesystem_path_traversal_prevention(temp_usb_dir):
    fs = FilesystemService(temp_usb_dir)

    # Attempting to climb out of root
    with pytest.raises(SecurityViolation):
        fs.sanitize_and_resolve("../../Windows/System32")

    with pytest.raises(SecurityViolation):
        fs.sanitize_and_resolve("Documents/../../../etc/passwd")

    with pytest.raises(SecurityViolation):
        fs.sanitize_and_resolve(".phonetoUSB/receiver_identity.json")

    with pytest.raises(SecurityViolation):
        fs.sanitize_and_resolve("CON.txt")

def test_filesystem_crud_operations(temp_usb_dir):
    fs = FilesystemService(temp_usb_dir)

    # Create directory
    res_mkdir = fs.create_directory("Projects/MobileApp")
    assert res_mkdir["success"] is True
    assert (temp_usb_dir / "Projects" / "MobileApp").is_dir()

    # Rename
    res_rename = fs.rename_item("Projects/MobileApp", "PhoneToUSB_Project")
    assert res_rename["success"] is True
    assert (temp_usb_dir / "Projects" / "PhoneToUSB_Project").is_dir()

    # Move
    res_move = fs.move_item("Projects/PhoneToUSB_Project", "Documents")
    assert res_move["success"] is True
    assert (temp_usb_dir / "Documents" / "PhoneToUSB_Project").is_dir()

    # Delete
    res_del = fs.delete_item("Documents/PhoneToUSB_Project", recursive=True)
    assert res_del["success"] is True
    assert not (temp_usb_dir / "Documents" / "PhoneToUSB_Project").exists()

# ==========================================
# 3. Transfer Service & Atomic Commit Tests
# ==========================================
def test_transfer_upload_streaming_and_atomic_commit(temp_usb_dir):
    usb_mgr = USBManager(override_path=temp_usb_dir)
    usb_mgr.detect_usb_root()
    fs = FilesystemService(temp_usb_dir)
    transfer_svc = TransferService(usb_mgr, fs)

    content = b"This is a large file stream transferred chunk-by-chunk to the USB drive."
    file_sha256 = hashlib.sha256(content).hexdigest()
    transfer_id = "test-transfer-uuid-1"

    # Step 1: Prepare
    prep = transfer_svc.prepare_upload(
        transfer_id=transfer_id,
        relative_path="Documents/streamed_doc.txt",
        file_size=len(content),
        expected_sha256=file_sha256,
        conflict_policy="RENAME"
    )
    assert prep["status"] == "ACCEPTED"

    # Step 2: Write Chunks
    chunk1 = content[:20]
    chunk2 = content[20:]
    transfer_svc.write_upload_chunk(transfer_id, 0, chunk1)
    transfer_svc.write_upload_chunk(transfer_id, 1, chunk2)

    # Step 3: Finish & Atomic Commit
    fin = transfer_svc.finish_upload(transfer_id)
    assert fin["status"] == "SUCCESS"

    final_file = temp_usb_dir / "Documents" / "streamed_doc.txt"
    assert final_file.exists()
    assert final_file.read_bytes() == content

def test_transfer_checksum_mismatch_purges_temp(temp_usb_dir):
    usb_mgr = USBManager(override_path=temp_usb_dir)
    usb_mgr.detect_usb_root()
    fs = FilesystemService(temp_usb_dir)
    transfer_svc = TransferService(usb_mgr, fs)

    content = b"Corrupted content"
    transfer_id = "test-transfer-corrupt"

    transfer_svc.prepare_upload(
        transfer_id=transfer_id,
        relative_path="corrupt.bin",
        file_size=len(content),
        expected_sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        conflict_policy="RENAME"
    )
    transfer_svc.write_upload_chunk(transfer_id, 0, content)

    with pytest.raises(TransferError):
        transfer_svc.finish_upload(transfer_id)

    # Temporary file must be destroyed
    part_file = temp_usb_dir / ".phonetoUSB" / "temp" / f"{transfer_id}.part"
    assert not part_file.exists()
    assert not (temp_usb_dir / "corrupt.bin").exists()

# ==========================================
# 4. Pairing & Authorization Tests
# ==========================================
def test_pairing_token_lifecycle(temp_usb_dir):
    identity = ReceiverIdentity.load_or_create(temp_usb_dir)
    pairing_svc = PairingService(identity.receiver_id, identity.public_key_base64, "ws://localhost:8000")

    token, payload = pairing_svc.generate_pairing_session()
    assert pairing_svc.is_token_valid(token) is True
    assert pairing_svc.is_token_valid("invalid-token") is False

    # Invalidate token
    pairing_svc.invalidate_token()
    assert pairing_svc.is_token_valid(token) is False

def test_authorization_service_registry(temp_usb_dir):
    auth_svc = AuthorizationService(temp_usb_dir)
    client_id = "p2u-client-android-pixel8"

    assert auth_svc.is_authorized(client_id) is False

    auth_svc.authorize_device(client_id, "mock-pubkey-base64", "My Pixel 8")
    assert auth_svc.is_authorized(client_id) is True
    assert auth_svc.get_client_pubkey(client_id) == "mock-pubkey-base64"

    # Reload from disk
    auth_svc2 = AuthorizationService(temp_usb_dir)
    assert auth_svc2.is_authorized(client_id) is True

    # Revoke
    auth_svc2.revoke_device(client_id)
    assert auth_svc2.is_authorized(client_id) is False
