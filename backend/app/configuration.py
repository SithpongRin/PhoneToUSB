"""
Configuration settings for PhoneToUSB Coordination Backend.
Loads environment variables with secure defaults.
"""

import os
from pydantic import BaseModel

class Settings(BaseModel):
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Security & Secrets
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-please-replace-in-production-random-64-bytes")
    TURN_SECRET: str = os.getenv("TURN_SECRET", "coturn-shared-secret-for-ephemeral-turn-credentials")
    TURN_REALM: str = os.getenv("TURN_REALM", "turn.phonetousb.example.com")
    TURN_SERVERS: str = os.getenv("TURN_SERVERS", "turn:turn.phonetousb.example.com:3478,turns:turn.phonetousb.example.com:5349")
    STUN_SERVERS: str = os.getenv("STUN_SERVERS", "stun:stun.l.google.com:19302,stun:turn.phonetousb.example.com:3478")

    # Timeouts & Limits
    RECEIVER_HEARTBEAT_TIMEOUT_SEC: int = int(os.getenv("RECEIVER_HEARTBEAT_TIMEOUT_SEC", "45"))
    PAIRING_TOKEN_TTL_SEC: int = int(os.getenv("PAIRING_TOKEN_TTL_SEC", "180"))
    MAX_PAIRING_ATTEMPTS_PER_MIN: int = int(os.getenv("MAX_PAIRING_ATTEMPTS_PER_MIN", "5"))
    MAX_CONNECTIONS_PER_IP: int = int(os.getenv("MAX_CONNECTIONS_PER_IP", "25"))

settings = Settings()
