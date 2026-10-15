"""
Tkinter Desktop User Interface for PhoneToUSB Windows 11 Receiver.
Features a clean, modern design with status indicators, pairing QR code display,
pairing approval modals, device management, and transfer monitoring.
"""

import sys
import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk, Image

class MainWindow:
    def __init__(self, root: tk.Tk, app_coordinator: Any, async_loop: asyncio.AbstractEventLoop):
        self.root = root
        self.app = app_coordinator
        self.loop = async_loop

        self.root.title("PhoneToUSB Receiver")
        self.root.geometry("680x560")
        self.root.minsize(620, 500)
        self.root.configure(bg="#0F172A")  # Modern slate dark background

        self._style = ttk.Style()
        self._style.theme_use("clam")
        self._configure_styles()

        self._qr_image_tk: Optional[ImageTk.PhotoImage] = None
        self._timer_after_id = None

        self._build_header()
        self._build_status_cards()
        self._build_tabs()

        # Connect application coordinator callbacks
        self.app.on_status_change_callback = self._on_network_status_change
        self.app.on_usb_change_callback = self._on_usb_status_change
        self.app.on_pairing_prompt_callback = self._on_pairing_request_prompt
        self.app.on_transfer_progress_callback = self._on_transfer_progress

        # Initialize with current state
        self._update_usb_display(self.app.usb_manager.get_storage_stats())

    def _configure_styles(self):
        self._style.configure("TFrame", background="#0F172A")
        self._style.configure("Card.TFrame", background="#1E293B", relief="flat")
        self._style.configure("TLabel", background="#0F172A", foreground="#F8FAFC", font=("Segoe UI", 10))
        self._style.configure("Header.TLabel", background="#0F172A", foreground="#38BDF8", font=("Segoe UI", 16, "bold"))
        self._style.configure("SubHeader.TLabel", background="#0F172A", foreground="#94A3B8", font=("Segoe UI", 9))
        self._style.configure("Status.TLabel", background="#1E293B", foreground="#F8FAFC", font=("Segoe UI", 11, "bold"))
        self._style.configure("Desc.TLabel", background="#1E293B", foreground="#94A3B8", font=("Segoe UI", 9))

        self._style.configure("Primary.TButton", background="#0284C7", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), borderwidth=0)
        self._style.map("Primary.TButton", background=[("active", "#0369A1"), ("disabled", "#334155")])

        self._style.configure("Danger.TButton", background="#EF4444", foreground="#FFFFFF", font=("Segoe UI", 9), borderwidth=0)
        self._style.map("Danger.TButton", background=[("active", "#DC2626")])

        self._style.configure("TNotebook", background="#0F172A", borderwidth=0)
        self._style.configure("TNotebook.Tab", background="#1E293B", foreground="#94A3B8", font=("Segoe UI", 10), padding=[12, 6])
        self._style.map("TNotebook.Tab", background=[("selected", "#0284C7")], foreground=[("selected", "#FFFFFF")])

    def _build_header(self):
        header_frame = ttk.Frame(self.root, padding=16)
        header_frame.pack(fill="x")

        title = ttk.Label(header_frame, text="PhoneToUSB Receiver", style="Header.TLabel")
        title.pack(anchor="w")

        info_text = f"Receiver ID: {self.app.identity.receiver_id}  |  Version 1.0.0"
        subtitle = ttk.Label(header_frame, text=info_text, style="SubHeader.TLabel")
        subtitle.pack(anchor="w", pady=(2, 0))

    def _build_status_cards(self):
        cards_frame = ttk.Frame(self.root, padding=(16, 0, 16, 12))
        cards_frame.pack(fill="x")

        # Network Card
        net_card = ttk.Frame(cards_frame, style="Card.TFrame", padding=12)
        net_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.lbl_net_status = ttk.Label(net_card, text="Connecting...", style="Status.TLabel", foreground="#F59E0B")
        self.lbl_net_status.pack(anchor="w")
        self.lbl_net_desc = ttk.Label(net_card, text="Connecting to Internet coordination service", style="Desc.TLabel")
        self.lbl_net_desc.pack(anchor="w")

        # USB Card
        usb_card = ttk.Frame(cards_frame, style="Card.TFrame", padding=12)
        usb_card.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self.lbl_usb_status = ttk.Label(usb_card, text="Checking USB...", style="Status.TLabel")
        self.lbl_usb_status.pack(anchor="w")
        self.lbl_usb_desc = ttk.Label(usb_card, text="Verifying removable storage volume", style="Desc.TLabel")
        self.lbl_usb_desc.pack(anchor="w")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Tab 1: Pairing & QR
        self.tab_pairing = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.notebook.add(self.tab_pairing, text="Pairing & Security")
        self._build_pairing_tab()

        # Tab 2: Paired Devices
        self.tab_devices = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.notebook.add(self.tab_devices, text="Paired Devices")
        self._build_devices_tab()

        # Tab 3: Transfer Activity
        self.tab_transfers = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.notebook.add(self.tab_transfers, text="Transfers")
        self._build_transfers_tab()

        # Tab 4: Updates & Settings
        self.tab_updates = ttk.Frame(self.notebook, style="Card.TFrame", padding=16)
        self.notebook.add(self.tab_updates, text="Updates")
        self._build_updates_tab()

    def _build_pairing_tab(self):
        desc = ttk.Label(
            self.tab_pairing,
            text="To connect your Android phone securely, generate a single-use pairing QR code.",
            style="Desc.TLabel"
        )
        desc.pack(anchor="w", pady=(0, 12))

        btn_frame = ttk.Frame(self.tab_pairing, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(0, 12))

        self.btn_pair = ttk.Button(btn_frame, text="Generate Pairing QR Code", style="Primary.TButton", command=self._on_generate_qr_clicked)
        self.btn_pair.pack(side="left")

        self.lbl_timer = ttk.Label(btn_frame, text="", style="Desc.TLabel")
        self.lbl_timer.pack(side="left", padx=16)

        # QR Display Container
        self.qr_container = tk.Label(self.tab_pairing, bg="#1E293B")
        self.qr_container.pack(pady=8)

    def _on_generate_qr_clicked(self):
        token, payload = self.app.pairing_service.generate_pairing_session()
        pil_img = self.app.pairing_service.render_qr_image(payload)
        pil_img = pil_img.resize((220, 220), Image.Resampling.LANCZOS)
        self._qr_image_tk = ImageTk.PhotoImage(pil_img)
        self.qr_container.configure(image=self._qr_image_tk)
        self._update_timer()

    def _update_timer(self):
        rem = self.app.pairing_service.remaining_seconds
        if rem > 0:
            self.lbl_timer.configure(text=f"Expires in: {rem} seconds", foreground="#38BDF8")
            self._timer_after_id = self.root.after(1000, self._update_timer)
        else:
            self.lbl_timer.configure(text="QR code expired. Please generate a new one.", foreground="#EF4444")
            self.qr_container.configure(image="")
            self._qr_image_tk = None

    def _build_devices_tab(self):
        top_bar = ttk.Frame(self.tab_devices, style="Card.TFrame")
        top_bar.pack(fill="x", pady=(0, 8))

        lbl = ttk.Label(top_bar, text="Authorized Android Phones:", style="Desc.TLabel")
        lbl.pack(side="left")

        btn_revoke_all = ttk.Button(top_bar, text="Revoke All Devices", style="Danger.TButton", command=self._on_revoke_all_clicked)
        btn_revoke_all.pack(side="right")

        # Treeview for paired devices
        cols = ("Name", "Device ID", "Paired Date", "Last Seen")
        self.device_tree = ttk.Treeview(self.tab_devices, columns=cols, show="headings", height=8)
        for col in cols:
            self.device_tree.heading(col, text=col)
            self.device_tree.column(col, width=130)

        self.device_tree.pack(fill="both", expand=True)

        action_frame = ttk.Frame(self.tab_devices, style="Card.TFrame")
        action_frame.pack(fill="x", pady=(8, 0))

        btn_revoke_sel = ttk.Button(action_frame, text="Revoke Selected", style="Danger.TButton", command=self._on_revoke_selected_clicked)
        btn_revoke_sel.pack(side="left")

        btn_refresh = ttk.Button(action_frame, text="Refresh List", command=self._refresh_device_list)
        btn_refresh.pack(side="right")

        self._refresh_device_list()

    def _refresh_device_list(self):
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        devices = self.app.auth_service.list_devices()
        for d in devices:
            paired_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("paired_at", 0)))
            last_seen = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("last_seen", 0)))
            self.device_tree.insert("", "end", values=(
                d.get("friendly_name", "Phone"),
                d.get("client_id", ""),
                paired_time,
                last_seen
            ))

    def _on_revoke_selected_clicked(self):
        selected = self.device_tree.selection()
        if not selected:
            return
        item_vals = self.device_tree.item(selected[0])["values"]
        client_id = str(item_vals[1])
        if messagebox.askyesno("Confirm Revocation", f"Revoke authorization for '{item_vals[0]}'?"):
            self.app.auth_service.revoke_device(client_id)
            self._refresh_device_list()

    def _on_revoke_all_clicked(self):
        if messagebox.askyesno("Confirm Revoke All", "Are you sure you want to revoke ALL paired phones?"):
            self.app.auth_service.revoke_all()
            self._refresh_device_list()

    def _build_transfers_tab(self):
        prog_frame = ttk.Frame(self.tab_transfers, style="Card.TFrame")
        prog_frame.pack(fill="x", pady=(0, 12))

        self.lbl_active_transfer = ttk.Label(prog_frame, text="No active transfer", style="Desc.TLabel")
        self.lbl_active_transfer.pack(anchor="w", pady=(0, 4))

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x")

        ttk.Label(self.tab_transfers, text="Recent Transfer History:", style="Desc.TLabel").pack(anchor="w", pady=(8, 4))

        cols = ("Direction", "File Name", "Size", "Status", "Time")
        self.history_tree = ttk.Treeview(self.tab_transfers, columns=cols, show="headings", height=8)
        for col in cols:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=100)
        self.history_tree.pack(fill="both", expand=True)

        self._refresh_history_list()

    def _refresh_history_list(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        history = self.app.transfer_service.get_history()
        for h in history[:50]:
            t_str = time.strftime("%H:%M:%S", time.localtime(h.get("timestamp", 0)))
            size_mb = f"{h.get('size', 0) / (1024 * 1024):.2f} MB"
            self.history_tree.insert("", "end", values=(
                h.get("direction", ""),
                h.get("filename", ""),
                size_mb,
                h.get("status", ""),
                t_str
            ))

    def _build_updates_tab(self):
        lbl = ttk.Label(self.tab_updates, text="GitHub Releases Auto-Update", style="Status.TLabel")
        lbl.pack(anchor="w", pady=(0, 4))

        desc = ttk.Label(
            self.tab_updates,
            text="Checks official GitHub releases for updates without disturbing your USB files.",
            style="Desc.TLabel"
        )
        desc.pack(anchor="w", pady=(0, 16))

        self.lbl_update_status = ttk.Label(self.tab_updates, text=f"Installed Version: 1.0.0", style="Desc.TLabel")
        self.lbl_update_status.pack(anchor="w", pady=(0, 12))

        self.btn_check_update = ttk.Button(self.tab_updates, text="Check for Updates", style="Primary.TButton", command=self._on_check_update_clicked)
        self.btn_check_update.pack(anchor="w")

    def _on_check_update_clicked(self):
        self.lbl_update_status.configure(text="Checking GitHub for latest release...")

        def run_check():
            future = asyncio.run_coroutine_threadsafe(self.app.update_service.check_for_updates(), self.loop)
            try:
                res = future.result(timeout=10)
                if res.get("update_available"):
                    text = f"Update available: v{res['latest_version']} (Current: v1.0.0)"
                    self.root.after(0, lambda: self.lbl_update_status.configure(text=text, foreground="#38BDF8"))
                else:
                    text = f"PhoneToUSB is up to date (Version 1.0.0)"
                    self.root.after(0, lambda: self.lbl_update_status.configure(text=text, foreground="#10B981"))
            except Exception as e:
                self.root.after(0, lambda: self.lbl_update_status.configure(text=f"Update check failed: {e}", foreground="#EF4444"))

        threading.Thread(target=run_check, daemon=True).start()

    def _on_network_status_change(self, status: str):
        def update():
            if status == "ONLINE":
                self.lbl_net_status.configure(text="Online (Connected)", foreground="#10B981")
                self.lbl_net_desc.configure(text="Ready for incoming remote connections")
            elif status == "CONNECTING":
                self.lbl_net_status.configure(text="Connecting...", foreground="#F59E0B")
                self.lbl_net_desc.configure(text="Establishing secure WebSocket connection")
            else:
                self.lbl_net_status.configure(text="Offline", foreground="#EF4444")
                self.lbl_net_desc.configure(text="No connection to coordination service")

        self.root.after(0, update)

    def _on_usb_status_change(self, stats: Dict[str, Any]):
        self.root.after(0, lambda: self._update_usb_display(stats))

    def _update_usb_display(self, stats: Dict[str, Any]):
        if stats.get("is_ready"):
            letter = stats.get("drive_letter", "")
            free_gb = stats.get("free_bytes", 0) / (1024**3)
            total_gb = stats.get("total_bytes", 0) / (1024**3)
            label = stats.get("volume_label", "USB")

            self.lbl_usb_status.configure(text=f"USB Ready ({letter})", foreground="#10B981")
            self.lbl_usb_desc.configure(text=f"{label} - {free_gb:.1f} GB free of {total_gb:.1f} GB")
        else:
            self.lbl_usb_status.configure(text="USB Not Ready", foreground="#EF4444")
            self.lbl_usb_desc.configure(text=stats.get("error", "Volume unmounted or missing"))

    def _on_pairing_request_prompt(self, msg: Dict[str, Any], future: asyncio.Future):
        """Displays an explicit approval popup on the Windows PC screen."""
        client_name = msg.get("client_name", "Android Phone")
        client_id = msg.get("client_id", "Unknown")

        def ask_user():
            res = messagebox.askyesno(
                "Phone Pairing Request",
                f"Do you want to authorize phone:\n\n'{client_name}'\n(ID: {client_id})\n\nto access this USB drive remotely over the Internet?",
                icon="question"
            )
            future.set_result(res)
            self._refresh_device_list()

        self.root.after(0, ask_user)

    def _on_transfer_progress(self, progress: Dict[str, Any]):
        def update():
            written = progress.get("bytes_written", 0)
            self.lbl_active_transfer.configure(text=f"Receiving file chunks... ({written / 1024:.0f} KB)")
        self.root.after(0, update)
