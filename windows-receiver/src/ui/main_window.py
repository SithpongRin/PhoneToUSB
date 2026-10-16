"""
Modern Windows 11 Desktop User Interface for PhoneToUSB Receiver.
Implements Windows 11 immersive dark mode title bar, High-DPI awareness,
sleek card architecture, QR code display with countdown, custom approval dialogs,
and live storage/transfer meters.
"""

import sys
import os
import time
import json
import asyncio
import threading
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk, Image

# Color Palette (Obsidian & Cyan Windows 11 Dark Theme)
BG_MAIN = "#0B0F19"         # Deep obsidian backdrop
BG_CARD = "#161F30"         # Primary card background
BG_CARD_HOVER = "#1E2B42"   # Elevated card background
BORDER_COLOR = "#23334D"    # Subtle card border
ACCENT_PRIMARY = "#0EA5E9"  # Vibrant Sky Blue
ACCENT_CYAN = "#38BDF8"     # Bright cyan
TEXT_PRIMARY = "#F8FAFC"    # Bright white text
TEXT_SECONDARY = "#94A3B8"  # Slate secondary text
TEXT_MUTED = "#64748B"      # Muted metadata text
COLOR_SUCCESS = "#10B981"   # Emerald green
COLOR_DANGER = "#EF4444"    # Rose danger red
COLOR_WARNING = "#F59E0B"   # Amber warning

class MainWindow:
    def __init__(self, root: tk.Tk, app_coordinator: Any, async_loop: asyncio.AbstractEventLoop):
        self.root = root
        self.app = app_coordinator
        self.loop = async_loop

        # Configure High-DPI & Windows 11 Immersive Dark Titlebar
        self._apply_windows_11_styling()

        self.root.title("PhoneToUSB Receiver — Secure Storage Management")
        self.root.geometry("820x680")
        self.root.minsize(760, 600)
        self.root.configure(bg=BG_MAIN)

        self._style = ttk.Style()
        self._style.theme_use("clam")
        self._configure_custom_styles()

        self._qr_image_tk: Optional[ImageTk.PhotoImage] = None
        self._timer_after_id = None
        self._active_tab = "pairing"

        self._build_top_navbar()
        self._build_status_overview_cards()
        self._build_navigation_tabs()
        self._build_content_area()

        # Connect application coordinator callbacks
        self.app.on_status_change_callback = self._on_network_status_change
        self.app.on_usb_change_callback = self._on_usb_status_change
        self.app.on_pairing_prompt_callback = self._on_pairing_request_prompt
        self.app.on_transfer_progress_callback = self._on_transfer_progress

        # Initialize with current USB hardware state
        self._update_usb_display(self.app.usb_manager.get_storage_stats())

    def _apply_windows_11_styling(self):
        """Applies Windows 11 immersive dark mode to window frame and enables High DPI."""
        try:
            # Per-monitor DPI awareness
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 11 build 22000+)
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
        except Exception:
            pass

    def _configure_custom_styles(self):
        self._style.configure("TFrame", background=BG_MAIN)
        self._style.configure("Card.TFrame", background=BG_CARD, relief="flat")
        self._style.configure("CardBorder.TFrame", background=BORDER_COLOR, relief="flat")

        # Labels
        self._style.configure("TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY, font=("Segoe UI", 10))
        self._style.configure("HeaderTitle.TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY, font=("Segoe UI", 16, "bold"))
        self._style.configure("HeaderSub.TLabel", background=BG_MAIN, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        self._style.configure("CardTitle.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=("Segoe UI", 12, "bold"))
        self._style.configure("CardBody.TLabel", background=BG_CARD, foreground=TEXT_SECONDARY, font=("Segoe UI", 9))
        self._style.configure("Badge.TLabel", background=BG_CARD, foreground=ACCENT_CYAN, font=("Segoe UI", 10, "bold"))

        # Primary Action Buttons
        self._style.configure(
            "Primary.TButton",
            background=ACCENT_PRIMARY,
            foreground="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padding=[16, 8],
            borderwidth=0
        )
        self._style.map(
            "Primary.TButton",
            background=[("active", "#0284C7"), ("disabled", "#334155")]
        )

        # Danger Button
        self._style.configure(
            "Danger.TButton",
            background="#B91C1C",
            foreground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padding=[12, 6],
            borderwidth=0
        )
        self._style.map("Danger.TButton", background=[("active", "#991B1B")])

        # Modern Progress Bar
        self._style.configure(
            "Cyan.Horizontal.TProgressbar",
            troughcolor=BG_MAIN,
            background=ACCENT_CYAN,
            thickness=8,
            borderwidth=0
        )

        # Treeview styling
        self._style.configure(
            "Treeview",
            background=BG_CARD,
            foreground=TEXT_PRIMARY,
            fieldbackground=BG_CARD,
            rowheight=32,
            font=("Segoe UI", 9),
            borderwidth=0
        )
        self._style.configure(
            "Treeview.Heading",
            background="#1E293B",
            foreground=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
            borderwidth=0
        )
        self._style.map(
            "Treeview",
            background=[("selected", ACCENT_PRIMARY)],
            foreground=[("selected", "#FFFFFF")]
        )

    def _build_top_navbar(self):
        nav = tk.Frame(self.root, bg=BG_MAIN, padx=24, pady=16)
        nav.pack(fill="x")

        left = tk.Frame(nav, bg=BG_MAIN)
        left.pack(side="left")

        title_lbl = tk.Label(
            left,
            text="PhoneToUSB",
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_PRIMARY,
            bg=BG_MAIN
        )
        title_lbl.pack(anchor="w")

        sub_text = f"Portable Receiver v1.0.2  •  {self.app.identity.friendly_name}"
        sub_lbl = tk.Label(
            left,
            text=sub_text,
            font=("Segoe UI", 9),
            fg=TEXT_SECONDARY,
            bg=BG_MAIN
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Right-side Receiver ID Badge
        right = tk.Frame(nav, bg=BG_CARD, padx=12, pady=6)
        right.pack(side="right")

        id_lbl = tk.Label(
            right,
            text=f"ID: {self.app.identity.receiver_id}",
            font=("Consolas", 10, "bold"),
            fg=ACCENT_CYAN,
            bg=BG_CARD
        )
        id_lbl.pack()

    def _build_status_overview_cards(self):
        cards_container = tk.Frame(self.root, bg=BG_MAIN, padx=24, pady=4)
        cards_container.pack(fill="x")

        # 1. Network Status Card
        self.net_card = tk.Frame(cards_container, bg=BG_CARD, padx=16, pady=12, highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.net_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        net_header = tk.Frame(self.net_card, bg=BG_CARD)
        net_header.pack(fill="x")

        self.net_indicator = tk.Label(net_header, text="●", font=("Segoe UI", 14), fg=COLOR_WARNING, bg=BG_CARD)
        self.net_indicator.pack(side="left")

        self.net_title = tk.Label(net_header, text=" Internet: Connecting...", font=("Segoe UI", 11, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD)
        self.net_title.pack(side="left", padx=4)

        self.net_desc = tk.Label(
            self.net_card,
            text="Establishing secure connection with coordination service",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_CARD
        )
        self.net_desc.pack(anchor="w", pady=(4, 0))

        # 2. USB Hardware Storage Card
        self.usb_card = tk.Frame(cards_container, bg=BG_CARD, padx=16, pady=12, highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.usb_card.pack(side="right", fill="both", expand=True, padx=(10, 0))

        usb_header = tk.Frame(self.usb_card, bg=BG_CARD)
        usb_header.pack(fill="x")

        self.usb_indicator = tk.Label(usb_header, text="●", font=("Segoe UI", 14), fg=COLOR_WARNING, bg=BG_CARD)
        self.usb_indicator.pack(side="left")

        self.usb_title = tk.Label(usb_header, text=" USB: Checking...", font=("Segoe UI", 11, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD)
        self.usb_title.pack(side="left", padx=4)

        self.usb_desc = tk.Label(
            self.usb_card,
            text="Detecting removable drive volume",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_CARD
        )
        self.usb_desc.pack(anchor="w", pady=(4, 6))

        self.usb_capacity_bar = ttk.Progressbar(self.usb_card, style="Cyan.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.usb_capacity_bar.pack(fill="x")

    def _build_navigation_tabs(self):
        tab_bar = tk.Frame(self.root, bg=BG_MAIN, padx=24, pady=12)
        tab_bar.pack(fill="x")

        self.tab_buttons = {}
        tabs = [
            ("pairing", "Pairing & QR"),
            ("devices", "Paired Phones"),
            ("transfers", "Transfer Activity"),
            ("updates", "GitHub Updates")
        ]

        for tab_id, tab_label in tabs:
            btn = tk.Button(
                tab_bar,
                text=tab_label,
                font=("Segoe UI", 10, "bold"),
                bg=BG_CARD if tab_id == self._active_tab else BG_MAIN,
                fg=ACCENT_CYAN if tab_id == self._active_tab else TEXT_SECONDARY,
                activebackground=BG_CARD_HOVER,
                activeforeground=TEXT_PRIMARY,
                relief="flat",
                bd=0,
                padx=16,
                pady=8,
                cursor="hand2",
                command=lambda t=tab_id: self._switch_tab(t)
            )
            btn.pack(side="left", padx=(0, 8))
            self.tab_buttons[tab_id] = btn

    def _build_content_area(self):
        self.content_frame = tk.Frame(self.root, bg=BG_MAIN, padx=24, pady=0)
        self.content_frame.pack(fill="both", expand=True, pady=(0, 16))

        # Containers for each tab view
        self.views = {
            "pairing": self._create_pairing_view(),
            "devices": self._create_devices_view(),
            "transfers": self._create_transfers_view(),
            "updates": self._create_updates_view()
        }
        self._switch_tab("pairing")

    def _switch_tab(self, tab_name: str):
        self._active_tab = tab_name
        for t_id, btn in self.tab_buttons.items():
            if t_id == tab_name:
                btn.configure(bg=BG_CARD, fg=ACCENT_CYAN)
            else:
                btn.configure(bg=BG_MAIN, fg=TEXT_SECONDARY)

        for name, view in self.views.items():
            if name == tab_name:
                view.pack(fill="both", expand=True)
            else:
                view.pack_forget()

    # ==========================================
    # View 1: Pairing & QR Display
    # ==========================================
    def _create_pairing_view(self) -> tk.Frame:
        view = tk.Frame(self.content_frame, bg=BG_CARD, padx=24, pady=20, highlightbackground=BORDER_COLOR, highlightthickness=1)

        header_row = tk.Frame(view, bg=BG_CARD)
        header_row.pack(fill="x", pady=(0, 12))

        lbl = tk.Label(header_row, text="Connect Android Phone", font=("Segoe UI", 13, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD)
        lbl.pack(side="left")

        self.btn_gen_qr = tk.Button(
            header_row,
            text="Generate Pairing QR Code",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT_PRIMARY,
            fg="#FFFFFF",
            activebackground="#0284C7",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_generate_qr_clicked
        )
        self.btn_gen_qr.pack(side="right")

        self.lbl_countdown = tk.Label(view, text="", font=("Segoe UI", 10, "bold"), fg=ACCENT_CYAN, bg=BG_CARD)
        self.lbl_countdown.pack(anchor="w", pady=(0, 8))

        # White rounded card for high contrast QR rendering
        self.qr_card = tk.Frame(view, bg="#FFFFFF", padx=16, pady=16)
        self.qr_card.pack(pady=10)

        self.qr_label = tk.Label(self.qr_card, bg="#FFFFFF")
        self.qr_label.pack()

        # Instructions below
        inst_frame = tk.Frame(view, bg=BG_CARD)
        inst_frame.pack(fill="x", pady=(12, 0))

        instructions = (
            "1. Open the PhoneToUSB app on your Android phone.\n"
            "2. Tap 'Pair New USB Drive' and point your camera at this QR code.\n"
            "3. Click 'Approve' when the authorization prompt appears on this laptop.\n"
            "Note: Pairing is required only once. The phone remembers this USB drive automatically."
        )
        inst_lbl = tk.Label(inst_frame, text=instructions, font=("Segoe UI", 9), fg=TEXT_MUTED, bg=BG_CARD, justify="left")
        inst_lbl.pack(anchor="w")

        # Initial render of QR code
        self._on_generate_qr_clicked()
        return view

    def _on_generate_qr_clicked(self):
        token, payload = self.app.pairing_service.generate_pairing_session()
        pil_img = self.app.pairing_service.render_qr_image(payload)
        pil_img = pil_img.resize((240, 240), Image.Resampling.LANCZOS)
        self._qr_image_tk = ImageTk.PhotoImage(pil_img)
        self.qr_label.configure(image=self._qr_image_tk)
        self._update_timer()

    def _update_timer(self):
        rem = self.app.pairing_service.remaining_seconds
        if rem > 0:
            self.lbl_countdown.configure(
                text=f"QR expires in: {rem}s  •  Wi-Fi Server: {self.app.pairing_service.backend_url}",
                fg=ACCENT_CYAN
            )
            self._timer_after_id = self.root.after(1000, self._update_timer)
        else:
            self.lbl_countdown.configure(
                text="QR Code Expired. Please click 'Generate Pairing QR Code' to create a new one.",
                fg=COLOR_DANGER
            )
            self.qr_label.configure(image="")
            self._qr_image_tk = None

    # ==========================================
    # View 2: Paired Phones Management
    # ==========================================
    def _create_devices_view(self) -> tk.Frame:
        view = tk.Frame(self.content_frame, bg=BG_CARD, padx=20, pady=16, highlightbackground=BORDER_COLOR, highlightthickness=1)

        top = tk.Frame(view, bg=BG_CARD)
        top.pack(fill="x", pady=(0, 12))

        tk.Label(top, text="Authorized Android Phones", font=("Segoe UI", 12, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(side="left")

        btn_revoke_all = tk.Button(
            top,
            text="Revoke All Phones",
            font=("Segoe UI", 9, "bold"),
            bg="#991B1B",
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_revoke_all_clicked
        )
        btn_revoke_all.pack(side="right")

        cols = ("Name", "Device ID", "Paired Date", "Last Seen")
        self.device_tree = ttk.Treeview(view, columns=cols, show="headings", height=9)
        for col in cols:
            self.device_tree.heading(col, text=col)
            self.device_tree.column(col, width=150)
        self.device_tree.pack(fill="both", expand=True)

        bottom = tk.Frame(view, bg=BG_CARD)
        bottom.pack(fill="x", pady=(12, 0))

        btn_revoke_sel = tk.Button(
            bottom,
            text="Revoke Selected Phone",
            font=("Segoe UI", 9, "bold"),
            bg="#DC2626",
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._on_revoke_selected_clicked
        )
        btn_revoke_sel.pack(side="left")

        btn_refresh = tk.Button(
            bottom,
            text="Refresh List",
            font=("Segoe UI", 9),
            bg=BORDER_COLOR,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._refresh_device_list
        )
        btn_refresh.pack(side="right")

        self._refresh_device_list()
        return view

    def _refresh_device_list(self):
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        devices = self.app.auth_service.list_devices()
        for d in devices:
            paired_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("paired_at", 0)))
            last_seen = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("last_seen", 0)))
            self.device_tree.insert("", "end", values=(
                d.get("friendly_name", "Android Phone"),
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
        if messagebox.askyesno("Confirm Revocation", f"Revoke authorization for '{item_vals[0]}'?\nThis phone will immediately lose access to the USB."):
            self.app.auth_service.revoke_device(client_id)
            self._refresh_device_list()

    def _on_revoke_all_clicked(self):
        if messagebox.askyesno("Confirm Revoke All", "Are you sure you want to revoke ALL paired phones?\nNo phone will be able to access this USB until re-paired."):
            self.app.auth_service.revoke_all()
            self._refresh_device_list()

    # ==========================================
    # View 3: Transfer Activity
    # ==========================================
    def _create_transfers_view(self) -> tk.Frame:
        view = tk.Frame(self.content_frame, bg=BG_CARD, padx=20, pady=16, highlightbackground=BORDER_COLOR, highlightthickness=1)

        # Active Transfer Meter Box
        active_box = tk.Frame(view, bg=BG_MAIN, padx=16, pady=12)
        active_box.pack(fill="x", pady=(0, 16))

        self.lbl_active_transfer = tk.Label(active_box, text="Idle — Ready for transfers", font=("Segoe UI", 10, "bold"), fg=TEXT_PRIMARY, bg=BG_MAIN)
        self.lbl_active_transfer.pack(anchor="w", pady=(0, 4))

        self.progress_bar = ttk.Progressbar(active_box, style="Cyan.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.lbl_transfer_meta = tk.Label(active_box, text="Safe atomic writing to .phonetoUSB/temp/*.part with SHA-256 validation", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_MAIN)
        self.lbl_transfer_meta.pack(anchor="w")

        tk.Label(view, text="Recent Transfer History", font=("Segoe UI", 11, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(0, 8))

        cols = ("Direction", "File Name", "Size", "Status", "Time")
        self.history_tree = ttk.Treeview(view, columns=cols, show="headings", height=8)
        for col in cols:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=120)
        self.history_tree.pack(fill="both", expand=True)

        self._refresh_history_list()
        return view

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

    # ==========================================
    # View 4: GitHub Releases Updates
    # ==========================================
    def _create_updates_view(self) -> tk.Frame:
        view = tk.Frame(self.content_frame, bg=BG_CARD, padx=24, pady=20, highlightbackground=BORDER_COLOR, highlightthickness=1)

        tk.Label(view, text="GitHub Releases Auto-Update", font=("Segoe UI", 13, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(anchor="w", pady=(0, 4))
        tk.Label(
            view,
            text="Checks official GitHub releases for verified updates without disturbing your USB files or pairing data.",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_CARD
        ).pack(anchor="w", pady=(0, 16))

        self.lbl_update_status = tk.Label(view, text="Installed Version: v1.0.2 (Official)", font=("Segoe UI", 10), fg=TEXT_SECONDARY, bg=BG_CARD)
        self.lbl_update_status.pack(anchor="w", pady=(0, 16))

        self.btn_check_update = tk.Button(
            view,
            text="Check for Updates",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT_PRIMARY,
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_check_update_clicked
        )
        self.btn_check_update.pack(anchor="w")

        # In-App Update Install Button (hidden until update found or clicked)
        self.btn_apply_update = tk.Button(
            view,
            text="Download & Install Update Now (In-App)",
            font=("Segoe UI", 10, "bold"),
            bg=COLOR_SUCCESS,
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_install_update_clicked
        )

        # Server Endpoint Config Section
        server_box = tk.Frame(view, bg=BG_MAIN, padx=16, pady=12, highlightbackground=BORDER_COLOR, highlightthickness=1)
        server_box.pack(fill="x", pady=(24, 0))

        tk.Label(server_box, text="Coordination Server Address (Used in QR Code)", font=("Segoe UI", 10, "bold"), fg=TEXT_PRIMARY, bg=BG_MAIN).pack(anchor="w", pady=(0, 4))
        tk.Label(server_box, text="Set your laptop's Wi-Fi IP (e.g. ws://192.168.1.5:8000/ws/client) or public domain for global access.", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_MAIN).pack(anchor="w", pady=(0, 8))

        url_row = tk.Frame(server_box, bg=BG_MAIN)
        url_row.pack(fill="x")

        self.server_entry = tk.Entry(url_row, font=("Segoe UI", 10), bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", bd=4)
        self.server_entry.insert(0, self.app.backend_url)
        self.server_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_save_url = tk.Button(
            url_row,
            text="Apply & Reconnect",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_PRIMARY,
            fg="#FFFFFF",
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._on_save_server_url
        )
        btn_save_url.pack(side="right")

        return view

    def _on_save_server_url(self):
        new_url = self.server_entry.get().strip()
        if new_url:
            self.app.backend_url = new_url
            self.app.pairing_service.backend_url = new_url
            self.app.signaling_client.backend_ws_url = self.app._resolve_signaling_url(new_url)
            self.app.signaling_client.stop()
            self._on_generate_qr_clicked()
            asyncio.run_coroutine_threadsafe(self.app.signaling_client.start(), self.loop)
            messagebox.showinfo("Server Updated", f"Backend server URL updated to:\n{new_url}\n\nPairing QR code has been refreshed.")

    def _on_check_update_clicked(self):
        self.lbl_update_status.configure(text="Checking for official updates...", fg=ACCENT_CYAN)

        def run_check():
            future = asyncio.run_coroutine_threadsafe(self.app.update_service.check_for_updates(), self.loop)
            try:
                res = future.result(timeout=10)
                if res.get("update_available") or res.get("download_url"):
                    text = f"Official Release available: v{res['latest_version']} (Current: v1.0.2)"
                    def show_btn():
                        self.lbl_update_status.configure(text=text, fg=ACCENT_CYAN)
                        self.btn_apply_update.pack(anchor="w", pady=(8, 0))
                    self.root.after(0, show_btn)
                else:
                    text = "PhoneToUSB is fully up to date (Version 1.0.2)"
                    self.root.after(0, lambda: self.lbl_update_status.configure(text=text, fg=COLOR_SUCCESS))
            except Exception as e:
                self.root.after(0, lambda: self.lbl_update_status.configure(text=f"Running version v1.0.2.", fg=TEXT_SECONDARY))

        threading.Thread(target=run_check, daemon=True).start()

    def _on_install_update_clicked(self):
        self.lbl_update_status.configure(text="Downloading latest PhoneToUSB.exe from GitHub...", fg=ACCENT_CYAN)
        self.btn_apply_update.configure(state="disabled")

        def run_install():
            try:
                dl_url = "https://github.com/SithpongRin/PhoneToUSB/raw/main/dist/PhoneToUSB.exe"
                future = asyncio.run_coroutine_threadsafe(self.app.update_service.download_update(dl_url), self.loop)
                staged_exe = future.result(timeout=120)
                batch_file = self.app.update_service.stage_update_and_prepare_script(staged_exe)

                def prompt_restart():
                    if messagebox.askyesno("Update Downloaded", "New PhoneToUSB.exe downloaded successfully!\n\nRestart now to apply the update?"):
                        os.startfile(str(batch_file))
                        self.root.destroy()
                        sys.exit(0)
                self.root.after(0, prompt_restart)
            except Exception as e:
                self.root.after(0, lambda: self.lbl_update_status.configure(text=f"Update failed: {e}", fg=COLOR_DANGER))
                self.root.after(0, lambda: self.btn_apply_update.configure(state="normal"))

        threading.Thread(target=run_install, daemon=True).start()

    # ==========================================
    # Status Updates & Real-time Callbacks
    # ==========================================
    def _on_network_status_change(self, status: str):
        def update():
            if status == "ONLINE":
                self.net_indicator.configure(fg=COLOR_SUCCESS)
                self.net_title.configure(text=" Internet: Online (Ready)", fg=COLOR_SUCCESS)
                self.net_desc.configure(text="Securely connected to coordination backend. Ready for incoming requests.")
            elif status == "CONNECTING":
                self.net_indicator.configure(fg=COLOR_WARNING)
                self.net_title.configure(text=" Internet: Connecting...", fg=COLOR_WARNING)
                self.net_desc.configure(text="Establishing secure WebSocket connection...")
            else:
                self.net_indicator.configure(fg=COLOR_DANGER)
                self.net_title.configure(text=" Internet: Offline", fg=COLOR_DANGER)
                self.net_desc.configure(text="Disconnected from Internet coordination service.")
        self.root.after(0, update)

    def _on_usb_status_change(self, stats: Dict[str, Any]):
        self.root.after(0, lambda: self._update_usb_display(stats))

    def _update_usb_display(self, stats: Dict[str, Any]):
        if stats.get("is_ready"):
            letter = stats.get("drive_letter", "")
            free_gb = stats.get("free_bytes", 0) / (1024**3)
            total_gb = stats.get("total_bytes", 0) / (1024**3)
            label = stats.get("volume_label", "USB")
            pct = stats.get("percent_used", 0)

            self.usb_indicator.configure(fg=COLOR_SUCCESS)
            self.usb_title.configure(text=f" USB: Ready ({letter})", fg=COLOR_SUCCESS)
            self.usb_desc.configure(text=f"{label} • {free_gb:.1f} GB free of {total_gb:.1f} GB ({pct}% used)")
            self.usb_capacity_bar["value"] = pct
        else:
            self.usb_indicator.configure(fg=COLOR_DANGER)
            self.usb_title.configure(text=" USB: Not Ready", fg=COLOR_DANGER)
            self.usb_desc.configure(text=stats.get("error", "USB drive unmounted or write-protected"))
            self.usb_capacity_bar["value"] = 0

    def _on_pairing_request_prompt(self, msg: Dict[str, Any], future: asyncio.Future):
        """Displays a dedicated custom modal dialog on Windows to approve phone pairing."""
        client_name = msg.get("client_name", "Android Phone")
        client_id = msg.get("client_id", "Unknown")

        def prompt_dialog():
            dlg = tk.Toplevel(self.root)
            dlg.title("Authorize New Android Phone")
            dlg.geometry("460x280")
            dlg.configure(bg=BG_CARD)
            dlg.resizable(False, False)
            dlg.transient(self.root)
            dlg.grab_set()

            # Center dialog on main window
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 230
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 140
            dlg.geometry(f"+{x}+{y}")

            tk.Label(dlg, text="Pairing Approval Request", font=("Segoe UI", 13, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=(20, 8))

            info_msg = (
                f"An Android phone is requesting remote access to this USB drive:\n\n"
                f"Phone Name: {client_name}\n"
                f"Device ID: {client_id}\n\n"
                f"Do you want to authorize this phone to browse, upload,\nand download files on this USB over the Internet?"
            )
            tk.Label(dlg, text=info_msg, font=("Segoe UI", 9), fg=TEXT_SECONDARY, bg=BG_CARD, justify="center").pack(padx=20)

            btn_box = tk.Frame(dlg, bg=BG_CARD)
            btn_box.pack(pady=20)

            def on_approve():
                future.set_result(True)
                dlg.destroy()
                self._refresh_device_list()

            def on_reject():
                future.set_result(False)
                dlg.destroy()

            btn_reject = tk.Button(btn_box, text="Reject", font=("Segoe UI", 10), bg="#334155", fg=TEXT_PRIMARY, relief="flat", bd=0, padx=16, pady=6, cursor="hand2", command=on_reject)
            btn_reject.pack(side="left", padx=8)

            btn_approve = tk.Button(btn_box, text="Approve Device", font=("Segoe UI", 10, "bold"), bg=COLOR_SUCCESS, fg="#FFFFFF", relief="flat", bd=0, padx=20, pady=6, cursor="hand2", command=on_approve)
            btn_approve.pack(side="left", padx=8)

        self.root.after(0, prompt_dialog)

    def _on_transfer_progress(self, progress: Dict[str, Any]):
        def update():
            written = progress.get("bytes_written", 0)
            self.lbl_active_transfer.configure(text=f"Writing file chunks to USB... ({written / 1024:.0f} KB written)")
            self._refresh_history_list()
        self.root.after(0, update)
