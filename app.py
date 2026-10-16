# -*- coding: utf-8 -*-
# USB File Transfer - High-Performance Local WiFi File Transfer Server

import os
import re
import sys
import time
import socket
import ctypes
import shutil
import secrets
import threading
import subprocess
from io import BytesIO
from datetime import datetime
from functools import wraps
from urllib.parse import quote
import urllib.request
import json
import tempfile

# Ensure dedicated Windows Taskbar identity so users can pin the application
if os.name == "nt":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SithpongRin.PhoneToUSB.App.v1")
    except Exception:
        pass

# Prevent errors when running windowless via pythonw.exe or PyInstaller --noconsole
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

try:
    from flask import (
        Flask,
        request,
        jsonify,
        send_from_directory,
        render_template_string,
        session,
        redirect,
        url_for,
    )
    from werkzeug.exceptions import RequestEntityTooLarge
    import segno
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "segno"])
    from flask import (
        Flask,
        request,
        jsonify,
        send_from_directory,
        render_template_string,
        session,
        redirect,
        url_for,
    )
    from werkzeug.exceptions import RequestEntityTooLarge
    import segno

# ==============================================================================
# CONFIGURATION
# ==============================================================================

USB_DRIVE = None
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
UPLOAD_FOLDER_NAME = "PhoneToUSB"
DRIVE_REMOVABLE = 2

# Application Version and GitHub Repository for In-App Updates
APP_VERSION = "1.0.1"
GITHUB_REPO = "SithpongRin/PhoneToUSB"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

ACTIVE_PORT = 5000

STATE_LOCK = threading.Lock()
SELECTED_USB_DRIVE = USB_DRIVE

# QR rotation interval: default 5 minutes (300s), switchable to 10 minutes (600s)
ROTATE_INTERVAL_SECONDS = 300
CURRENT_QR_ID = secrets.token_hex(4)
LAST_ROTATE_TIME = time.time()

# 6-digit Access Code required to unlock transfer session
ACCESS_CODE = f"{secrets.randbelow(900000) + 100000}"

# Generated direct share links: {token: expire_timestamp}
GENERATED_LINKS = {}

# Fast cache for IP and USB detection so UI never lags
_CACHED_IP = None
_CACHED_IP_TIME = 0.0
_CACHED_USBS = []
_CACHED_USB_TIME = 0.0
_CACHED_QR_KEY = None
_CACHED_QR_SVG = ""


# ==============================================================================
# STATE, ACCESS CODE & LINK GENERATOR
# ==============================================================================

def check_and_rotate_state(force_qr=False, force_code=False):
    global CURRENT_QR_ID, ACCESS_CODE, LAST_ROTATE_TIME
    now = time.time()
    with STATE_LOCK:
        elapsed = now - LAST_ROTATE_TIME
        if force_qr or elapsed >= ROTATE_INTERVAL_SECONDS:
            CURRENT_QR_ID = secrets.token_hex(4)
            LAST_ROTATE_TIME = now
            elapsed = 0
        if force_code:
            ACCESS_CODE = f"{secrets.randbelow(900000) + 100000}"
        remaining = max(1, int(ROTATE_INTERVAL_SECONDS - elapsed))
        return {
            "qr_id": CURRENT_QR_ID,
            "access_code": ACCESS_CODE,
            "remaining": remaining,
            "interval_sec": ROTATE_INTERVAL_SECONDS,
        }


def set_rotation_interval(minutes_val):
    global ROTATE_INTERVAL_SECONDS, LAST_ROTATE_TIME
    with STATE_LOCK:
        if minutes_val in (5, 10):
            ROTATE_INTERVAL_SECONDS = minutes_val * 60
            LAST_ROTATE_TIME = time.time()


def create_share_link_token(minutes_valid=30):
    token = secrets.token_urlsafe(10)
    expire_at = time.time() + (minutes_valid * 60)
    with STATE_LOCK:
        now = time.time()
        expired = [k for k, v in GENERATED_LINKS.items() if v < now]
        for k in expired:
            del GENERATED_LINKS[k]
        GENERATED_LINKS[token] = expire_at
    return token, minutes_valid


def verify_share_link_token(token_str):
    if not token_str:
        return False
    now = time.time()
    with STATE_LOCK:
        if token_str in GENERATED_LINKS:
            if GENERATED_LINKS[token_str] >= now:
                return True
            del GENERATED_LINKS[token_str]
def parse_version(v_str):
    """Parse version string like 'v1.0.3' or '1.0.3' into tuple of integers"""
    clean = re.sub(r'^[^\d]*', '', str(v_str))
    parts = []
    for p in clean.split('.'):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def cleanup_old_binary():
    """Remove any temporary or old binaries from previous in-app updates"""
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else BASE_DIR
        for fname in os.listdir(exe_dir):
            if fname.endswith(".old") or fname.startswith("_updater_temp"):
                try:
                    os.remove(os.path.join(exe_dir, fname))
                except OSError:
                    pass
    except Exception:
        pass


def create_desktop_and_start_menu_shortcuts():
    """Create Windows Desktop and Start Menu shortcuts with icon for Taskbar Pinning"""
    if os.name != "nt":
        return False
    try:
        exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.join(BASE_DIR, "USB_Transfer.exe")
        icon_path = os.path.join(BASE_DIR, "app_icon.ico")
        if not os.path.isfile(icon_path):
            icon_path = exe_path

        vbs_lines = [
            'Set oWS = CreateObject("WScript.Shell")',
            'sDesk = oWS.SpecialFolders("Desktop") & "\\USB File Transfer.lnk"',
            'sProg = oWS.SpecialFolders("Programs") & "\\USB File Transfer.lnk"',
            'Sub Make(p)',
            '  On Error Resume Next',
            '  Set l = oWS.CreateShortcut(p)',
            f'  l.TargetPath = "{exe_path}"',
            f'  l.WorkingDirectory = "{os.path.dirname(exe_path)}"',
            f'  l.IconLocation = "{icon_path},0"',
            '  l.Description = "USB File Transfer"',
            '  l.Save',
            'End Sub',
            'Make(sDesk)',
            'Make(sProg)',
        ]
        vpath = os.path.join(tempfile.gettempdir(), "_mk_sc.vbs")
        with open(vpath, "w", encoding="utf-8") as f:
            f.write("\r\n".join(vbs_lines))
        subprocess.run(["cscript", "//nologo", vpath], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            os.remove(vpath)
        except OSError:
            pass
        return True
    except Exception:
        return False


# ==============================================================================
# FAST SYSTEM, IP & USB DETECTION
# ==============================================================================

def format_size(num_bytes):
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 ** 2:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 ** 3:
        return f"{num_bytes / (1024 ** 2):.2f} MB"
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def get_drive_volume_name(drive_letter):
    if os.name != "nt":
        return "USB Drive"
    try:
        kernel32 = ctypes.windll.kernel32
        vol_name_buf = ctypes.create_unicode_buffer(261)
        fs_name_buf = ctypes.create_unicode_buffer(261)
        serial_num = ctypes.c_ulong(0)
        max_comp_len = ctypes.c_ulong(0)
        fs_flags = ctypes.c_ulong(0)
        res = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive_letter + "\\"),
            vol_name_buf,
            ctypes.sizeof(vol_name_buf),
            ctypes.byref(serial_num),
            ctypes.byref(max_comp_len),
            ctypes.byref(fs_flags),
            fs_name_buf,
            ctypes.sizeof(fs_name_buf),
        )
        if res and vol_name_buf.value.strip():
            return vol_name_buf.value.strip()
    except Exception:
        pass
    return "USB Drive"


def detect_all_usb_drives(force_refresh=False):
    global _CACHED_USBS, _CACHED_USB_TIME
    now = time.time()
    if not force_refresh and (now - _CACHED_USB_TIME < 1.5):
        return _CACHED_USBS

    usb_list = []
    if os.name == "nt":
        try:
            k32 = ctypes.windll.kernel32
            # Suppress Windows error dialogs for empty card readers or unmounted drives
            k32.SetErrorMode(0x0001 | 0x8000)
            mask = k32.GetLogicalDrives()
            for idx in range(2, 26):
                if mask & (1 << idx):
                    drv = f"{chr(65 + idx)}:"
                    root_path = drv + "\\"
                    try:
                        dtype = k32.GetDriveTypeW(ctypes.c_wchar_p(root_path))
                        if dtype == DRIVE_REMOVABLE:
                            try:
                                usage = shutil.disk_usage(root_path)
                                if usage.total <= 0:
                                    continue
                                free_str = format_size(usage.free)
                                total_str = format_size(usage.total)
                                used_pct = round(((usage.total - usage.free) / usage.total) * 100) if usage.total else 0
                            except Exception:
                                continue

                            vol_name = get_drive_volume_name(drv)
                            usb_list.append({
                                "drive": drv,
                                "label": vol_name,
                                "display": f"{vol_name} ({drv})",
                                "free_space": free_str,
                                "total_space": total_str,
                                "used_pct": used_pct,
                            })
                    except Exception:
                        continue
        except Exception:
            pass

    _CACHED_USBS = usb_list
    _CACHED_USB_TIME = now
    return usb_list


def resolve_storage(force_refresh=False):
    global SELECTED_USB_DRIVE
    usbs = detect_all_usb_drives(force_refresh=force_refresh)
    available_letters = [u["drive"] for u in usbs]

    with STATE_LOCK:
        if SELECTED_USB_DRIVE and SELECTED_USB_DRIVE not in available_letters:
            SELECTED_USB_DRIVE = None
        if len(usbs) == 1 and not SELECTED_USB_DRIVE:
            SELECTED_USB_DRIVE = usbs[0]["drive"]
        active_drive = SELECTED_USB_DRIVE

    # STRICT USB-ONLY REQUIREMENT: DO NOT ALLOW SAVING TO LOCAL HARD DISK!
    # If no USB flash drive is connected, uploads are strictly blocked.
    if not usbs:
        return {
            "upload_dir": "",
            "folder_name": UPLOAD_FOLDER_NAME,
            "usb_found": False,
            "need_selection": False,
            "usb_count": 0,
            "usbs": [],
            "active_drive": None,
            "drive_label": "No USB Drive Detected",
            "free_space": "0 B",
            "total_space": "0 B",
            "message": "No USB flash drive detected. Please connect a USB drive to transfer files.",
        }

    # If multiple USB drives are detected and no drive selected yet, default to first available
    if not active_drive or active_drive not in available_letters:
        active_drive = usbs[0]["drive"]
        with STATE_LOCK:
            SELECTED_USB_DRIVE = active_drive

    selected_info = next((u for u in usbs if u["drive"] == active_drive), usbs[0])
    target_dir = os.path.join(active_drive + "\\", UPLOAD_FOLDER_NAME)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        pass

    return {
        "upload_dir": target_dir,
        "folder_name": UPLOAD_FOLDER_NAME,
        "usb_found": True,
        "need_selection": False,
        "usb_count": len(usbs),
        "usbs": usbs,
        "active_drive": active_drive,
        "drive_label": selected_info["display"],
        "free_space": selected_info["free_space"],
        "total_space": selected_info["total_space"],
        "message": f"Connected to {selected_info['display']}",
    }


def get_laptop_ip():
    global _CACHED_IP, _CACHED_IP_TIME
    now = time.time()
    if _CACHED_IP and (now - _CACHED_IP_TIME < 5.0):
        return _CACHED_IP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                _CACHED_IP = ip
                _CACHED_IP_TIME = now
                return ip
    except OSError:
        pass
    _CACHED_IP = "127.0.0.1"
    _CACHED_IP_TIME = now
    return "127.0.0.1"


def clean_filename(raw_name):
    if not raw_name:
        return f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base = os.path.basename(raw_name.replace("\\", "/"))
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    if not cleaned:
        cleaned = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return cleaned


def unique_destination(folder, fname):
    full = os.path.join(folder, fname)
    if not os.path.exists(full):
        return fname, full
    stem, ext = os.path.splitext(fname)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = f"{stem}_{stamp}{ext}"
    full = os.path.join(folder, candidate)
    seq = 1
    while os.path.exists(full):
        candidate = f"{stem}_{stamp}_{seq}{ext}"
        full = os.path.join(folder, candidate)
        seq += 1
    return candidate, full


def badge_for_file(fname):
    ext = os.path.splitext(fname)[1].lower()
    mapping = {
        ".pdf": "PDF",
        ".doc": "DOC", ".docx": "DOCX", ".rtf": "RTF",
        ".xls": "XLS", ".xlsx": "XLSX", ".csv": "CSV",
        ".ppt": "PPT", ".pptx": "PPTX",
        ".jpg": "JPG", ".jpeg": "JPG", ".png": "PNG", ".gif": "GIF", ".webp": "WEBP", ".heic": "HEIC",
        ".mp4": "MP4", ".mov": "MOV", ".mkv": "MKV", ".avi": "AVI", ".webm": "WEBM",
        ".mp3": "MP3", ".wav": "WAV", ".m4a": "M4A",
        ".zip": "ZIP", ".rar": "RAR", ".7z": "7Z",
    }
    return mapping.get(ext, "FILE")


def scan_uploaded_files(folder):
    items = []
    if not os.path.exists(folder):
        return items
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and not entry.name.endswith(".part"):
                try:
                    st = entry.stat()
                    items.append({
                        "name": entry.name,
                        "encoded": quote(entry.name),
                        "size": format_size(st.st_size),
                        "mtime": st.st_mtime,
                        "time_str": datetime.fromtimestamp(st.st_mtime).strftime("%b %d, %Y %H:%M"),
                        "badge": badge_for_file(entry.name),
                    })
                except OSError:
                    continue
    except OSError:
        pass
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def make_svg_qr(url_str):
    global _CACHED_QR_KEY, _CACHED_QR_SVG
    if _CACHED_QR_KEY == url_str and _CACHED_QR_SVG:
        return _CACHED_QR_SVG
    qr_obj = segno.make(url_str, error="m", micro=False)
    buf = BytesIO()
    qr_obj.save(
        buf,
        kind="svg",
        xmldecl=False,
        scale=8,
        border=4,
        dark="#0f172a",
        light="#ffffff",
    )
    svg_text = buf.getvalue().decode("utf-8").strip()
    m = re.search(r'width="(\d+)"\s+height="(\d+)"', svg_text)
    if m and "viewBox=" not in svg_text:
        w, h = m.group(1), m.group(2)
        svg_text = svg_text.replace("<svg ", f'<svg viewBox="0 0 {w} {h}" ', 1)
    _CACHED_QR_KEY = url_str
    _CACHED_QR_SVG = svg_text
    return svg_text


def is_local_request():
    ip = request.remote_addr
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    try:
        if ip:
            if ip == get_laptop_ip():
                return True
            local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            if ip in local_ips:
                return True
    except Exception:
        pass
    return False


def is_session_authenticated():
    if is_local_request():
        return True
    with STATE_LOCK:
        current_code = ACCESS_CODE
    if session.get("verified_code") == current_code:
        return True
    if session.get("link_verified"):
        return True
    return False


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_session_authenticated():
            return jsonify({
                "ok": False,
                "need_code": True,
                "error": "Authentication required. Please enter the 6-digit Access Code."
            }), 401
        return fn(*args, **kwargs)
    return wrapper


# ==============================================================================
# ULTRA-CLEAN ENGLISH UI WITH DARK/LIGHT MODE & SMOOTH MOTION (NO EMOJIS)
# ==============================================================================

SHARED_CSS = """
:root {
    --bg-primary: #f8fafc;
    --bg-secondary: #ffffff;
    --bg-subtle: #f1f5f9;
    --bg-glass: rgba(255, 255, 255, 0.85);
    --text-primary: #0f172a;
    --text-secondary: #475569;
    --text-muted: #94a3b8;
    --accent: #4f46e5;
    --accent-hover: #4338ca;
    --accent-soft: rgba(79, 70, 229, 0.1);
    --accent-glow: rgba(79, 70, 229, 0.25);
    --border-color: #e2e8f0;
    --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.04);
    --shadow-lg: 0 12px 32px -4px rgba(15, 23, 42, 0.08);
    --success-bg: rgba(16, 185, 129, 0.12);
    --success-text: #059669;
    --success-border: rgba(16, 185, 129, 0.3);
    --danger-bg: rgba(239, 68, 68, 0.12);
    --danger-text: #dc2626;
    --danger-border: rgba(239, 68, 68, 0.3);
    --mesh-1: rgba(79, 70, 229, 0.08);
    --mesh-2: rgba(14, 165, 233, 0.08);
}

[data-theme="dark"] {
    --bg-primary: #090d16;
    --bg-secondary: #111827;
    --bg-subtle: #1e293b;
    --bg-glass: rgba(17, 24, 39, 0.85);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #6366f1;
    --accent-hover: #818cf8;
    --accent-soft: rgba(99, 102, 241, 0.15);
    --accent-glow: rgba(99, 102, 241, 0.35);
    --border-color: #1f2937;
    --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
    --shadow-lg: 0 16px 40px -4px rgba(0, 0, 0, 0.5);
    --success-bg: rgba(16, 185, 129, 0.15);
    --success-text: #34d399;
    --success-border: rgba(16, 185, 129, 0.35);
    --danger-bg: rgba(239, 68, 68, 0.15);
    --danger-text: #f87171;
    --danger-border: rgba(239, 68, 68, 0.35);
    --mesh-1: rgba(99, 102, 241, 0.14);
    --mesh-2: rgba(14, 165, 233, 0.1);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: var(--bg-primary);
    background-image:
        radial-gradient(at 15% 15%, var(--mesh-1) 0px, transparent 50%),
        radial-gradient(at 85% 85%, var(--mesh-2) 0px, transparent 50%);
    background-attachment: fixed;
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.5;
    transition: background-color 0.35s cubic-bezier(0.16, 1, 0.3, 1), color 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    -webkit-font-smoothing: antialiased;
}

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(14px) scale(0.99); }
    to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes pulseDot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.35); opacity: 0.65; }
}

@keyframes floatSlow {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-4px); }
}

.animate-in {
    animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.delay-1 { animation-delay: 0.06s; opacity: 0; }
.delay-2 { animation-delay: 0.12s; opacity: 0; }
.delay-3 { animation-delay: 0.18s; opacity: 0; }

.theme-toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    height: 40px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-primary);
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.theme-toggle:hover {
    transform: translateY(-1px);
    border-color: var(--accent);
    box-shadow: 0 4px 12px var(--accent-glow);
}

.theme-toggle:active {
    transform: scale(0.96);
}

.theme-toggle svg {
    width: 16px;
    height: 16px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.theme-toggle:hover svg {
    transform: rotate(20deg);
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    background: var(--success-bg);
    color: var(--success-text);
    border: 1px solid var(--success-border);
    transition: all 0.3s ease;
}

.status-pill.warn {
    background: var(--danger-bg);
    color: var(--danger-text);
    border-color: var(--danger-border);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    animation: pulseDot 2s infinite ease-in-out;
}

.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 20px;
    padding: 24px;
    box-shadow: var(--shadow-lg);
    transition: background-color 0.35s ease, border-color 0.35s ease, transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.btn {
    min-height: 46px;
    padding: 10px 18px;
    border-radius: 12px;
    border: 1px solid transparent;
    font-family: inherit;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    text-decoration: none;
    transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.btn:active {
    transform: scale(0.97);
}

.btn-primary {
    background: var(--accent);
    color: #ffffff;
    box-shadow: 0 4px 14px var(--accent-glow);
}

.btn-primary:hover {
    background: var(--accent-hover);
    transform: translateY(-1px);
    box-shadow: 0 6px 20px var(--accent-glow);
}

.btn-outline {
    background: var(--bg-secondary);
    border-color: var(--border-color);
    color: var(--text-primary);
}

.btn-outline:hover {
    background: var(--bg-subtle);
    border-color: var(--accent);
    transform: translateY(-1px);
}

.btn-danger {
    background: var(--danger-bg);
    color: var(--danger-text);
    border-color: var(--danger-border);
}

.btn-danger:hover {
    opacity: 0.9;
    transform: translateY(-1px);
}
"""

THEME_SCRIPT = """
function initTheme() {
    const saved = localStorage.getItem('usb_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeBtn(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('usb_theme', next);
    updateThemeBtn(next);
}

function updateThemeBtn(mode) {
    const label = document.getElementById('themeLabel');
    const icon = document.getElementById('themeIcon');
    if (!label || !icon) return;
    if (mode === 'dark') {
        label.textContent = 'Light Mode';
        icon.innerHTML = '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>';
    } else {
        label.textContent = 'Dark Mode';
        icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
    }
}
initTheme();

function showToast(title, msg, isError) {
    const overlay = document.getElementById('toastOverlay');
    const icon = document.getElementById('toastIcon');
    const titleEl = document.getElementById('toastTitle');
    const msgEl = document.getElementById('toastMsg');
    const path = document.getElementById('toastPath');
    if (!overlay) return;

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = msg;
    if (icon && path) {
        if (isError) {
            icon.className = 'toast-icon err';
            path.setAttribute('d', 'M6 6l12 12M6 18L18 6');
        } else {
            icon.className = 'toast-icon';
            path.setAttribute('d', 'M5 12.5l4.5 4.5L19 7.5');
        }
    }
    overlay.classList.add('show');
    clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(hideToast, 4000);
}

function hideToast() {
    const overlay = document.getElementById('toastOverlay');
    if (overlay) overlay.classList.remove('show');
}
"""

MOBILE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>USB File Transfer</title>
<style>
""" + SHARED_CSS + """
.container {
    max-width: 580px;
    margin: 0 auto;
    padding: 24px 16px 56px;
}
.nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
.brand-mark {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: var(--accent);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px var(--accent-glow);
}
.brand-mark svg {
    width: 18px;
    height: 18px;
    stroke: #fff;
    fill: none;
    stroke-width: 2.2;
}
.status-row {
    margin-bottom: 20px;
}
.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}
.section-title {
    font-size: 1rem;
    font-weight: 700;
}
.section-sub {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 16px;
}
.code-input {
    width: 100%;
    height: 58px;
    border: 1.5px solid var(--border-color);
    border-radius: 14px;
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: 8px;
    text-align: center;
    color: var(--text-primary);
    background: var(--bg-subtle);
    outline: none;
    transition: all 0.2s ease;
}
.code-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
}
.dropzone {
    display: block;
    border: 2px dashed var(--border-color);
    background: var(--bg-subtle);
    border-radius: 16px;
    padding: 32px 18px;
    text-align: center;
    cursor: pointer;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.dropzone:hover, .dropzone.dragover {
    border-color: var(--accent);
    background: var(--accent-soft);
    transform: translateY(-2px);
}
.dropzone-icon {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    background: var(--accent);
    color: #fff;
    margin: 0 auto 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 16px var(--accent-glow);
    animation: floatSlow 3s infinite ease-in-out;
}
.dropzone-icon svg {
    width: 24px;
    height: 24px;
    stroke: #fff;
    fill: none;
    stroke-width: 2.2;
}
.alert-box {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: 12px;
    font-size: 0.86rem;
    font-weight: 600;
    display: none;
    word-break: break-all;
    animation: fadeUp 0.3s ease forwards;
}
.alert-ok { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); display: block; }
.alert-err { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); display: block; }
.prog-card {
    background: var(--bg-subtle);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 12px;
    margin-top: 10px;
    animation: fadeUp 0.25s ease forwards;
}
.prog-head {
    display: flex;
    justify-content: space-between;
    font-size: 0.84rem;
    font-weight: 600;
    margin-bottom: 6px;
}
.prog-track {
    height: 7px;
    background: var(--border-color);
    border-radius: 99px;
    overflow: hidden;
}
.prog-bar {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--accent), #38bdf8);
    border-radius: 99px;
    transition: width 0.2s ease;
}
.file-card {
    border: 1px solid var(--border-color);
    background: var(--bg-subtle);
    border-radius: 14px;
    padding: 14px;
    margin-top: 10px;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    animation: fadeUp 0.35s ease forwards;
}
.file-card:hover {
    border-color: var(--accent);
    transform: translateY(-1px);
}
.file-top {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}
.file-badge {
    min-width: 52px;
    height: 38px;
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.75rem;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.file-info { flex: 1; min-width: 0; }
.file-name {
    font-size: 0.92rem;
    font-weight: 600;
    word-break: break-all;
}
.file-meta {
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-top: 2px;
}
.file-actions {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
}
.usb-list { display: flex; flex-direction: column; gap: 8px; }
.usb-option {
    padding: 12px 14px;
    border-radius: 12px;
    border: 1.5px solid var(--border-color);
    background: var(--bg-subtle);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.2s ease;
}
.usb-option.active {
    border-color: var(--accent);
    background: var(--accent-soft);
}
.toast-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(2, 6, 23, 0.45);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 999;
    padding: 20px;
}
.toast-overlay.show {
    opacity: 1;
    pointer-events: auto;
}
.toast-card {
    width: 100%;
    max-width: 340px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 24px;
    padding: 32px 24px 24px;
    text-align: center;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
    transform: translateY(24px) scale(0.92);
    transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.toast-overlay.show .toast-card {
    transform: translateY(0) scale(1);
}
.toast-icon {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    margin: 0 auto 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--success-bg);
    border: 2px solid var(--success-border);
    color: var(--success-text);
}
.toast-icon.err {
    background: var(--danger-bg);
    border-color: var(--danger-border);
    color: var(--danger-text);
}
.toast-icon svg {
    width: 36px;
    height: 36px;
    fill: none;
    stroke: currentColor;
    stroke-width: 3;
    stroke-linecap: round;
    stroke-linejoin: round;
}
.toast-icon svg path {
    stroke-dasharray: 48;
    stroke-dashoffset: 48;
}
.toast-overlay.show .toast-icon {
    animation: popRing 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.toast-overlay.show .toast-icon svg path {
    animation: drawStroke 0.5s 0.25s cubic-bezier(0.65, 0, 0.35, 1) forwards;
}
@keyframes popRing {
    0% { transform: scale(0.4); opacity: 0; }
    100% { transform: scale(1); opacity: 1; }
}
@keyframes drawStroke {
    to { stroke-dashoffset: 0; }
}
.toast-title {
    font-size: 1.25rem;
    font-weight: 800;
    margin-bottom: 6px;
    letter-spacing: -0.01em;
}
.toast-msg {
    font-size: 0.88rem;
    color: var(--text-secondary);
    margin-bottom: 20px;
    word-break: break-word;
}
</style>
</head>
<body>
<div id="toastOverlay" class="toast-overlay" onclick="if(event.target===this)hideToast()">
    <div class="toast-card">
        <div id="toastIcon" class="toast-icon">
            <svg viewBox="0 0 24 24"><path id="toastPath" d="M5 12.5l4.5 4.5L19 7.5"/></svg>
        </div>
        <div id="toastTitle" class="toast-title">Success</div>
        <div id="toastMsg" class="toast-msg">Files uploaded.</div>
        <button type="button" class="btn btn-primary" style="width:100%;" onclick="hideToast()">Done</button>
    </div>
</div>
<div class="container">
    <div class="nav-bar animate-in">
        <div class="brand">
            <div class="brand-mark">
                <svg viewBox="0 0 24 24"><path d="M12 2v14m0-14l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
            </div>
            <span>USB Transfer</span>
        </div>
        <button type="button" class="theme-toggle" onclick="toggleTheme()">
            <svg id="themeIcon" viewBox="0 0 24 24"></svg>
            <span id="themeLabel">Light Mode</span>
        </button>
    </div>

    <div class="status-row animate-in delay-1">
        <div id="usbBadge" class="status-pill {{ 'warn' if not storage.usb_found else '' }}">
            <span class="status-dot"></span>
            <span id="usbBadgeText">
                {% if storage.usb_found %}
                    USB Active: {{ storage.drive_label }} ({{ storage.free_space }} free)
                {% else %}
                    No USB Connected (Uploads Blocked)
                {% endif %}
            </span>
        </div>
    </div>

    {% if not authed %}
    <div class="card animate-in delay-2">
        <div class="section-head">
            <div class="section-title">Enter Access Code</div>
        </div>
        <div class="section-sub">
            Enter the 6-digit Access Code displayed on your laptop control panel to unlock file transfers.
        </div>
        <input type="tel" id="codeField" class="code-input" maxlength="6" placeholder="000000" autocomplete="off">
        <button type="button" class="btn btn-primary" style="width:100%;margin-top:14px;" onclick="verifyAccessCode()">Unlock Session</button>
        <div id="authAlert" class="alert-box"></div>
    </div>
    <script>
    """ + THEME_SCRIPT + """
    async function verifyAccessCode() {
        const input = document.getElementById('codeField');
        const alertBox = document.getElementById('authAlert');
        const code = (input.value || '').replace(/\\s+/g, '');
        if (code.length < 4) {
            alertBox.className = 'alert-box alert-err';
            alertBox.textContent = 'Please enter a valid 6-digit access code.';
            return;
        }
        const r = await fetch('/api/verify-code', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({code: code})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            location.reload();
        } else {
            alertBox.className = 'alert-box alert-err';
            alertBox.textContent = d.error || 'Invalid access code.';
        }
    }
    document.getElementById('codeField').addEventListener('keyup', function(e) {
        if (e.key === 'Enter') verifyAccessCode();
    });
    </script>
    {% else %}

    <div class="card animate-in delay-1" id="usbSelectCard" style="display:{{ 'block' if storage.usb_count > 1 else 'none' }};margin-bottom:16px;">
        <div class="section-head">
            <div class="section-title">Select Target USB Drive</div>
        </div>
        <div class="section-sub">Multiple USB drives detected. Choose which drive to use:</div>
        <div id="usbChoiceList" class="usb-list"></div>
    </div>

    {% if not storage.usb_found %}
    <div class="card animate-in delay-2" style="margin-bottom:16px;border:1.5px solid var(--danger);background:var(--danger-soft);">
        <div style="font-weight:700;color:var(--danger);font-size:1.05rem;margin-bottom:6px;">Uploads Blocked: No USB Flash Drive Connected</div>
        <div style="font-size:0.86rem;color:var(--text-secondary);line-height:1.5;">
            Files are strictly forbidden from being saved to the laptop local disk. Please plug a USB flash drive into the computer to unlock file transfers.
        </div>
    </div>
    {% else %}
    <div class="card animate-in delay-2" style="margin-bottom:16px;">
        <div class="section-head">
            <div class="section-title">Upload Files Directly to USB ({{ storage.active_drive }})</div>
            <span style="font-size:0.78rem;color:var(--text-secondary);">Max 2 GB / file</span>
        </div>
        <label for="filePicker" class="dropzone" id="dropArea">
            <div class="dropzone-icon">
                <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <div style="font-weight:700;font-size:0.98rem;">Tap to select files or drag & drop</div>
            <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:4px;">Files are stored directly inside {{ storage.active_drive }}\\{{ storage.folder_name }}</div>
        </label>
        <input type="file" id="filePicker" multiple style="display:none">
        <div id="mainAlert" class="alert-box"></div>
        <div id="progressContainer"></div>
    </div>
    {% endif %}

    <div class="card animate-in delay-3">
        <div class="section-head">
            <div class="section-title">Files on USB (<span id="countLabel">0</span>)</div>
            <button type="button" class="btn btn-outline" style="min-height:36px;padding:6px 12px;font-size:0.8rem;" onclick="loadUsbFiles()">Refresh</button>
        </div>
        <div id="filesContainer" style="color:var(--text-secondary);font-size:0.88rem;">Loading files...</div>
    </div>

    <script>
    """ + THEME_SCRIPT + """
    const filePicker = document.getElementById('filePicker');
    const dropArea = document.getElementById('dropArea');
    const progressContainer = document.getElementById('progressContainer');
    const mainAlert = document.getElementById('mainAlert');
    const filesContainer = document.getElementById('filesContainer');
    const usbSelectCard = document.getElementById('usbSelectCard');
    const usbChoiceList = document.getElementById('usbChoiceList');

    function showNotice(text, isError) {
        mainAlert.textContent = text;
        mainAlert.className = 'alert-box ' + (isError ? 'alert-err' : 'alert-ok');
    }

    ['dragenter', 'dragover'].forEach(evt => {
        dropArea.addEventListener(evt, e => { e.preventDefault(); dropArea.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(evt => {
        dropArea.addEventListener(evt, e => { e.preventDefault(); dropArea.classList.remove('dragover'); });
    });
    dropArea.addEventListener('drop', e => {
        if (e.dataTransfer && e.dataTransfer.files.length) {
            startBatchUpload(Array.from(e.dataTransfer.files));
        }
    });

    filePicker.addEventListener('change', function() {
        const list = Array.from(this.files || []);
        if (!list.length) return;
        this.value = '';
        startBatchUpload(list);
    });

    async function selectUsb(drive) {
        const r = await fetch('/api/select-usb', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({drive: drive})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            showNotice('Switched active storage to ' + drive, false);
            loadUsbFiles();
        } else {
            showNotice(d.error || 'Could not select USB drive.', true);
        }
    }

    function updateUsbSelector(storage) {
        if (!storage || storage.usb_count <= 1) {
            usbSelectCard.style.display = 'none';
            return;
        }
        usbSelectCard.style.display = 'block';
        usbChoiceList.innerHTML = '';
        storage.usbs.forEach(u => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'usb-option' + (storage.active_drive === u.drive ? ' active' : '');
            const left = document.createElement('span');
            left.textContent = u.display;
            const right = document.createElement('span');
            right.style.fontSize = '0.8rem';
            right.textContent = (storage.active_drive === u.drive ? 'Active | ' : '') + u.free_space + ' free';
            btn.appendChild(left);
            btn.appendChild(right);
            btn.onclick = () => selectUsb(u.drive);
            usbChoiceList.appendChild(btn);
        });
    }

    async function startBatchUpload(list) {
        progressContainer.innerHTML = '';
        mainAlert.style.display = 'none';
        let okCount = 0, failCount = 0;

        const tasks = list.map((f, idx) => {
            const item = document.createElement('div');
            item.className = 'prog-card';
            item.innerHTML = `
                <div class="prog-head">
                    <span id="pName_${idx}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:75%;"></span>
                    <span id="pPct_${idx}">0%</span>
                </div>
                <div class="prog-track"><div class="prog-bar" id="pBar_${idx}"></div></div>
                <div id="pMsg_${idx}" style="font-size:0.76rem;color:var(--text-secondary);margin-top:4px;">Queued...</div>
            `;
            progressContainer.appendChild(item);
            document.getElementById(`pName_${idx}`).textContent = f.name;
            return {f, idx};
        });

        for (const t of tasks) {
            const ok = await uploadFileItem(t.f, t.idx);
            if (ok) okCount++; else failCount++;
        }

        if (failCount === 0 && okCount > 0) {
            showNotice(`Successfully uploaded ${okCount} file(s) to USB.`, false);
            showToast('Success!', `All ${okCount} file(s) successfully saved to your USB drive.`, false);
        } else if (okCount > 0 && failCount > 0) {
            showNotice(`Uploaded ${okCount} file(s), failed ${failCount} file(s).`, true);
            showToast('Partial Upload', `Saved ${okCount} file(s), but ${failCount} failed.`, true);
        } else if (failCount > 0) {
            showNotice(`Failed to upload ${failCount} file(s).`, true);
            showToast('Upload Failed', `Could not upload files to USB drive.`, true);
        }
        loadUsbFiles();
    }

    function uploadFileItem(fileObj, idx) {
        return new Promise((resolve) => {
            const pctEl = document.getElementById(`pPct_${idx}`);
            const barEl = document.getElementById(`pBar_${idx}`);
            const msgEl = document.getElementById(`pMsg_${idx}`);

            if (fileObj.size > 2 * 1024 * 1024 * 1024) {
                pctEl.textContent = 'Over 2GB';
                barEl.style.background = '#dc2626';
                barEl.style.width = '100%';
                msgEl.textContent = 'File exceeds 2GB limit.';
                return resolve(false);
            }

            const xhr = new XMLHttpRequest();
            const fd = new FormData();
            fd.append('file', fileObj);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const p = Math.round((e.loaded / e.total) * 100);
                    pctEl.textContent = p + '%';
                    barEl.style.width = p + '%';
                    msgEl.textContent = 'Uploading to USB...';
                }
            };

            xhr.onload = () => {
                try {
                    const d = JSON.parse(xhr.responseText || '{}');
                    if (xhr.status >= 200 && xhr.status < 300 && d.ok) {
                        pctEl.textContent = '100%';
                        barEl.style.background = '#10b981';
                        barEl.style.width = '100%';
                        msgEl.textContent = 'Saved as: ' + d.saved_name;
                        resolve(true);
                    } else {
                        pctEl.textContent = 'Failed';
                        barEl.style.background = '#dc2626';
                        msgEl.textContent = d.error || 'Upload failed';
                        resolve(false);
                    }
                } catch (err) {
                    pctEl.textContent = 'Error';
                    msgEl.textContent = 'Server response error';
                    resolve(false);
                }
            };

            xhr.onerror = () => {
                pctEl.textContent = 'Offline';
                barEl.style.background = '#dc2626';
                msgEl.textContent = 'Network connection lost';
                resolve(false);
            };

            xhr.open('POST', '/upload', true);
            xhr.send(fd);
        });
    }

    async function generateFileLink(encName) {
        const r = await fetch('/api/generate-link', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({file: encName, minutes: 30})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(d.url);
                showNotice('Direct download link copied: ' + d.url, false);
            } else {
                prompt('Copy direct file link:', d.url);
            }
        }
    }

    async function deleteUsbFile(rawName, encName) {
        if (!confirm(`Delete "${rawName}" from USB drive?`)) return;
        const r = await fetch('/delete/' + encName, {method: 'POST'});
        const d = await r.json();
        if (r.ok && d.ok) {
            showNotice(`Deleted "${rawName}".`, false);
            loadUsbFiles();
        } else {
            showNotice(d.error || 'Could not delete file.', true);
        }
    }

    async function loadUsbFiles() {
        try {
            const r = await fetch('/api/files');
            if (r.status === 401) {
                location.reload();
                return;
            }
            const d = await r.json();
            if (!d.ok) return;

            updateUsbSelector(d.storage);
            document.getElementById('countLabel').textContent = d.files.length;

            const badge = document.getElementById('usbBadge');
            const badgeTxt = document.getElementById('usbBadgeText');
            if (d.storage.need_selection) {
                badge.className = 'status-pill warn';
                badgeTxt.textContent = 'Action Required: Select a USB Drive';
            } else if (d.storage.usb_found) {
                badge.className = 'status-pill';
                badgeTxt.textContent = `USB Active: ${d.storage.drive_label} (${d.storage.free_space} free)`;
            } else {
                badge.className = 'status-pill warn';
                badgeTxt.textContent = 'No USB Detected (Using Local Fallback)';
            }

            if (!d.files.length) {
                filesContainer.innerHTML = '<div style="text-align:center;color:var(--text-secondary);padding:24px 0;">No files stored on USB yet.</div>';
                return;
            }

            filesContainer.innerHTML = '';
            d.files.forEach(f => {
                const item = document.createElement('div');
                item.className = 'file-card';

                const top = document.createElement('div');
                top.className = 'file-top';

                const tag = document.createElement('div');
                tag.className = 'file-badge';
                tag.textContent = f.badge;

                const meta = document.createElement('div');
                meta.className = 'file-info';
                const title = document.createElement('div');
                title.className = 'file-name';
                title.textContent = f.name;
                const sub = document.createElement('div');
                sub.className = 'file-meta';
                sub.textContent = `${f.size}  |  ${f.time_str}`;
                meta.appendChild(title);
                meta.appendChild(sub);

                top.appendChild(tag);
                top.appendChild(meta);

                const actions = document.createElement('div');
                actions.className = 'file-actions';

                const aDl = document.createElement('a');
                aDl.className = 'btn btn-outline';
                aDl.style.minHeight = '40px';
                aDl.href = '/download/' + f.encoded;
                aDl.setAttribute('download', '');
                aDl.textContent = 'Download';

                const bShare = document.createElement('button');
                bShare.className = 'btn btn-outline';
                bShare.style.minHeight = '40px';
                bShare.textContent = 'Copy Link';
                bShare.onclick = () => generateFileLink(f.encoded);

                const bDel = document.createElement('button');
                bDel.className = 'btn btn-danger';
                bDel.style.minHeight = '40px';
                bDel.textContent = 'Delete';
                bDel.onclick = () => deleteUsbFile(f.name, f.encoded);

                actions.appendChild(aDl);
                actions.appendChild(bShare);
                actions.appendChild(bDel);

                item.appendChild(top);
                item.appendChild(actions);
                filesContainer.appendChild(item);
            });
        } catch (err) {
            filesContainer.innerHTML = '<div style="color:var(--danger-text);text-align:center;">Unable to load file list.</div>';
        }
    }

    loadUsbFiles();
    </script>
    {% endif %}
</div>
</body>
</html>
"""

LAPTOP_QR_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>USB File Transfer - Control Center</title>
<style>
""" + SHARED_CSS + """
.shell {
    max-width: 920px;
    margin: 0 auto;
    padding: 32px 20px 56px;
}
.header-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 24px;
}
.brand-block {
    display: flex;
    align-items: center;
    gap: 14px;
}
.brand-icon {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 18px var(--accent-glow);
}
.brand-icon svg {
    width: 22px;
    height: 22px;
    stroke: #fff;
    fill: none;
    stroke-width: 2.2;
}
.brand-text h1 {
    font-size: 1.35rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
.brand-text p {
    font-size: 0.84rem;
    color: var(--text-secondary);
}
.header-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.usb-selector-banner {
    background: var(--bg-secondary);
    border: 1.5px solid var(--accent);
    border-radius: 18px;
    padding: 20px;
    margin-bottom: 24px;
    display: none;
    box-shadow: var(--shadow-lg);
    animation: fadeUp 0.35s ease forwards;
}
.usb-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 12px;
    margin-top: 12px;
}
.usb-drive-card {
    padding: 14px 16px;
    border-radius: 14px;
    border: 1.5px solid var(--border-color);
    background: var(--bg-subtle);
    color: var(--text-primary);
    font-family: inherit;
    text-align: left;
    cursor: pointer;
    transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
.usb-drive-card:hover {
    transform: translateY(-2px);
    border-color: var(--accent);
}
.usb-drive-card.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
    box-shadow: 0 4px 16px var(--accent-glow);
}
.grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    align-items: stretch;
}
@media (max-width: 740px) {
    .grid-2 { grid-template-columns: 1fr; }
}
.panel-head {
    margin-bottom: 18px;
}
.panel-title {
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 4px;
}
.panel-sub {
    font-size: 0.84rem;
    color: var(--text-secondary);
}
.qr-stage {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 16px;
    background: #ffffff;
    border-radius: 18px;
    border: 1px solid var(--border-color);
    margin: 0 auto 18px;
    width: fit-content;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.qr-stage:hover {
    transform: scale(1.02);
}
.qr-stage svg {
    width: 220px;
    height: auto;
    display: block;
}
.timer-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-subtle);
    border: 1px solid var(--border-color);
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 0.84rem;
    margin-bottom: 14px;
}
.seg-switch {
    display: inline-flex;
    background: var(--bg-primary);
    padding: 3px;
    border-radius: 9px;
    border: 1px solid var(--border-color);
}
.seg-opt {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    padding: 4px 10px;
    border-radius: 6px;
    font-family: inherit;
    font-size: 0.76rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
}
.seg-opt.active {
    background: var(--accent);
    color: #ffffff;
}
.code-stage {
    background: var(--bg-subtle);
    border: 1.5px solid var(--border-color);
    border-radius: 16px;
    padding: 24px 16px;
    text-align: center;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
}
.code-caption {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.code-value {
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: 10px;
    color: var(--accent);
    font-family: Consolas, 'SF Mono', monospace;
}
.info-strip {
    background: var(--bg-subtle);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 12px 14px;
    font-size: 0.85rem;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    word-break: break-all;
}
.stack-btns {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.toast-box {
    margin-top: 12px;
    padding: 12px 14px;
    border-radius: 12px;
    background: var(--success-bg);
    border: 1px solid var(--success-border);
    color: var(--success-text);
    font-size: 0.82rem;
    font-weight: 600;
    display: none;
    word-break: break-all;
    animation: fadeUp 0.25s ease forwards;
}
.footer-strip {
    margin-top: 24px;
    padding: 16px 22px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 0.84rem;
    color: var(--text-secondary);
    box-shadow: var(--shadow-sm);
}
.update-banner {
    background: var(--bg-secondary);
    border: 1.5px solid var(--accent);
    border-radius: 16px;
    padding: 14px 18px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    box-shadow: 0 4px 20px var(--accent-glow);
    animation: fadeUp 0.35s ease forwards;
}
.update-banner-content {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
}
.update-badge {
    padding: 4px 10px;
    border-radius: 8px;
    background: var(--accent);
    color: #fff;
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.05em;
}
.update-text {
    font-size: 0.88rem;
    color: var(--text-primary);
}
.update-notes {
    display: block;
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-top: 2px;
}
</style>
</head>
<body>
<div class="shell">
    <div class="header-bar animate-in">
        <div class="brand-block">
            <div class="brand-icon">
                <svg viewBox="0 0 24 24"><path d="M12 2v14m0-14l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>
            </div>
            <div class="brand-text">
                <h1>USB File Transfer</h1>
                <p>Local WiFi High-Speed Phone-to-USB Bridge</p>
            </div>
        </div>
        <div class="header-controls">
            <div id="usbStatusPill" class="status-pill">
                <span class="status-dot"></span>
                <span id="usbStatusText">Checking USB...</span>
            </div>
            <button type="button" class="theme-toggle" id="pinBtn" onclick="installShortcuts()" title="Pin to Taskbar & Desktop">
                <svg viewBox="0 0 24 24"><path d="M12 2v20M2 12h20"/></svg>
                <span>Pin to Taskbar</span>
            </button>
            <button type="button" class="theme-toggle" id="updateBtn" onclick="checkForUpdates(true)">
                <svg viewBox="0 0 24 24"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                <span id="updateBtnText">v{{ current_version }}</span>
            </button>
            <button type="button" class="theme-toggle" onclick="toggleTheme()">
                <svg id="themeIcon" viewBox="0 0 24 24"></svg>
                <span id="themeLabel">Light Mode</span>
            </button>
        </div>
    </div>

    <div id="updateBanner" class="update-banner" style="display:none;">
        <div class="update-banner-content">
            <div class="update-badge">UPDATE</div>
            <div class="update-text">
                <strong>New Version Available:</strong> <span id="newVerTag">v1.0.1</span>
                <span id="updateReleaseNotes" class="update-notes"></span>
            </div>
        </div>
        <button type="button" class="btn btn-primary" id="startUpdateBtn" onclick="applyUpdate()">Update Now</button>
    </div>

    <div id="usbSelectorPanel" class="usb-selector-banner" style="display:block;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <div>
                <div style="font-weight:700;font-size:1.02rem;" id="usbSelectorTitle">Connected USB Flash Drives</div>
                <div style="font-size:0.83rem;color:var(--text-secondary);margin-top:2px;" id="usbSelectorSub">
                    Files from mobile phone are saved strictly to USB storage. Local disk storage is disabled.
                </div>
            </div>
            <button type="button" class="btn btn-outline" style="min-height:36px;padding:6px 14px;font-size:0.82rem;" onclick="refreshState(false, false)">Refresh USB</button>
        </div>
        <div id="usbGrid" class="usb-grid"></div>
    </div>

    <div class="grid-2">
        <!-- Left Card: QR Scanner -->
        <div class="card animate-in delay-1" style="display:flex;flex-direction:column;justify-content:space-between;">
            <div>
                <div class="panel-head">
                    <div class="panel-title">1. Scan QR Code</div>
                    <div class="panel-sub">Connect your phone to the same WiFi network and scan with your camera</div>
                </div>
                <div class="qr-stage" id="qrContainer">{{ qr_svg | safe }}</div>
            </div>
            <div>
                <div class="timer-bar">
                    <span>Auto-refresh in <strong id="timerText" style="color:var(--text-primary);">05:00</strong></span>
                    <div class="seg-switch">
                        <button type="button" id="btn5m" class="seg-opt active" onclick="changeInterval(5)">5 Min</button>
                        <button type="button" id="btn10m" class="seg-opt" onclick="changeInterval(10)">10 Min</button>
                    </div>
                </div>
                <button type="button" class="btn btn-outline" style="width:100%;" onclick="refreshState(true, false)">Regenerate QR Code Now</button>
            </div>
        </div>

        <!-- Right Card: Access Code & Direct Link Generator -->
        <div class="card animate-in delay-2" style="display:flex;flex-direction:column;justify-content:space-between;">
            <div>
                <div class="panel-head">
                    <div class="panel-title">2. Access Code & Share Link</div>
                    <div class="panel-sub">Enter this 6-digit code on your phone after scanning, or generate a direct link</div>
                </div>

                <div class="code-stage">
                    <div class="code-caption">Security Access Code</div>
                    <div class="code-value" id="accessCodeText">{{ access_code }}</div>
                </div>

                <div class="info-strip">
                    <span>Server URL: <strong id="baseUrlText" style="color:var(--text-primary);">{{ target_url }}</strong></span>
                </div>
            </div>

            <div class="stack-btns">
                <button type="button" class="btn btn-primary" onclick="refreshState(false, true)">Generate New Access Code</button>
                <button type="button" class="btn btn-outline" onclick="createDirectLink()">Generate & Copy Direct Link (30m)</button>
                <div id="shareOutput" class="toast-box"></div>
            </div>
        </div>
    </div>

    <div class="footer-strip animate-in delay-3">
        <div>Active Storage Folder: <strong id="savePathText" style="color:var(--text-primary);">{{ storage.upload_dir }}</strong></div>
        <a href="/" target="_blank" style="color:var(--accent);font-weight:700;text-decoration:none;">Open Web Uploader on Laptop</a>
    </div>
</div>

<script>
""" + THEME_SCRIPT + """
let lastQrId = "{{ qr_id }}";

function formatMMSS(totalSec) {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

async function selectUsbDrive(drv) {
    await fetch('/api/select-usb', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({drive: drv})
    });
    refreshState(false, false);
}

async function changeInterval(mins) {
    await fetch('/api/set-interval', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({minutes: mins})
    });
    refreshState(false, false);
}

async function createDirectLink() {
    try {
        const r = await fetch('/api/generate-link', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({minutes: 30})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            const out = document.getElementById('shareOutput');
            out.style.display = 'block';
            out.textContent = 'Direct Link: ' + d.url;
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(d.url);
                    out.textContent = 'Direct Link Copied to Clipboard: ' + d.url;
                } else {
                    const temp = document.createElement('textarea');
                    temp.value = d.url;
                    document.body.appendChild(temp);
                    temp.select();
                    document.execCommand('copy');
                    document.body.removeChild(temp);
                    out.textContent = 'Direct Link Copied to Clipboard: ' + d.url;
                }
            } catch (err) {}
        }
    } catch(e) {}
}

async function refreshState(forceQr, forceCode) {
    try {
        const q = `?force_qr=${forceQr ? 1 : 0}&force_code=${forceCode ? 1 : 0}`;
        const r = await fetch('/api/qr-state' + q);
        if (!r.ok) return;
        const d = await r.json();

        if (d.qr_id !== lastQrId || forceQr) {
            document.getElementById('qrContainer').innerHTML = d.qr_svg;
            lastQrId = d.qr_id;
        }

        document.getElementById('accessCodeText').textContent = d.access_code;
        document.getElementById('timerText').textContent = formatMMSS(d.remaining);
        document.getElementById('baseUrlText').textContent = d.target_url;
        document.getElementById('savePathText').textContent = d.storage.upload_dir;

        document.getElementById('btn5m').className = 'seg-opt' + (d.interval_sec === 300 ? ' active' : '');
        document.getElementById('btn10m').className = 'seg-opt' + (d.interval_sec === 600 ? ' active' : '');

        const pill = document.getElementById('usbStatusPill');
        const pillText = document.getElementById('usbStatusText');
        const selPanel = document.getElementById('usbSelectorPanel');
        const grid = document.getElementById('usbGrid');
        const selTitle = document.getElementById('usbSelectorTitle');
        const selSub = document.getElementById('usbSelectorSub');

        if (d.storage.usb_found && d.storage.usb_count > 0) {
            pill.className = 'status-pill';
            pillText.textContent = `USB: ${d.storage.drive_label} (${d.storage.free_space} free)`;

            if (selPanel) selPanel.style.display = 'block';
            if (selTitle) selTitle.textContent = 'Active Target USB Drive: ' + d.storage.drive_label;
            if (selSub) {
                selSub.textContent = d.storage.usb_count > 1 
                    ? `${d.storage.usb_count} USB drives detected. Click any drive to switch destination:` 
                    : 'Files will be saved directly into this USB drive:';
            }
            if (grid) {
                grid.innerHTML = '';
                d.storage.usbs.forEach(u => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    const active = (d.storage.active_drive === u.drive);
                    btn.className = 'usb-drive-card' + (active ? ' selected' : '');
                    btn.innerHTML = `
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-weight:700;font-size:0.95rem;">${u.display}</span>
                            ${active ? '<span style="font-size:0.72rem;background:var(--accent);color:#fff;padding:2px 7px;border-radius:6px;font-weight:700;">ACTIVE</span>' : ''}
                        </div>
                        <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:6px;">
                            Free: <strong>${u.free_space}</strong> / Total: ${u.total_space}
                        </div>
                    `;
                    btn.onclick = () => selectUsbDrive(u.drive);
                    grid.appendChild(btn);
                });
            }
        } else {
            pill.className = 'status-pill warn';
            pillText.textContent = 'No USB Detected (Uploads Blocked)';
            if (selPanel) selPanel.style.display = 'block';
            if (selTitle) selTitle.textContent = 'No USB Flash Drive Connected';
            if (selSub) selSub.textContent = 'Saving to laptop local disk is strictly prohibited. Please plug in a USB flash drive.';
            if (grid) {
                grid.innerHTML = `
                    <div style="grid-column:1/-1;padding:16px 20px;background:var(--danger-soft);border:1.5px solid var(--danger);border-radius:12px;color:var(--danger);font-weight:600;font-size:0.9rem;">
                        No USB flash drive detected. Please plug a USB flash drive into your laptop. Mobile phone upload is strictly disabled until a USB drive is plugged in.
                    </div>
                `;
            }
        }
    } catch (e) {}
}

let updateDownloadUrl = "";

async function checkForUpdates(manual = false) {
    const btnText = document.getElementById('updateBtnText');
    if (manual && btnText) btnText.textContent = 'Checking...';
    try {
        const r = await fetch('/api/check-update');
        const d = await r.json();
        if (r.ok && d.ok) {
            if (btnText) btnText.textContent = 'v' + d.current_version;
            if (d.has_update) {
                updateDownloadUrl = d.download_url;
                const newVerTag = document.getElementById('newVerTag');
                if (newVerTag) newVerTag.textContent = d.latest_version;
                const notes = document.getElementById('updateReleaseNotes');
                if (notes && d.release_notes) notes.textContent = d.release_notes;
                const banner = document.getElementById('updateBanner');
                if (banner) banner.style.display = 'flex';
                if (btnText) btnText.textContent = 'Update to ' + d.latest_version;
            } else if (manual) {
                alert('You are running the latest version (' + d.current_version + ').');
            }
        } else if (manual) {
            if (btnText) btnText.textContent = 'v{{ current_version }}';
            alert('Could not check for updates. Please check your internet connection.');
        }
    } catch (e) {
        if (manual) alert('Error connecting to update service.');
    }
}

async function applyUpdate() {
    if (!updateDownloadUrl) return;
    const btn = document.getElementById('startUpdateBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Downloading Update...';
    }
    try {
        const r = await fetch('/api/apply-update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({download_url: updateDownloadUrl})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            if (btn) btn.textContent = 'Restarting App...';
            setTimeout(() => {
                location.reload();
            }, 3500);
        } else {
            alert(d.error || 'Update failed.');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Update Now';
            }
        }
    } catch (e) {
        alert('Failed to apply update.');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Update Now';
        }
    }
}

async function installShortcuts() {
    try {
        const r = await fetch('/api/create-shortcuts', {method: 'POST'});
        const d = await r.json();
        if (d.ok) {
            alert(`Shortcuts created on Desktop and Windows Start Menu!

To pin to Taskbar:
1. Open Windows Start Menu
2. Search 'USB File Transfer'
3. Right-click and choose 'Pin to taskbar'.`);
        } else {
            alert("Could not create shortcuts automatically.");
        }
    } catch(e) {
        alert("Error creating shortcuts.");
    }
}

// Check for updates automatically in background
setTimeout(() => { checkForUpdates(false); }, 2500);

refreshState(false, false);
setInterval(() => refreshState(false, false), 1000);
</script>
</body>
</html>
"""


# ==============================================================================
# FLASK ROUTES
# ==============================================================================

@app.errorhandler(RequestEntityTooLarge)
def on_too_large(err):
    return jsonify({"ok": False, "error": "File exceeds the 2GB maximum size limit."}), 413


@app.route("/api/ping", methods=["GET"])
def api_ping():
    return jsonify({"ok": True, "app": "usb_transfer_v3"})


@app.route("/", methods=["GET"])
def home_page():
    link_token = request.args.get("link", "").strip()
    if link_token and verify_share_link_token(link_token):
        session["link_verified"] = True
        dl_file = request.args.get("file", "").strip()
        if dl_file:
            return redirect(url_for("download_route", filename=dl_file))
        return redirect(url_for("home_page"))

    st = resolve_storage()
    return render_template_string(
        MOBILE_PAGE_TEMPLATE,
        storage=st,
        authed=is_session_authenticated(),
    )


@app.route("/api/verify-code", methods=["POST"])
def api_verify_code():
    body = request.get_json(silent=True) or {}
    submitted = str(body.get("code", "")).replace(" ", "").strip()
    state = check_and_rotate_state()
    if submitted and submitted == state["access_code"]:
        session["verified_code"] = state["access_code"]
        return jsonify({"ok": True})
    return jsonify({
        "ok": False,
        "error": "Invalid Access Code. Please check the 6-digit code on your laptop."
    }), 401


@app.route("/qr", methods=["GET"])
def laptop_qr_view():
    if not is_local_request():
        return (
            "<h3 style='font-family:sans-serif;color:#dc2626;text-align:center;margin-top:40px;'>"
            "Access Denied: The /qr control center can only be viewed directly on the host laptop.</h3>"
        ), 403

    state = check_and_rotate_state()
    ip_val = get_laptop_ip()
    qr_url = f"http://{ip_val}:{ACTIVE_PORT}/?q={state['qr_id']}"
    display_url = f"http://{ip_val}:{ACTIVE_PORT}"
    st = resolve_storage()
    return render_template_string(
        LAPTOP_QR_TEMPLATE,
        qr_svg=make_svg_qr(qr_url),
        qr_id=state["qr_id"],
        access_code=state["access_code"],
        target_url=display_url,
        storage=st,
        current_version=APP_VERSION,
    )


@app.route("/api/check-update", methods=["GET"])
def api_check_update():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "USB-Transfer-App",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "")
                latest_ver = parse_version(tag_name)
                current_ver = parse_version(APP_VERSION)
                has_update = latest_ver > current_ver

                download_url = ""
                asset_size = 0
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if name == "usb_transfer.exe":
                        download_url = asset.get("browser_download_url", "")
                        asset_size = asset.get("size", 0)
                        break
                    elif name.endswith(".exe") and not download_url:
                        download_url = asset.get("browser_download_url", "")
                        asset_size = asset.get("size", 0)

                return jsonify({
                    "ok": True,
                    "current_version": APP_VERSION,
                    "latest_version": tag_name,
                    "has_update": has_update and bool(download_url),
                    "download_url": download_url,
                    "asset_size_str": format_size(asset_size),
                    "release_notes": data.get("body", "")[:280] if data.get("body") else "",
                })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not check for updates: {str(e)}"}), 500


@app.route("/api/apply-update", methods=["POST"])
def api_apply_update():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    body = request.get_json(silent=True) or {}
    download_url = body.get("download_url", "").strip()
    if not download_url:
        return jsonify({"ok": False, "error": "No download URL provided."}), 400

    def run_updater_thread():
        try:
            target_exe = sys.executable if getattr(sys, "frozen", False) else None
            if not target_exe or not target_exe.lower().endswith(".exe"):
                target_exe = os.path.join(BASE_DIR, "USB_Transfer.exe")

            temp_new_exe = target_exe + ".new"
            req = urllib.request.Request(download_url, headers={"User-Agent": "USB-Transfer-App"})
            with urllib.request.urlopen(req, timeout=120.0) as resp, open(temp_new_exe, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)

            curr_pid = os.getpid()
            updater_bat = os.path.join(os.path.dirname(target_exe), "_updater_temp.bat")
            with open(updater_bat, "w", encoding="ascii", errors="ignore") as f:
                f.write(f'''@echo off
timeout /t 2 /nobreak >nul
taskkill /F /PID {curr_pid} >nul 2>&1
taskkill /F /IM USB_Transfer.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "{temp_new_exe}" (
    move /y "{target_exe}" "{target_exe}.old" >nul 2>&1
    move /y "{temp_new_exe}" "{target_exe}" >nul 2>&1
    start "" "{target_exe}"
)
timeout /t 2 /nobreak >nul
del "%~f0"
''')
            subprocess.Popen(
                ["cmd.exe", "/c", updater_bat],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            os._exit(0)
        except Exception:
            pass

    threading.Thread(target=run_updater_thread, daemon=True).start()
    return jsonify({"ok": True, "message": "Downloading update and restarting..."})


@app.route("/api/qr-state", methods=["GET"])
def api_qr_state():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    force_qr = request.args.get("force_qr") == "1"
    force_code = request.args.get("force_code") == "1"
    state = check_and_rotate_state(force_qr=force_qr, force_code=force_code)
    ip_val = get_laptop_ip()
    qr_url = f"http://{ip_val}:{ACTIVE_PORT}/?q={state['qr_id']}"
    display_url = f"http://{ip_val}:{ACTIVE_PORT}"
    st = resolve_storage()
    return jsonify({
        "ok": True,
        "qr_id": state["qr_id"],
        "qr_svg": make_svg_qr(qr_url),
        "access_code": state["access_code"],
        "remaining": state["remaining"],
        "interval_sec": state["interval_sec"],
        "target_url": display_url,
        "storage": st,
    })


@app.route("/api/set-interval", methods=["POST"])
def api_set_interval():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    body = request.get_json(silent=True) or {}
    mins = int(body.get("minutes", 5))
    set_rotation_interval(mins)
    return jsonify({"ok": True})


@app.route("/api/generate-link", methods=["POST"])
@require_auth
def api_generate_link():
    body = request.get_json(silent=True) or {}
    minutes = int(body.get("minutes", 30))
    file_target = str(body.get("file", "")).strip()
    token, valid_mins = create_share_link_token(minutes_valid=minutes)
    ip_val = get_laptop_ip()
    if file_target:
        share_url = f"http://{ip_val}:{ACTIVE_PORT}/?link={token}&file={file_target}"
    else:
        share_url = f"http://{ip_val}:{ACTIVE_PORT}/?link={token}"
    return jsonify({
        "ok": True,
        "url": share_url,
        "minutes": valid_mins,
    })


@app.route("/api/select-usb", methods=["POST"])
def api_select_usb():
    if not is_local_request() and not is_session_authenticated():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    global SELECTED_USB_DRIVE
    body = request.get_json(silent=True) or {}
    drv = str(body.get("drive", "")).strip().upper()
    usbs = detect_all_usb_drives(force_refresh=True)
    valid_drives = [u["drive"] for u in usbs]

    if drv not in valid_drives:
        return jsonify({"ok": False, "error": "Selected USB drive is no longer available."}), 400

    with STATE_LOCK:
        SELECTED_USB_DRIVE = drv

    return jsonify({"ok": True, "selected": drv})


@app.route("/api/create-shortcuts", methods=["POST"])
def api_create_shortcuts():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    ok = create_desktop_and_start_menu_shortcuts()
    return jsonify({"ok": ok})


@app.route("/api/files", methods=["GET"])
@require_auth
def list_files_route():
    st = resolve_storage()
    return jsonify({
        "ok": True,
        "storage": st,
        "files": scan_uploaded_files(st["upload_dir"]),
    })


@app.route("/upload", methods=["POST"])
@require_auth
def upload_route():
    st = resolve_storage(force_refresh=True)
    if not st.get("usb_found") or not st.get("upload_dir"):
        return jsonify({
            "ok": False,
            "error": "Transfer Blocked: No USB flash drive detected. Uploads must be stored directly on a connected USB drive."
        }), 403

    if st.get("need_selection"):
        return jsonify({
            "ok": False,
            "error": "Multiple USB drives detected. Please select a target USB drive on the PC first."
        }), 400

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file selected."}), 400

    incoming = request.files["file"]
    if not incoming or not incoming.filename:
        return jsonify({"ok": False, "error": "Empty filename."}), 400

    dest_dir = st["upload_dir"]
    safe_fname = clean_filename(incoming.filename)
    final_name, final_path = unique_destination(dest_dir, safe_fname)
    part_path = f"{final_path}.{os.getpid()}.{secrets.randbelow(9000) + 1000}.part"

    try:
        os.makedirs(dest_dir, exist_ok=True)
        written = 0
        with open(part_path, "wb") as out_fp:
            while True:
                buf = incoming.stream.read(1024 * 1024)
                if not buf:
                    break
                written += len(buf)
                if written > MAX_FILE_SIZE:
                    raise ValueError("OVER_2GB")
                out_fp.write(buf)
            out_fp.flush()
            os.fsync(out_fp.fileno())

        os.replace(part_path, final_path)
        return jsonify({"ok": True, "saved_name": final_name})

    except ValueError:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                pass
        return jsonify({"ok": False, "error": "File exceeds 2GB maximum size."}), 413

    except OSError as err:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                pass
        if getattr(err, "errno", None) == 28 or getattr(err, "winerror", None) == 112:
            msg = "USB drive is full. Please free up some space."
        else:
            msg = "Cannot write to USB drive (USB may have been unplugged or write-protected)."
        return jsonify({"ok": False, "error": msg}), 500


@app.route("/download/<path:filename>", methods=["GET"])
@require_auth
def download_route(filename):
    st = resolve_storage()
    clean = os.path.basename(filename)
    target = os.path.join(st["upload_dir"], clean)
    if not os.path.isfile(target) or clean.endswith(".part"):
        return "<h3 style='color:#dc2626;text-align:center;font-family:sans-serif;'>File not found on USB drive.</h3>", 404
    try:
        return send_from_directory(st["upload_dir"], clean, as_attachment=True)
    except OSError:
        return jsonify({"ok": False, "error": "Could not read file from USB drive."}), 500


@app.route("/delete/<path:filename>", methods=["POST"])
@require_auth
def delete_route(filename):
    st = resolve_storage()
    clean = os.path.basename(filename)
    target = os.path.join(st["upload_dir"], clean)
    if not os.path.isfile(target):
        return jsonify({"ok": False, "error": "File not found."}), 404
    try:
        os.remove(target)
        return jsonify({"ok": True})
    except OSError:
        return jsonify({"ok": False, "error": "Could not delete file from USB drive."}), 500


def open_url_instantly(url):
    """Open URL instantaneously on Windows without shell delay"""
    try:
        if os.name == "nt":
            os.startfile(url)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    cleanup_old_binary()
    create_desktop_and_start_menu_shortcuts()
    # Check if our server is already actively listening on port 5000
    already_running = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(0.2)
            test_sock.connect(("127.0.0.1", 5000))
            already_running = True
    except OSError:
        already_running = False

    if already_running:
        # Server is already running on port 5000! Open the page immediately and exit.
        open_url_instantly("http://127.0.0.1:5000/qr")
        sys.exit(0)

    ACTIVE_PORT = 5000
    # Pre-warm caches before opening browser so first page load takes < 10ms
    get_laptop_ip()
    resolve_storage(force_refresh=True)
    threading.Timer(0.15, open_url_instantly, args=(f"http://127.0.0.1:{ACTIVE_PORT}/qr",)).start()
    app.run(host="0.0.0.0", port=ACTIVE_PORT, debug=False, threaded=True)
