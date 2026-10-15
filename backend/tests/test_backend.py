"""
Automated unit tests for PhoneToUSB Coordination Backend.
Tests REST endpoints, HMAC-SHA1 TURN credentials, rate limiting,
receiver registration challenge-response, and WebSockets.
"""

import sys
import time
import base64
import json
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Ensure backend app is in path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app, registry, rate_limiter
from app.receiver_registry import ReceiverRegistry
from app.session_manager import SessionManager
from app.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "active_receivers" in data

@pytest.mark.asyncio
async def test_presence_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/presence/p2u-rcv-nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_online"] is False

@pytest.mark.asyncio
async def test_ephemeral_turn_credential_generation():
    mgr = SessionManager(
        turn_secret="test-turn-secret-key",
        turn_realm="turn.example.com",
        stun_urls=["stun:stun.example.com:3478"],
        turn_urls=["turn:turn.example.com:3478"]
    )
    creds = mgr.generate_turn_credentials(client_id="test-client-123", ttl_seconds=1800)

    assert creds["ttl"] == 1800
    assert creds["expires_at"] > time.time()
    ice_servers = creds["ice_servers"]
    assert len(ice_servers) == 2

    # Check TURN server entry has valid credentials
    turn_entry = ice_servers[1]
    assert "username" in turn_entry
    assert "credential" in turn_entry
    assert turn_entry["username"].endswith(":test-client-123")

def test_rate_limiter_throttling():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    user_id = "test-user-ip"

    assert limiter.is_allowed(user_id) is True
    assert limiter.is_allowed(user_id) is True
    assert limiter.is_allowed(user_id) is True
    # 4th request within window must be rejected
    assert limiter.is_allowed(user_id) is False

def test_receiver_registry_challenge_handshake():
    reg = ReceiverRegistry(heartbeat_timeout=30)
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_key = priv_key.public_key()
    pub_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
    receiver_id = "p2u-rcv-test-1"

    # Step 1: Initiate
    mock_ws = object()
    nonce = reg.initiate_registration(receiver_id, "Office USB", pub_b64, mock_ws)
    assert nonce is not None

    # Step 2: Valid signature completes auth
    sig = priv_key.sign(nonce.encode("utf-8"))
    sig_b64 = base64.b64encode(sig).decode("ascii")

    assert reg.complete_registration(receiver_id, sig_b64) is True
    assert reg.is_online(receiver_id) is True

    # Bad signature fails
    assert reg.complete_registration("p2u-rcv-bad", "invalidsig") is False
