"""
Main entry point for PhoneToUSB Windows Receiver.
Runs the Tkinter GUI on the main thread and the asyncio networking loop in a background worker thread.
"""

import sys
import os
import asyncio
import threading
from pathlib import Path
import tkinter as tk

# Add src to sys.path if running as script
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from application import PhoneToUSBApp
from ui.main_window import MainWindow

def run_app():
    # Setup Tkinter root
    root = tk.Tk()

    # Create dedicated background event loop for networking
    async_loop = asyncio.new_event_loop()

    # Determine backend URL from environment or fallback default
    backend_url = os.environ.get("PHONETOUSB_BACKEND_URL", "ws://127.0.0.1:8000/ws/receiver")

    app_coordinator = PhoneToUSBApp(backend_url=backend_url)
    window = MainWindow(root, app_coordinator, async_loop)

    def start_async_loop(loop):
        asyncio.set_event_loop(loop)
        loop.create_task(app_coordinator.start())
        loop.run_forever()

    network_thread = threading.Thread(target=start_async_loop, args=(async_loop,), daemon=True)
    network_thread.start()

    def on_close():
        # Cleanly stop network loop
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
