# -*- coding: utf-8 -*-
"""
Automated Comprehensive Security Test Suite for PhoneToUSB
Covers 25 Real Security Scenarios:
1. Missing USB detection / rejected transfer
2. USB disconnected during active transfer
3. Reconnecting a USB drive and resuming normal operation
4. Path traversal attempt using ../ and ..\\
5. Absolute path injection
6. Dangerous file names (reserved Windows names, control characters, trailing dots/spaces)
7. Symlink / junction resolution outside the target directory
8. File overwrite protection
9. Upload of zero-byte file
10. Upload exceeding the configured file size limit
11. Partial / interrupted upload cleanup (.part file removal)
12. Valid 6-digit PIN verification
13. Invalid 6-digit PIN rejection
14. Brute-force PIN rate limiting / lockout
15. QR code rotation and old QR expiration
16. Valid share link access
17. Expired share link rejection
18. Revoked or invalidated share link
19. Share link attempting to access an unrelated file
20. Upload-only link attempting to list or delete files
21. Local-only endpoint rejected when accessed remotely
22. Auto-update URL outside trusted GitHub repository rejected
23. Auto-update with untrusted binary name rejected
24. Safe process shutdown without killing unrelated processes
25. Direct API request without valid session / code rejected
"""

import os
import sys
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


class PhoneToUSBSecurityTestCase(unittest.TestCase):
    def setUp(self):
        app.app.config["TESTING"] = True
        app.app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.app.test_client()
        self.temp_usb_dir = tempfile.mkdtemp(prefix="mock_usb_")
        self.temp_outside_dir = tempfile.mkdtemp(prefix="mock_outside_")

        # Clear verify attempts before each test
        app.clear_verify_attempts("192.168.1.100")
        app.clear_verify_attempts("127.0.0.1")

    def tearDown(self):
        shutil.rmtree(self.temp_usb_dir, ignore_errors=True)
        shutil.rmtree(self.temp_outside_dir, ignore_errors=True)

    def mock_storage_connected(self):
        return {
            "upload_dir": self.temp_usb_dir,
            "folder_name": "PhoneToUSB",
            "usb_found": True,
            "need_selection": False,
            "usb_count": 1,
            "usbs": [{"drive": "E:", "display": "Mock USB (E:)", "free_space": "10 GB", "total_space": "16 GB"}],
            "active_drive": "E:",
            "drive_label": "Mock USB (E:)",
            "free_space": "10 GB",
            "total_space": "16 GB",
            "message": "Connected to Mock USB (E:)",
        }

    def mock_storage_disconnected(self):
        return {
            "upload_dir": "",
            "folder_name": "PhoneToUSB",
            "usb_found": False,
            "need_selection": False,
            "usb_count": 0,
            "usbs": [],
            "active_drive": None,
            "drive_label": "No USB Drive Detected",
            "free_space": "0 B",
            "total_space": "0 B",
            "message": "No USB flash drive detected. Please connect a USB drive to transfer files.",
        }

    # 1. Missing USB detection / rejected transfer
    @patch("app.resolve_storage")
    def test_01_missing_usb_detection_rejected_transfer(self, mock_res):
        mock_res.return_value = self.mock_storage_disconnected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        data = {"file": (BytesIO(b"sample content"), "test.txt")}
        resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b"Transfer Blocked", resp.data)

    # 2. USB disconnected during active transfer
    @patch("app.resolve_storage")
    def test_02_usb_disconnected_during_active_transfer(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        # Simulate I/O error during writing to USB
        with patch("builtins.open", side_effect=OSError(1117, "The request could not be performed because of an I/O device error.")):
            data = {"file": (BytesIO(b"data to write"), "test.txt")}
            resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 500)
            self.assertIn(b"Cannot write to USB drive", resp.data)

    # 3. Reconnecting a USB drive and resuming normal operation
    @patch("app.resolve_storage")
    def test_03_reconnecting_usb_resumes_normal_operation(self, mock_res):
        # Step A: Disconnected
        mock_res.return_value = self.mock_storage_disconnected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        resp_dis = self.client.post("/upload", data={"file": (BytesIO(b"abc"), "abc.txt")}, content_type="multipart/form-data")
        self.assertEqual(resp_dis.status_code, 403)

        # Step B: Reconnected
        mock_res.return_value = self.mock_storage_connected()
        resp_conn = self.client.post("/upload", data={"file": (BytesIO(b"hello world"), "hello.txt")}, content_type="multipart/form-data")
        self.assertEqual(resp_conn.status_code, 200)
        self.assertTrue(resp_conn.json["ok"])
        self.assertTrue(os.path.isfile(os.path.join(self.temp_usb_dir, "hello.txt")))

    # 4. Path traversal attempt using ../ and ..\\
    @patch("app.resolve_storage")
    def test_04_path_traversal_attempt(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()

        # Direct safe_usb_resolve tests
        target, err, code = app.safe_usb_resolve("../../boot.ini")
        self.assertIsNone(target)
        self.assertEqual(code, 403)

        target, err, code = app.safe_usb_resolve("..\\..\\windows\\system32\\cmd.exe")
        self.assertIsNone(target)
        self.assertEqual(code, 403)

    # 5. Absolute path injection
    @patch("app.resolve_storage")
    def test_05_absolute_path_injection(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()

        target, err, code = app.safe_usb_resolve(r"C:\Windows\System32\calc.exe")
        self.assertIsNone(target)
        self.assertEqual(code, 403)

    # 6. Dangerous file names (reserved Windows names, control characters, trailing dots/spaces)
    def test_06_dangerous_file_names(self):
        self.assertEqual(app.clean_filename("CON.txt"), "safe_CON.txt")
        self.assertEqual(app.clean_filename("prn"), "safe_prn")
        self.assertEqual(app.clean_filename("aux.png"), "safe_aux.png")
        self.assertEqual(app.clean_filename("nul"), "safe_nul")
        self.assertEqual(app.clean_filename("com1.zip"), "safe_com1.zip")
        self.assertEqual(app.clean_filename("lpt1.log"), "safe_lpt1.log")
        self.assertEqual(app.clean_filename("hello\x00world.txt"), "hello_world.txt")
        self.assertEqual(app.clean_filename("my_document...   "), "my_document")
        self.assertTrue(app.clean_filename("").startswith("file_"))

    # 7. Symlink / junction resolution outside the target directory
    @patch("app.resolve_storage")
    def test_07_symlink_outside_target_directory(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        outside_file = os.path.join(self.temp_outside_dir, "secret.txt")
        with open(outside_file, "w") as f:
            f.write("sensitive content")

        symlink_target = os.path.join(self.temp_usb_dir, "symlink_test.txt")
        try:
            os.symlink(outside_file, symlink_target)
            target, err, code = app.safe_usb_resolve("symlink_test.txt")
            self.assertIsNone(target)
            self.assertEqual(code, 403)
        except (OSError, NotImplementedError):
            # In case Windows unprivileged symlink creation is restricted, test containment logic
            with patch("os.path.realpath") as mock_real:
                mock_real.return_value = outside_file
                target, err, code = app.safe_usb_resolve("symlink_test.txt")
                self.assertIsNone(target)
                self.assertEqual(code, 403)

    # 8. File overwrite protection
    def test_08_file_overwrite_protection(self):
        f1 = os.path.join(self.temp_usb_dir, "data.txt")
        with open(f1, "w") as f:
            f.write("original")

        name2, path2 = app.unique_destination(self.temp_usb_dir, "data.txt")
        self.assertNotEqual(path2, f1)
        self.assertTrue(name2.startswith("data_"))
        self.assertTrue(name2.endswith(".txt"))

    # 9. Upload of zero-byte file
    @patch("app.resolve_storage")
    def test_09_upload_zero_byte_file(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        data = {"file": (BytesIO(b""), "empty.txt")}
        resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json["ok"])
        saved_file = os.path.join(self.temp_usb_dir, resp.json["saved_name"])
        self.assertTrue(os.path.isfile(saved_file))
        self.assertEqual(os.path.getsize(saved_file), 0)

    # 10. Upload exceeding configured file size limit
    @patch("app.resolve_storage")
    def test_10_upload_exceeding_file_size_limit(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        orig_max = app.MAX_FILE_SIZE
        try:
            app.MAX_FILE_SIZE = 50  # 50 bytes maximum
            data = {"file": (BytesIO(b"A" * 120), "big.txt")}
            resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
            self.assertEqual(resp.status_code, 413)
        finally:
            app.MAX_FILE_SIZE = orig_max

    # 11. Partial / interrupted upload cleanup (.part file removal)
    @patch("app.resolve_storage")
    def test_11_partial_upload_cleanup(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        with self.client.session_transaction() as sess:
            sess["verified_code"] = app.ACCESS_CODE

        orig_max = app.MAX_FILE_SIZE
        try:
            app.MAX_FILE_SIZE = 30
            data = {"file": (BytesIO(b"X" * 100), "interrupted.txt")}
            self.client.post("/upload", data=data, content_type="multipart/form-data")
            # Verify no .part file remains
            part_files = [f for f in os.listdir(self.temp_usb_dir) if f.endswith(".part")]
            self.assertEqual(len(part_files), 0)
        finally:
            app.MAX_FILE_SIZE = orig_max

    # 12. Valid 6-digit PIN verification
    def test_12_valid_pin_verification(self):
        state = app.check_and_rotate_state()
        code = state["access_code"]
        resp = self.client.post("/api/verify-code", json={"code": code}, environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json["ok"])

    # 13. Invalid 6-digit PIN rejection
    def test_13_invalid_pin_rejection(self):
        resp = self.client.post("/api/verify-code", json={"code": "000000"}, environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json["ok"])

    # 14. Brute-force PIN rate limiting / lockout
    def test_14_brute_force_pin_rate_limiting(self):
        client_ip = "192.168.1.100"
        app.clear_verify_attempts(client_ip)

        for _ in range(5):
            resp = self.client.post("/api/verify-code", json={"code": "999999"}, environ_base={"REMOTE_ADDR": client_ip})
            self.assertIn(resp.status_code, (401, 429))

        # 6th attempt must be locked out with 429
        resp6 = self.client.post("/api/verify-code", json={"code": "999999"}, environ_base={"REMOTE_ADDR": client_ip})
        self.assertEqual(resp6.status_code, 429)
        self.assertIn("Locked out", resp6.json["error"])

    # 15. QR code rotation and old QR expiration
    def test_15_qr_rotation_and_old_qr_expiration(self):
        s1 = app.check_and_rotate_state(force_qr=True)
        qr1 = s1["qr_id"]

        # Rotate to new QR
        s2 = app.check_and_rotate_state(force_qr=True)
        qr2 = s2["qr_id"]
        self.assertNotEqual(qr1, qr2)

        # Old QR is accepted during grace period
        resp_grace = self.client.get(f"/?q={qr1}")
        self.assertEqual(resp_grace.status_code, 302)

        # Expire previous QR
        with app.STATE_LOCK:
            app.PREVIOUS_QR_EXPIRE = time.time() - 10

        # Old QR now fails to auto-login
        with self.client.session_transaction() as sess:
            sess.clear()
        resp_expired = self.client.get(f"/?q={qr1}")
        self.assertEqual(resp_expired.status_code, 200)  # Renders login page, not redirect

    # 16. Valid share link access
    @patch("app.resolve_storage")
    def test_16_valid_share_link_access(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        file_path = os.path.join(self.temp_usb_dir, "shared_doc.txt")
        with open(file_path, "w") as f:
            f.write("shared content")

        token, _ = app.create_share_link_token(minutes_valid=30, file_target="shared_doc.txt", scope="file")
        resp = self.client.get(f"/download/shared_doc.txt?link={token}", environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"shared content")

    # 17. Expired share link rejection
    @patch("app.resolve_storage")
    def test_17_expired_share_link_rejection(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        file_path = os.path.join(self.temp_usb_dir, "expired.txt")
        with open(file_path, "w") as f:
            f.write("content")

        token, _ = app.create_share_link_token(minutes_valid=1, file_target="expired.txt", scope="file")
        # Expire token
        with app.STATE_LOCK:
            app.GENERATED_LINKS[token]["expire_at"] = time.time() - 10

        resp = self.client.get(f"/download/expired.txt?link={token}", environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 401)

    # 18. Revoked or invalidated share link
    @patch("app.resolve_storage")
    def test_18_revoked_share_link(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        file_path = os.path.join(self.temp_usb_dir, "revoked.txt")
        with open(file_path, "w") as f:
            f.write("secret data")

        token, _ = app.create_share_link_token(minutes_valid=30, file_target="revoked.txt", scope="file")
        app.revoke_share_link_token(token)

        resp = self.client.get(f"/download/revoked.txt?link={token}", environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 401)

    # 19. Share link attempting to access an unrelated file
    @patch("app.resolve_storage")
    def test_19_share_link_attempting_to_access_unrelated_file(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        file_a = os.path.join(self.temp_usb_dir, "file_a.txt")
        file_b = os.path.join(self.temp_usb_dir, "file_b.txt")
        with open(file_a, "w") as f:
            f.write("file A")
        with open(file_b, "w") as f:
            f.write("file B")

        token, _ = app.create_share_link_token(minutes_valid=30, file_target="file_a.txt", scope="file")

        # Try to access unrelated file_b with token of file_a
        resp = self.client.get(f"/download/file_b.txt?link={token}", environ_base={"REMOTE_ADDR": "192.168.1.100"})
        self.assertEqual(resp.status_code, 401)

    # 20. Upload-only link attempting to list or delete files
    @patch("app.resolve_storage")
    def test_20_upload_only_link_attempting_to_list_or_delete_files(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        file_target = os.path.join(self.temp_usb_dir, "test_del.txt")
        with open(file_target, "w") as f:
            f.write("delete candidate")

        remote_env = {"REMOTE_ADDR": "192.168.1.100"}
        with self.client.session_transaction() as sess:
            sess["can_upload_only"] = True

        # Attempt to list files -> 401
        resp_list = self.client.get("/api/files", environ_base=remote_env)
        self.assertEqual(resp_list.status_code, 401)

        # Attempt to delete file -> 401
        resp_del = self.client.post("/delete/test_del.txt", environ_base=remote_env)
        self.assertEqual(resp_del.status_code, 401)

        # But upload must succeed
        data = {"file": (BytesIO(b"upload only content"), "upl.txt")}
        resp_upl = self.client.post("/upload", data=data, content_type="multipart/form-data", environ_base=remote_env)
        self.assertEqual(resp_upl.status_code, 200)

    # 21. Local-only endpoint rejected when accessed remotely
    def test_21_local_only_endpoint_rejected_remotely(self):
        remote_env = {"REMOTE_ADDR": "192.168.1.99"}

        resp_qr = self.client.get("/qr", environ_base=remote_env)
        self.assertEqual(resp_qr.status_code, 403)

        resp_update = self.client.post("/api/apply-update", json={"download_url": "https://example.com"}, environ_base=remote_env)
        self.assertEqual(resp_update.status_code, 403)

        resp_shutdown = self.client.post("/api/shutdown", environ_base=remote_env)
        self.assertEqual(resp_shutdown.status_code, 403)

    # 22. Auto-update URL outside trusted GitHub repository rejected
    def test_22_auto_update_untrusted_repository_url_rejected(self):
        local_env = {"REMOTE_ADDR": "127.0.0.1"}
        payload = {"download_url": "https://malicious-site.com/payload/USB_Transfer.exe"}
        resp = self.client.post("/api/apply-update", json=payload, environ_base=local_env)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Untrusted update source", resp.json["error"])

    # 23. Auto-update with untrusted binary name rejected
    def test_23_auto_update_untrusted_binary_name_rejected(self):
        local_env = {"REMOTE_ADDR": "127.0.0.1"}
        payload = {"download_url": "https://github.com/SithpongRin/PhoneToUSB/releases/download/v1.1.0/backdoor.bat"}
        resp = self.client.post("/api/apply-update", json=payload, environ_base=local_env)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Untrusted binary filename", resp.json["error"])

    # 24. Safe process shutdown without killing unrelated processes
    def test_24_safe_process_shutdown_no_unrelated_process_killing(self):
        # Read the updater code in app.py to verify no wildcard python process kills exist
        with open("app.py", "r", encoding="utf-8") as f:
            code = f.read()

        self.assertNotIn("taskkill /F /IM pythonw.exe", code)
        self.assertNotIn("taskkill /F /IM python.exe", code)

    # 25. Direct API request without valid session / code rejected
    @patch("app.resolve_storage")
    def test_25_direct_api_request_without_session_rejected(self, mock_res):
        mock_res.return_value = self.mock_storage_connected()
        remote_env = {"REMOTE_ADDR": "192.168.1.100"}

        # Attempt to list files without auth
        resp_files = self.client.get("/api/files", environ_base=remote_env)
        self.assertEqual(resp_files.status_code, 401)

        # Attempt to upload without auth
        data = {"file": (BytesIO(b"unauthed"), "test.txt")}
        resp_upload = self.client.post("/upload", data=data, content_type="multipart/form-data", environ_base=remote_env)
        self.assertEqual(resp_upload.status_code, 401)

        # Attempt to delete without auth
        resp_del = self.client.post("/delete/test.txt", environ_base=remote_env)
        self.assertEqual(resp_del.status_code, 401)


if __name__ == "__main__":
    unittest.main()
