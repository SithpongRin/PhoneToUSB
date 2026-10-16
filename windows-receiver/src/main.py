"""
Main entry point for PhoneToUSB Windows Receiver.
Resolves dynamic LAN IP for QR pairing and starts the desktop GUI.
"""

import sys
import os
import socket
import asyncio
import threading
from pathlib import Path
import tkinter as tk

# Add src to sys.path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import logging_service
import usb_manager
import receiver_identity
import filesystem_service
import authorization_service
import pairing_service
import transfer_service
import signaling_client
import update_service
import embedded_server
import ui.main_window

from application import PhoneToUSBApp
from ui.main_window import MainWindow

def resolve_lan_ip() -> str:
    """
    Detects the laptop's real local Wi-Fi / LAN IP address, ignoring virtual VPN
    tunnels such as Cloudflare WARP (172.16.0.2) and loopback/APIPA addresses.
    """
    candidates = []
    try:
        _, _, ip_list = socket.gethostbyname_ex(socket.gethostname())
        for ip in ip_list:
            if ip.startswith("127.") or ip.startswith("169.254.") or ip.startswith("172.16.0."):
                continue
            candidates.append(ip)
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        udp_ip = s.getsockname()[0]
        s.close()
        if (
            not udp_ip.startswith("127.")
            and not udp_ip.startswith("169.254.")
            and not udp_ip.startswith("172.16.0.")
            and udp_ip not in candidates
        ):
            candidates.insert(0, udp_ip)
    except Exception:
        pass

    # Prefer standard Wi-Fi / LAN private subnets (192.168.x.x, 10.x.x.x)
    for ip in candidates:
        if ip.startswith("192.168.") or ip.startswith("10."):
            return ip
    if candidates:
        return candidates[0]
    return "127.0.0.1"

def run_app():
    root = tk.Tk()
    async_loop = asyncio.new_event_loop()

    lan_ip = resolve_lan_ip()
    default_url = f"ws://{lan_ip}:8000/ws/client"
    backend_url = os.environ.get("PHONETOUSB_BACKEND_URL", default_url)

    app_coordinator = PhoneToUSBApp(backend_url=backend_url)
    window = MainWindow(root, app_coordinator, async_loop)

    def start_async_loop(loop):
        asyncio.set_event_loop(loop)
        loop.create_task(app_coordinator.start())
        loop.run_forever()

    network_thread = threading.Thread(target=start_async_loop, args=(async_loop,), daemon=True)
    network_thread.start()

    def on_close():
        future = asyncio.run_coroutine_threadsafe(app_coordinator.stop(), async_loop)
        try:
            future.result(timeout=2)
        except Exception:
            pass
        async_loop.call_soon_threadsafe(async_loop.stop)
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    run_app()
