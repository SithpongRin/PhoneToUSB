# Internet Deployment & Infrastructure Guide

## 1. Overview

PhoneToUSB requires an Internet-accessible coordination service and a STUN/TURN relay server to enable devices on separate networks (e.g. Android phone on 4G/5G mobile data and Windows laptop on home Wi-Fi) to discover, authenticate, and communicate with each other.

```
                    Internet (Public WAN)
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌─────────────────────────┐       ┌─────────────────────────┐
│ Signaling Coordination  │       │ Coturn STUN/TURN Relay  │
│ (FastAPI + WSS)         │       │ (RFC 5389 / 5766 / 8656)│
│ Port 443 (HTTPS/WSS)    │       │ Port 3478 / 5349 (TLS)  │
└─────────────────────────┘       └─────────────────────────┘
```

---

## 2. Infrastructure Requirements & Port Matrix

| Service | Protocol | External Port | Internal Port | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Signaling API** | TCP (TLS) | `443` | `8000` | Receiver presence, pairing coordination, WebRTC SDP signaling |
| **STUN/TURN** | UDP & TCP | `3478` | `3478` | Standard STUN/TURN binding & relay |
| **TURNS (Secure)** | TLS / TCP | `5349` | `5349` | Encrypted TURN over TLS |
| **TURN Relay Range**| UDP | `49152-65535` | `49152-65535` | Dynamic media/data relay ports |

---

## 3. Deployment with Docker Compose

A complete production deployment bundle is located in `/backend/docker-compose.yml` and `/turn/docker-compose.turn.yml`.

### 3.1 Environment Configuration (`.env`)
Create a production `.env` file on your server:
```env
# Server Domain
DOMAIN=signaling.phonetousb.example.com
TURN_DOMAIN=turn.phonetousb.example.com

# Backend Secrets
SECRET_KEY=change-this-to-a-secure-random-64-character-string
TURN_SECRET=change-this-to-a-strong-shared-secret-for-coturn-rest-api

# Rate Limiting
MAX_PAIRING_ATTEMPTS_PER_MINUTE=5
MAX_CONNECTIONS_PER_IP=20

# SSL / TLS
ACME_EMAIL=admin@phonetousb.example.com
```

### 3.2 Coturn Configuration (`coturn.conf`)
```ini
listening-port=3478
tls-listening-port=5349
realm=turn.phonetousb.example.com
use-auth-secret
static-auth-secret=change-this-to-a-strong-shared-secret-for-coturn-rest-api
fingerprint
lt-cred-mech
min-port=49152
max-port=65535
log-file=/var/log/turnserver.log
no-cli
no-tcp-relay
```

### 3.3 Ephemeral TURN Credentials (HMAC-SHA1)
The coordination backend dynamically issues short-lived credentials (valid 1 hour) using Coturn's REST API specification:
- `username`: `<timestamp>:<client_id>`
- `password`: `Base64(HMAC-SHA1(TURN_SECRET, username))`

This prevents unauthorized third-party bandwidth leeching on the TURN relay.

---

## 4. Bandwidth & Operational Cost Analysis

1. **Direct Peer-to-Peer (WebRTC)**:
   - When both devices can establish direct connectivity (estimated 75-85% of standard residential / Wi-Fi setups), **zero file transfer bandwidth traverses the server**. Only tiny JSON signaling packets (approx. 5-10 KB per connection setup) pass through the coordination service.
2. **Relayed via TURN**:
   - In restrictive environments (e.g. symmetric NAT on mobile carrier to corporate firewall), traffic is relayed via Coturn.
   - For every 1 GB of user files transferred, Coturn processes 1 GB inbound + 1 GB outbound (total 2 GB network transfer).
   - Cost recommendation: Use affordable cloud providers with generous bandwidth allowances (e.g. Hetzner, DigitalOcean, Linode, AWS Lightsail) or host on a home/office static IP server.
