"""
Main FastAPI Application for PhoneToUSB Coordination Backend.
Provides WebSockets for receivers and clients, REST endpoints for presence and TURN credentials,
and health monitoring.
"""

import os
import json
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .configuration import settings
from .receiver_registry import ReceiverRegistry
from .session_manager import SessionManager
from .pairing_coordinator import PairingCoordinator
from .signaling_service import SignalingService
from .rate_limiter import RateLimiter

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("PhoneToUSB.Backend")

app = FastAPI(
    title="PhoneToUSB Coordination Service",
    description="Signaling, presence, and pairing coordination service for secure remote USB access",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core service singletons
registry = ReceiverRegistry(heartbeat_timeout=settings.RECEIVER_HEARTBEAT_TIMEOUT_SEC)
rate_limiter = RateLimiter(max_requests=settings.MAX_PAIRING_ATTEMPTS_PER_MIN, window_seconds=60)
ip_rate_limiter = RateLimiter(max_requests=settings.MAX_CONNECTIONS_PER_IP, window_seconds=60)

stun_urls = [s.strip() for s in settings.STUN_SERVERS.split(",") if s.strip()]
turn_urls = [s.strip() for s in settings.TURN_SERVERS.split(",") if s.strip()]
session_manager = SessionManager(
    turn_secret=settings.TURN_SECRET,
    turn_realm=settings.TURN_REALM,
    stun_urls=stun_urls,
    turn_urls=turn_urls
)

pairing_coordinator = PairingCoordinator(registry, rate_limiter)
signaling_service = SignalingService(registry)

# Map of active client WebSocket connections: client_id -> WebSocket
connected_clients: Dict[str, WebSocket] = {}

# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker / load balancers."""
    return {
        "status": "healthy",
        "service": "phonetousb-coordination",
        "version": "1.0.0",
        "active_receivers": registry.active_count(),
        "active_clients": len(connected_clients)
    }

@app.get("/api/v1/presence/{receiver_id}")
async def check_receiver_presence(receiver_id: str):
    """Returns whether a specific USB receiver is online."""
    online = registry.is_online(receiver_id)
    session = registry.get_session(receiver_id)
    return {
        "receiver_id": receiver_id,
        "is_online": online,
        "friendly_name": session.friendly_name if session else None
    }

class TurnRequest(BaseModel):
    client_id: str
    ttl: int = 3600

@app.post("/api/v1/turn-credentials")
async def get_turn_credentials(req: TurnRequest):
    """Issues ephemeral, short-lived TURN credentials for WebRTC relay."""
    creds = session_manager.generate_turn_credentials(req.client_id, ttl_seconds=req.ttl)
    return creds

# ==========================================
# WebSocket: Windows Receiver Endpoint
# ==========================================

@app.websocket("/ws/receiver")
async def receiver_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    receiver_id: str = ""

    try:
        # Step 1: Registration Handshake
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        if msg.get("action") != "REGISTER_RECEIVER":
            await websocket.send_text(json.dumps({"error": "Expected REGISTER_RECEIVER"}))
            await websocket.close()
            return

        receiver_id = msg.get("receiver_id")
        friendly_name = msg.get("friendly_name", "PhoneToUSB Drive")
        pubkey_b64 = msg.get("public_key")

        # Send challenge
        nonce = registry.initiate_registration(receiver_id, friendly_name, pubkey_b64, websocket)
        await websocket.send_text(json.dumps({"action": "CHALLENGE", "nonce": nonce}))

        # Step 2: Auth Response
        auth_raw = await websocket.receive_text()
        auth_msg = json.loads(auth_raw)
        sig_b64 = auth_msg.get("signature")

        if not registry.complete_registration(receiver_id, sig_b64):
            await websocket.send_text(json.dumps({"status": "AUTH_FAILED"}))
            await websocket.close()
            return

        await websocket.send_text(json.dumps({"status": "AUTHENTICATED", "receiver_id": receiver_id}))
        logger.info(f"Receiver '{friendly_name}' ({receiver_id}) connected and authenticated.")

        # Step 3: Message Loop
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "HEARTBEAT":
                registry.update_heartbeat(receiver_id)
            elif action in ("PAIRING_RESULT", "SDP_ANSWER", "ICE_CANDIDATE", "DATA_FRAME"):
                await signaling_service.route_receiver_to_client(receiver_id, msg, connected_clients)

    except WebSocketDisconnect:
        logger.info(f"Receiver {receiver_id} disconnected.")
    except Exception as e:
        logger.warning(f"Receiver socket error: {e}")
    finally:
        if receiver_id:
            registry.remove_receiver(receiver_id)

# ==========================================
# WebSocket: Android Mobile Client Endpoint
# ==========================================

@app.websocket("/ws/client")
async def client_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id: str = ""
    client_ip = websocket.client.host if websocket.client else "unknown"

    if not ip_rate_limiter.is_allowed(client_ip):
        await websocket.send_text(json.dumps({"error": "RATE_LIMIT_EXCEEDED"}))
        await websocket.close()
        return

    try:
        # Step 1: Hello from client
        raw = await websocket.receive_text()
        msg = json.loads(raw)

        client_id = msg.get("client_id", "")
        if not client_id:
            await websocket.close()
            return

        connected_clients[client_id] = websocket
        await websocket.send_text(json.dumps({"status": "READY", "client_id": client_id}))

        # Step 2: Client Message Loop
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "QUERY_PRESENCE":
                receiver_ids = msg.get("receiver_ids", [])
                presence_map = {}
                for rid in receiver_ids:
                    presence_map[rid] = registry.is_online(rid)
                await websocket.send_text(json.dumps({
                    "action": "PRESENCE_RESPONSE",
                    "presence": presence_map
                }))

            elif action == "PAIRING_REQUEST":
                await pairing_coordinator.forward_pairing_request(websocket, msg, client_ip)

            elif action in ("SDP_OFFER", "ICE_CANDIDATE", "DATA_FRAME"):
                await signaling_service.route_client_to_receiver(client_id, msg, websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Client socket error: {e}")
    finally:
        if client_id:
            connected_clients.pop(client_id, None)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
