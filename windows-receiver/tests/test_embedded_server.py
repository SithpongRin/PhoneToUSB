"""
End-to-End Integration Test for EmbeddedCoordinationServer and PhoneToUSBApp.
Verifies that a standalone Windows Receiver instance hosts its own WebSocket
coordination server, authenticates itself, handles QR pairing with explicit
approval, and serves real USB directory listings to a paired Android phone.
"""

import sys
import json
import asyncio
from pathlib import Path
import pytest
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from application import PhoneToUSBApp
from embedded_server import EmbeddedCoordinationServer


@pytest.mark.asyncio
async def test_embedded_server_pairing_and_fs_list(tmp_path):
    # Create a real file on the simulated USB drive
    sample_file = tmp_path / "hello_usb.txt"
    sample_file.write_text("Hello from USB drive!", encoding="utf-8")

    # Start EmbeddedCoordinationServer on an ephemeral test port
    port = 18765
    ws_url = f"ws://127.0.0.1:{port}/ws/client"

    app = PhoneToUSBApp(
        backend_url=ws_url,
        usb_override_path=tmp_path,
        enable_embedded_server=False
    )
    app.embedded_server = EmbeddedCoordinationServer(host="127.0.0.1", port=port)
    app.signaling_client.backend_ws_url = f"ws://127.0.0.1:{port}/ws/receiver"

    # Auto-approve pairing prompt on Windows
    def auto_approve_pairing(msg, future):
        future.set_result(True)

    app.on_pairing_prompt_callback = auto_approve_pairing

    started = await app.embedded_server.start()
    assert started is True

    app_task = asyncio.create_task(app.signaling_client.start())

    try:
        # Wait for receiver to authenticate with embedded server
        for _ in range(30):
            if app.identity.receiver_id in app.embedded_server.receivers:
                break
            await asyncio.sleep(0.1)

        assert app.identity.receiver_id in app.embedded_server.receivers

        # Generate QR pairing session
        token, qr_payload = app.pairing_service.generate_pairing_session()
        assert qr_payload["rid"] == app.identity.receiver_id
        assert qr_payload["token"] == token

        # Connect simulated Android phone client to the embedded server
        async with websockets.connect(ws_url) as phone_ws:
            await phone_ws.send(json.dumps({
                "action": "HELLO",
                "client_id": "android-test-phone-01"
            }))
            ready_raw = await asyncio.wait_for(phone_ws.recv(), timeout=5.0)
            ready_msg = json.loads(ready_raw)
            assert ready_msg.get("status") == "READY"

            # Send PAIRING_REQUEST with QR token
            pair_req_id = "req-pair-123"
            await phone_ws.send(json.dumps({
                "action": "PAIRING_REQUEST",
                "request_id": pair_req_id,
                "receiver_id": qr_payload["rid"],
                "token": qr_payload["token"],
                "client_id": "android-test-phone-01",
                "client_name": "TECNO SPARK 30C",
                "client_pubkey": "dGVzdC1wdWJrZXk="
            }))

            pair_res_raw = await asyncio.wait_for(phone_ws.recv(), timeout=5.0)
            pair_res = json.loads(pair_res_raw)
            assert pair_res["action"] == "PAIRING_RESULT"
            assert pair_res["request_id"] == pair_req_id
            assert pair_res["status"] == "APPROVED"

            # Now send FS_LIST command as the newly authorized Android phone
            fs_req_id = "req-fs-456"
            await phone_ws.send(json.dumps({
                "action": "DATA_FRAME",
                "request_id": fs_req_id,
                "receiver_id": qr_payload["rid"],
                "client_id": "android-test-phone-01",
                "command": "FS_LIST",
                "params": {"path": ""}
            }))

            fs_res_raw = await asyncio.wait_for(phone_ws.recv(), timeout=5.0)
            fs_res = json.loads(fs_res_raw)
            assert fs_res["action"] == "DATA_FRAME"
            assert fs_res["request_id"] == fs_req_id
            assert fs_res["success"] is True
            items = fs_res["data"]["items"]
            names = [item["name"] for item in items]
            assert "hello_usb.txt" in names

    finally:
        app.signaling_client.stop()
        app_task.cancel()
        await app.embedded_server.stop()
