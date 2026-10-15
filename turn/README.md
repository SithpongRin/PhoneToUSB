# PhoneToUSB Coturn STUN/TURN Setup

## 1. Why STUN / TURN is Required

PhoneToUSB is built to work over the global Internet. While direct peer-to-peer WebRTC connections succeed in many network topologies, carrier-grade NATs (CGNAT, common on 4G/5G mobile carriers) and restrictive corporate firewalls prevent direct peer-to-peer UDP packet traversal.

When direct connectivity fails, PhoneToUSB falls back to this **TURN Relay Server**.

Traffic passing through TURN is **encrypted end-to-end** via DTLS/SRTP. The TURN server cannot decrypt or inspect user files.

---

## 2. Firewall Port Configuration

Make sure your server firewall (UFW, AWS Security Group, etc.) permits the following ports:

```bash
# STUN/TURN Standard
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp

# TURNS Secure (TLS)
sudo ufw allow 5349/tcp
sudo ufw allow 5349/udp

# Dynamic Relay Port Range
sudo ufw allow 49152:65535/udp
```

---

## 3. Launching Coturn with Docker

1. Edit `coturn.conf` with your actual domain and shared secret.
2. Start the container:
   ```bash
   docker compose -f docker-compose.turn.yml up -d
   ```
3. Check logs:
   ```bash
   docker logs -f phonetousb-turn
   ```
