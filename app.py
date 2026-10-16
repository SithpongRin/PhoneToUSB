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
import atexit

# Ensure dedicated Windows Taskbar identity and hide console window seamlessly
if os.name == "nt":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass
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
APP_VERSION = "1.1.0"
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
PREVIOUS_QR_ID = None
PREVIOUS_QR_EXPIRE = 0.0
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
    global CURRENT_QR_ID, PREVIOUS_QR_ID, PREVIOUS_QR_EXPIRE, ACCESS_CODE, LAST_ROTATE_TIME
    now = time.time()
    with STATE_LOCK:
        elapsed = now - LAST_ROTATE_TIME
        if force_qr or elapsed >= ROTATE_INTERVAL_SECONDS:
            PREVIOUS_QR_ID = CURRENT_QR_ID
            PREVIOUS_QR_EXPIRE = now + 60
            CURRENT_QR_ID = secrets.token_hex(4)
            LAST_ROTATE_TIME = now
            elapsed = 0
        if force_code:
            ACCESS_CODE = f"{secrets.randbelow(900000) + 100000}"
        remaining = max(1, int(ROTATE_INTERVAL_SECONDS - elapsed))
        return {
            "qr_id": CURRENT_QR_ID,
            "previous_qr_id": PREVIOUS_QR_ID,
            "previous_qr_expire": PREVIOUS_QR_EXPIRE,
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


def find_ssh_exe():
    ssh_path = shutil.which("ssh")
    if ssh_path and os.path.isfile(ssh_path):
        return ssh_path
    sys32_ssh = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    if os.path.isfile(sys32_ssh):
        return sys32_ssh
    return "ssh"


class TunnelManager:
    def __init__(self):
        self.process = None
        self.url = None
        self.status = "stopped"
        self.error = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None and self.url:
                return self.url
            if self.process:
                try:
                    self.process.kill()
                except Exception:
                    pass
                self.process = None
            self.status = "starting"
            self.error = None
            self.url = None

        ssh_exe = find_ssh_exe()

        def run_tunnel():
            cmd = [
                ssh_exe,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=NUL",
                "-o", "ServerAliveInterval=30",
                "-o", "ExitOnForwardFailure=yes",
                "-R", f"80:127.0.0.1:{ACTIVE_PORT}",
                "nokey@localhost.run"
            ]
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                with self.lock:
                    self.process = p

                discovered = None
                for line in p.stdout:
                    if not line:
                        break
                    m = re.search(r"https://[a-zA-Z0-9\-\.]+\.lhr\.life", line)
                    if m:
                        discovered = m.group(0)
                        with self.lock:
                            self.url = discovered
                            self.status = "running"
                        break
                if not discovered:
                    with self.lock:
                        if self.status != "running":
                            self.status = "error"
                            self.error = "Could not obtain public tunnel URL."
            except Exception as e:
                with self.lock:
                    self.status = "error"
                    self.error = str(e)

        threading.Thread(target=run_tunnel, daemon=True).start()
        start_t = time.time()
        while time.time() - start_t < 6.0:
            with self.lock:
                if self.url and self.status == "running":
                    return self.url
                if self.status == "error":
                    break
            time.sleep(0.25)
        return self.url

    def stop(self):
        with self.lock:
            if self.process:
                try:
                    self.process.kill()
                except Exception:
                    pass
                self.process = None
            self.url = None
            self.status = "stopped"
            self.error = None

    def get_info(self):
        with self.lock:
            if self.process and self.process.poll() is not None:
                self.status = "stopped"
                self.url = None
            return {
                "active": self.status == "running" and bool(self.url),
                "url": self.url,
                "status": self.status,
                "error": self.error,
            }

tunnel_mgr = TunnelManager()
atexit.register(tunnel_mgr.stop)
CONNECTION_MODE = "wifi"  # "wifi", "hotspot", "phone", "internet"
SELECTED_IP = None

def get_all_laptop_ips():
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            primary = s.getsockname()[0]
            if primary and not primary.startswith("127."):
                ips.append(primary)
    except OSError:
        pass
    try:
        host = socket.gethostname()
        for ip in socket.gethostbyname_ex(host)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        ips.append("127.0.0.1")
    return ips


def classify_network_modes():
    all_ips = get_all_laptop_ips()
    wifi_ip = None
    hotspot_ip = None
    phone_ip = None

    for ip in all_ips:
        if ip.startswith("192.168.137."):
            hotspot_ip = ip
        elif ip.startswith("192.168.43.") or ip.startswith("172.20.10."):
            phone_ip = ip
        elif not wifi_ip:
            wifi_ip = ip

    if not wifi_ip:
        wifi_ip = all_ips[0] if all_ips else "127.0.0.1"
    if not hotspot_ip:
        hotspot_ip = "192.168.137.1"
    if not phone_ip:
        phone_ip = "192.168.43.1"

    return {
        "wifi": wifi_ip,
        "hotspot": hotspot_ip,
        "phone": phone_ip,
        "all_ips": all_ips,
    }


def get_active_target_url():
    global CONNECTION_MODE
    with STATE_LOCK:
        mode = CONNECTION_MODE
    if mode == "internet":
        info = tunnel_mgr.get_info()
        if info["active"] and info["url"]:
            return info["url"]
    modes = classify_network_modes()
    if mode == "hotspot":
        ip = modes["hotspot"]
    elif mode == "phone":
        ip = modes["phone"]
    else:
        ip = modes["wifi"]
    return f"http://{ip}:{ACTIVE_PORT}"


def get_laptop_ip():
    global SELECTED_IP
    all_ips = get_all_laptop_ips()
    with STATE_LOCK:
        if SELECTED_IP and SELECTED_IP in all_ips:
            return SELECTED_IP
    return all_ips[0]


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
                    ext = os.path.splitext(entry.name)[1].lower()
                    is_img = ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico")
                    is_vid = ext in (".mp4", ".webm", ".mov", ".mkv")
                    is_aud = ext in (".mp3", ".wav", ".m4a", ".ogg", ".aac")
                    is_pdf = ext == ".pdf"
                    is_txt = ext in (".txt", ".log", ".json", ".csv", ".py", ".md", ".html", ".css", ".js", ".xml", ".yaml", ".yml")
                    items.append({
                        "name": entry.name,
                        "encoded": quote(entry.name),
                        "size": format_size(st.st_size),
                        "mtime": st.st_mtime,
                        "time_str": datetime.fromtimestamp(st.st_mtime).strftime("%b %d, %Y %H:%M"),
                        "badge": badge_for_file(entry.name),
                        "ext": ext,
                        "is_image": is_img,
                        "is_video": is_vid,
                        "is_audio": is_aud,
                        "is_pdf": is_pdf,
                        "is_text": is_txt,
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
    if request.headers.get("X-Forwarded-For") or request.headers.get("X-Forwarded-Host"):
        return False
    host = request.headers.get("Host", "").split(":")[0].lower()
    if host and host not in ("localhost", "127.0.0.1", "::1") and not host.startswith("192.168.") and not host.startswith("10.") and not host.startswith("172."):
        return False

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
    --bg-canvas: #f3f3f3;
    --card-bg: rgba(255, 255, 255, 0.85);
    --card-head-bg: rgba(255, 255, 255, 0.45);
    --border-color: rgba(0, 0, 0, 0.08);
    --border-subtle: rgba(0, 0, 0, 0.05);
    --bg-subtle: rgba(0, 0, 0, 0.025);
    --bg-hover: rgba(0, 0, 0, 0.05);
    --text-primary: #181818;
    --text-secondary: #5c5c5c;
    --text-muted: #888888;
    --accent: #0067c0;
    --accent-hover: #005aa3;
    --accent-soft: rgba(0, 103, 192, 0.08);
    --accent-glow: rgba(0, 103, 192, 0.2);
    --accent-text: #ffffff;
    --btn-outline-bg: rgba(255, 255, 255, 0.7);
    --btn-outline-border: rgba(0, 0, 0, 0.12);
    --success-bg: rgba(16, 185, 129, 0.1);
    --success-text: #059669;
    --success-border: rgba(16, 185, 129, 0.25);
    --danger-bg: rgba(239, 68, 68, 0.08);
    --danger-text: #dc2626;
    --danger-border: rgba(239, 68, 68, 0.22);
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.03), 0 2px 8px rgba(0, 0, 0, 0.04);
    --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.06), 0 2px 6px rgba(0, 0, 0, 0.03);
    --card-radius: 12px;
    --btn-radius: 6px;
}

[data-theme="dark"] {
    --bg-canvas: #202020;
    --card-bg: rgba(38, 38, 38, 0.82);
    --card-head-bg: rgba(255, 255, 255, 0.02);
    --border-color: rgba(255, 255, 255, 0.08);
    --border-subtle: rgba(255, 255, 255, 0.05);
    --bg-subtle: rgba(255, 255, 255, 0.03);
    --bg-hover: rgba(255, 255, 255, 0.06);
    --text-primary: #ffffff;
    --text-secondary: #9e9e9e;
    --text-muted: #6e6e6e;
    --accent: #4cc2ff;
    --accent-hover: #33b0f0;
    --accent-soft: rgba(76, 194, 255, 0.12);
    --accent-glow: rgba(76, 194, 255, 0.25);
    --accent-text: #000000;
    --btn-outline-bg: rgba(255, 255, 255, 0.04);
    --btn-outline-border: rgba(255, 255, 255, 0.09);
    --success-bg: rgba(16, 185, 129, 0.14);
    --success-text: #34d399;
    --success-border: rgba(16, 185, 129, 0.28);
    --danger-bg: rgba(239, 68, 68, 0.12);
    --danger-text: #f87171;
    --danger-border: rgba(239, 68, 68, 0.25);
    --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.25);
    --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Segoe UI Variable', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    background-color: var(--bg-canvas);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
    transition: background-color 0.25s ease, color 0.25s ease;
}

@keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes pulseDot {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.6; }
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.version-chip {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 999px;
    background: var(--bg-hover);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
    font-family: Consolas, monospace;
}

.mode-switch-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
    margin-top: 6px;
}

.mode-btn {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 7px 10px;
    border-radius: var(--btn-radius);
    border: 1px solid var(--border-color);
    background: var(--btn-outline-bg);
    color: var(--text-primary);
    cursor: pointer;
    text-align: left;
    transition: all 0.15s ease;
}

.mode-btn:hover {
    background: var(--bg-hover);
    border-color: var(--border-color);
}

.mode-btn.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
}

.mode-btn-title {
    font-size: 0.8rem;
    font-weight: 600;
}

.mode-btn-sub {
    font-size: 0.68rem;
    color: var(--text-muted);
    margin-top: 2px;
}

.mode-btn.active .mode-btn-sub {
    color: var(--accent);
    opacity: 0.85;
}

.animate-in {
    animation: fadeUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.delay-1 { animation-delay: 0.04s; opacity: 0; }
.delay-2 { animation-delay: 0.08s; opacity: 0; }
.delay-3 { animation-delay: 0.12s; opacity: 0; }

.theme-toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    border-radius: var(--btn-radius);
    border: 1px solid var(--btn-outline-border);
    background: var(--btn-outline-bg);
    color: var(--text-primary);
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
}

.theme-toggle:hover {
    background: var(--bg-hover);
    border-color: var(--border-color);
}

.theme-toggle:active {
    transform: scale(0.98);
}

.theme-toggle svg {
    width: 14px;
    height: 14px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    height: 30px;
    padding: 0 11px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 500;
    background: var(--success-bg);
    color: var(--success-text);
    border: 1px solid var(--success-border);
}

.status-pill.warn {
    background: var(--danger-bg);
    color: var(--danger-text);
    border-color: var(--danger-border);
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    animation: pulseDot 2s infinite ease-in-out;
}

/* Modern Fluent Card / Content Dialog */
.card {
    background: var(--card-bg);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    border: 1px solid var(--border-color);
    border-radius: var(--card-radius);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.card:hover {
    box-shadow: var(--shadow-lg);
}

.card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 13px 18px;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--card-head-bg);
}

.card-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
}

.card-body {
    padding: 18px;
}

.card-foot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    padding: 11px 18px;
    border-top: 1px solid var(--border-subtle);
    background: var(--bg-subtle);
}

.btn {
    height: 34px;
    padding: 0 14px;
    border-radius: var(--btn-radius);
    border: 1px solid transparent;
    font-family: inherit;
    font-size: 0.83rem;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    text-decoration: none;
    transition: all 0.15s ease;
    white-space: nowrap;
}

.btn:active {
    transform: scale(0.98);
}

.btn-primary {
    background: var(--accent);
    color: var(--accent-text);
}

.btn-primary:hover {
    background: var(--accent-hover);
    box-shadow: 0 2px 8px var(--accent-glow);
}

.btn-outline {
    background: var(--btn-outline-bg);
    border-color: var(--btn-outline-border);
    color: var(--text-primary);
}

.btn-outline:hover {
    background: var(--bg-hover);
    border-color: var(--border-color);
}

.btn-danger {
    background: var(--danger-bg);
    color: var(--danger-text);
    border-color: var(--danger-border);
}

.btn-danger:hover {
    filter: brightness(0.95);
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
        label.textContent = 'Light';
        icon.innerHTML = '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>';
    } else {
        label.textContent = 'Dark';
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
    max-width: 480px;
    margin: 0 auto;
    padding: 20px 14px 44px;
}
.nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}
.brand-mark {
    width: 28px;
    height: 28px;
    border-radius: var(--btn-radius);
    background: var(--accent);
    color: var(--accent-text);
    display: flex;
    align-items: center;
    justify-content: center;
}
.brand-mark svg {
    width: 15px;
    height: 15px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2.2;
}
.status-row {
    margin-bottom: 14px;
}
.code-input {
    width: 100%;
    height: 48px;
    border: 1px solid var(--border-color);
    border-radius: var(--btn-radius);
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: 6px;
    text-align: center;
    color: var(--text-primary);
    background: var(--bg-subtle);
    outline: none;
    transition: all 0.15s ease;
    font-family: Consolas, monospace;
}
.code-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-soft);
}
.dropzone {
    display: block;
    border: 1.5px dashed var(--border-color);
    background: var(--bg-subtle);
    border-radius: var(--btn-radius);
    padding: 26px 14px;
    text-align: center;
    cursor: pointer;
    transition: all 0.18s ease;
}
.dropzone:hover, .dropzone.dragover {
    border-color: var(--accent);
    background: var(--accent-soft);
}
.dropzone-icon {
    width: 40px;
    height: 40px;
    border-radius: var(--btn-radius);
    background: var(--accent-soft);
    color: var(--accent);
    margin: 0 auto 10px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.dropzone-icon svg {
    width: 20px;
    height: 20px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2;
}
.alert-box {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: var(--btn-radius);
    font-size: 0.82rem;
    font-weight: 500;
    display: none;
    word-break: break-all;
    animation: fadeUp 0.2s ease forwards;
}
.alert-ok { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--success-border); display: block; }
.alert-err { background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border); display: block; }
.prog-card {
    background: var(--bg-subtle);
    border: 1px solid var(--border-subtle);
    border-radius: var(--btn-radius);
    padding: 10px 12px;
    margin-top: 8px;
    animation: fadeUp 0.2s ease forwards;
}
.prog-head {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    font-weight: 500;
    margin-bottom: 5px;
}
.prog-track {
    height: 5px;
    background: var(--border-color);
    border-radius: 99px;
    overflow: hidden;
}
.prog-bar {
    height: 100%;
    width: 0%;
    background: var(--accent);
    border-radius: 99px;
    transition: width 0.15s ease;
}
.file-card {
    border: 1px solid var(--border-subtle);
    background: var(--bg-subtle);
    border-radius: var(--btn-radius);
    padding: 10px 12px;
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: all 0.15s ease;
    animation: fadeUp 0.25s ease forwards;
}
.file-card:hover {
    background: var(--bg-hover);
    border-color: var(--border-color);
}
.file-main {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    min-width: 0;
    width: 100%;
}
.file-thumb-box {
    width: 44px;
    height: 44px;
    border-radius: 6px;
    overflow: hidden;
    background: var(--bg-card);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border-color);
}
.file-thumb-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}
.file-badge {
    width: 44px;
    height: 44px;
    border-radius: 6px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border: 1px solid var(--border-color);
}
.file-details {
    flex: 1;
    min-width: 0;
    overflow: hidden;
}
.file-name {
    font-size: 0.88rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
}
.file-meta {
    font-size: 0.74rem;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 2px;
}
.preview-btn {
    height: 26px;
    padding: 0 10px;
    font-size: 0.72rem;
    font-weight: 500;
    border-radius: 13px;
    flex-shrink: 0;
}
.file-actions-row {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding-top: 6px;
    border-top: 1px solid var(--border-subtle);
}
.file-action-btn {
    flex: 1;
    height: 28px;
    padding: 0 6px;
    font-size: 0.74rem;
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    text-align: center;
}
.preview-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100vw;
    height: 100vh;
    height: 100dvh;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    z-index: 999999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 12px;
    box-sizing: border-box;
}
.preview-modal-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--card-radius);
    width: 100%;
    max-width: 520px;
    max-height: 90vh;
    max-height: 90dvh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
    overflow: hidden;
    margin: auto;
}
.preview-modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-subtle);
    gap: 12px;
    flex-shrink: 0;
}
.preview-modal-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.preview-modal-sub {
    font-size: 0.74rem;
    color: var(--text-muted);
    margin-top: 1px;
}
.preview-modal-body {
    padding: 12px;
    overflow-y: auto;
    overflow-x: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 120px;
    max-height: calc(88dvh - 120px);
    background: var(--bg-subtle);
    flex: 1 1 auto;
}
.preview-modal-foot {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 16px;
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
}
.preview-img {
    max-width: 100%;
    max-height: calc(82dvh - 120px);
    height: auto;
    width: auto;
    object-fit: contain;
    border-radius: 6px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    display: block;
    margin: 0 auto;
}
.preview-video {
    max-width: 100%;
    max-height: calc(82dvh - 120px);
    border-radius: 6px;
    outline: none;
    display: block;
    margin: 0 auto;
}
.preview-audio {
    width: 100%;
    max-width: 420px;
    margin: 20px 0;
}
.preview-text {
    width: 100%;
    max-height: 60vh;
    overflow: auto;
    padding: 12px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-family: Consolas, monospace;
    font-size: 0.82rem;
    white-space: pre-wrap;
    word-break: break-all;
    color: var(--text-primary);
}
.usb-list { display: flex; flex-direction: column; gap: 6px; }
.usb-option {
    padding: 9px 12px;
    border-radius: var(--btn-radius);
    border: 1px solid var(--border-color);
    background: var(--btn-outline-bg);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.84rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.15s ease;
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
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
    z-index: 999;
    padding: 16px;
}
.toast-overlay.show {
    opacity: 1;
    pointer-events: auto;
}
.toast-card {
    width: 100%;
    max-width: 320px;
    background: var(--card-bg);
    backdrop-filter: blur(24px);
    border: 1px solid var(--border-color);
    border-radius: var(--card-radius);
    padding: 22px 18px 16px;
    text-align: center;
    box-shadow: var(--shadow-lg);
    transform: translateY(10px) scale(0.96);
    transition: transform 0.2s ease;
}
.toast-overlay.show .toast-card {
    transform: translateY(0) scale(1);
}
.toast-icon {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    margin: 0 auto 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--success-bg);
    border: 1px solid var(--success-border);
    color: var(--success-text);
}
.toast-icon.err {
    background: var(--danger-bg);
    border-color: var(--danger-border);
    color: var(--danger-text);
}
.toast-icon svg {
    width: 22px;
    height: 22px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.5;
    stroke-linecap: round;
    stroke-linejoin: round;
}
.toast-title {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 4px;
}
.toast-msg {
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin-bottom: 16px;
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

<!-- Media and File Preview Dialog (Root level for proper viewport centering) -->
<div id="previewModal" class="preview-modal-backdrop" style="display:none;" onclick="handleModalBackdropClick(event)">
    <div class="preview-modal-card animate-in">
        <div class="preview-modal-head">
            <div style="min-width:0;flex:1;">
                <div id="previewTitle" class="preview-modal-title">File Preview</div>
                <div id="previewSub" class="preview-modal-sub">Details</div>
            </div>
            <button type="button" class="btn btn-outline" style="width:30px;height:30px;padding:0;display:flex;align-items:center;justify-content:center;border-radius:50%;" onclick="closePreview()">
                <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
        </div>
        <div id="previewBody" class="preview-modal-body"></div>
        <div class="preview-modal-foot">
            <a id="previewDownloadBtn" class="btn btn-primary" href="#" download>Download</a>
            <button type="button" class="btn btn-outline" onclick="copyCurrentPreviewLink()">Copy Link</button>
            <button type="button" class="btn btn-outline" onclick="closePreview()">Close</button>
        </div>
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
            <span id="themeLabel">Light</span>
        </button>
    </div>

    <div class="status-row animate-in delay-1">
        <div id="usbBadge" class="status-pill {{ 'warn' if not storage.usb_found else '' }}">
            <span class="status-dot"></span>
            <span id="usbBadgeText">
                {% if storage.usb_found %}
                    USB: {{ storage.drive_label }} ({{ storage.free_space }} free)
                {% else %}
                    No USB Connected
                {% endif %}
            </span>
        </div>
    </div>

    {% if not authed %}
    <div class="card animate-in delay-2">
        <div class="card-head">
            <div class="card-title">Access Code</div>
        </div>
        <div class="card-body">
            <input type="tel" id="codeField" class="code-input" maxlength="6" placeholder="000000" autocomplete="off">
            <div id="authAlert" class="alert-box"></div>
        </div>
        <div class="card-foot">
            <button type="button" class="btn btn-primary" style="width:100%;" onclick="verifyAccessCode()">Unlock</button>
        </div>
    </div>
    <script>
    """ + THEME_SCRIPT + """
    async function verifyAccessCode() {
        const input = document.getElementById('codeField');
        const alertBox = document.getElementById('authAlert');
        const code = (input.value || '').replace(/\\s+/g, '');
        if (code.length < 4) {
            alertBox.className = 'alert-box alert-err';
            alertBox.textContent = 'Please enter the 6-digit access code.';
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
            alertBox.textContent = d.error || 'Invalid code.';
        }
    }
    document.getElementById('codeField').addEventListener('keyup', function(e) {
        if (e.key === 'Enter') verifyAccessCode();
    });
    </script>
    {% else %}

    <div class="card animate-in delay-1" id="usbSelectCard" style="display:{{ 'block' if storage.usb_count > 1 else 'none' }};margin-bottom:14px;">
        <div class="card-head">
            <div class="card-title">Select USB Drive</div>
        </div>
        <div class="card-body" style="padding:10px 14px;">
            <div id="usbChoiceList" class="usb-list"></div>
        </div>
    </div>

    {% if not storage.usb_found %}
    <div class="card animate-in delay-2" style="margin-bottom:14px;border-color:var(--danger-border);">
        <div class="card-head" style="background:var(--danger-bg);border-bottom-color:var(--danger-border);">
            <div class="card-title" style="color:var(--danger-text);">No USB Connected</div>
        </div>
        <div class="card-body" style="font-size:0.86rem;color:var(--text-secondary);">
            Please plug a USB flash drive into the laptop to enable file transfers.
        </div>
    </div>
    {% else %}
    <div class="card animate-in delay-2" style="margin-bottom:14px;">
        <div class="card-head">
            <div class="card-title">Upload to USB ({{ storage.active_drive }})</div>
            <span style="font-size:0.76rem;color:var(--text-muted);">Max 2 GB</span>
        </div>
        <div class="card-body">
            <label for="filePicker" class="dropzone" id="dropArea">
                <div class="dropzone-icon">
                    <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
                <div style="font-weight:600;font-size:0.92rem;">Choose files or drop here</div>
                <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:2px;">Target: {{ storage.active_drive }}\\{{ storage.folder_name }}</div>
            </label>
            <input type="file" id="filePicker" multiple style="display:none">
            <div id="mainAlert" class="alert-box"></div>
            <div id="progressContainer"></div>
        </div>
    </div>
    {% endif %}

    <div class="card animate-in delay-3">
        <div class="card-head">
            <div class="card-title">Files on USB (<span id="countLabel">0</span>)</div>
            <button type="button" class="btn btn-outline" style="height:28px;padding:0 10px;font-size:0.76rem;" onclick="loadUsbFiles()">Refresh</button>
        </div>
        <div class="card-body" style="padding:10px 14px;">
            <div id="filesContainer" style="color:var(--text-secondary);font-size:0.84rem;">Loading...</div>
        </div>
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
                filesContainer.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px 0;font-size:0.84rem;">No files on USB</div>';
                return;
            }

            filesContainer.innerHTML = '';
            d.files.forEach(f => {
                const item = document.createElement('div');
                item.className = 'file-card';

                const mainRow = document.createElement('div');
                mainRow.className = 'file-main';
                mainRow.onclick = () => openPreview(f);

                if (f.is_image) {
                    const thumbBox = document.createElement('div');
                    thumbBox.className = 'file-thumb-box';
                    const img = document.createElement('img');
                    img.className = 'file-thumb-img';
                    img.src = '/view/' + f.encoded;
                    img.loading = 'lazy';
                    img.alt = f.name;
                    thumbBox.appendChild(img);
                    mainRow.appendChild(thumbBox);
                } else {
                    const tag = document.createElement('div');
                    tag.className = 'file-badge';
                    tag.textContent = f.badge;
                    mainRow.appendChild(tag);
                }

                const details = document.createElement('div');
                details.className = 'file-details';

                const title = document.createElement('div');
                title.className = 'file-name';
                title.title = f.name;
                title.textContent = f.name;

                const sub = document.createElement('div');
                sub.className = 'file-meta';
                sub.textContent = `${f.size} • ${f.time_str}`;

                details.appendChild(title);
                details.appendChild(sub);
                mainRow.appendChild(details);

                const btnPreview = document.createElement('button');
                btnPreview.type = 'button';
                btnPreview.className = 'btn btn-outline preview-btn';
                btnPreview.textContent = 'Preview';
                btnPreview.onclick = (e) => {
                    e.stopPropagation();
                    openPreview(f);
                };
                mainRow.appendChild(btnPreview);

                const actionsRow = document.createElement('div');
                actionsRow.className = 'file-actions-row';

                const aDl = document.createElement('a');
                aDl.className = 'btn btn-outline file-action-btn';
                aDl.href = '/download/' + f.encoded;
                aDl.setAttribute('download', f.name);
                aDl.textContent = 'Download';

                const bShare = document.createElement('button');
                bShare.type = 'button';
                bShare.className = 'btn btn-outline file-action-btn';
                bShare.textContent = 'Copy';
                bShare.onclick = () => generateFileLink(f.encoded);

                const bDel = document.createElement('button');
                bDel.type = 'button';
                bDel.className = 'btn btn-danger file-action-btn';
                bDel.textContent = 'Delete';
                bDel.onclick = () => deleteUsbFile(f.name, f.encoded);

                actionsRow.appendChild(aDl);
                actionsRow.appendChild(bShare);
                actionsRow.appendChild(bDel);

                item.appendChild(mainRow);
                item.appendChild(actionsRow);
                filesContainer.appendChild(item);
            });
        } catch (err) {
            filesContainer.innerHTML = '<div style="color:var(--danger-text);text-align:center;">Unable to load file list.</div>';
        }
    }

    let currentPreviewFile = null;

    function handleModalBackdropClick(e) {
        if (e.target && e.target.id === 'previewModal') {
            closePreview();
        }
    }

    function closePreview() {
        const modal = document.getElementById('previewModal');
        const body = document.getElementById('previewBody');
        if (modal) modal.style.display = 'none';
        if (body) body.innerHTML = '';
        document.body.style.overflow = '';
        currentPreviewFile = null;
    }

    function copyCurrentPreviewLink() {
        if (currentPreviewFile) {
            generateFileLink(currentPreviewFile.encoded);
        }
    }

    function openPreview(f) {
        currentPreviewFile = f;
        const modal = document.getElementById('previewModal');
        const title = document.getElementById('previewTitle');
        const sub = document.getElementById('previewSub');
        const body = document.getElementById('previewBody');
        const dlBtn = document.getElementById('previewDownloadBtn');

        if (!modal || !body) return;

        title.textContent = f.name;
        sub.textContent = `${f.size} • ${f.time_str}`;
        dlBtn.href = '/download/' + f.encoded;
        dlBtn.setAttribute('download', f.name);

        body.innerHTML = '';

        if (f.is_image) {
            const img = document.createElement('img');
            img.className = 'preview-img';
            img.src = '/view/' + f.encoded;
            img.alt = f.name;
            body.appendChild(img);
        } else if (f.is_video) {
            const vid = document.createElement('video');
            vid.className = 'preview-video';
            vid.src = '/view/' + f.encoded;
            vid.controls = true;
            vid.autoplay = true;
            vid.playsInline = true;
            body.appendChild(vid);
        } else if (f.is_audio) {
            const aud = document.createElement('audio');
            aud.className = 'preview-audio';
            aud.src = '/view/' + f.encoded;
            aud.controls = true;
            aud.autoplay = true;
            body.appendChild(aud);
        } else if (f.is_pdf) {
            const frame = document.createElement('iframe');
            frame.style.width = '100%';
            frame.style.height = '65vh';
            frame.style.border = 'none';
            frame.style.borderRadius = '6px';
            frame.src = '/view/' + f.encoded;
            body.appendChild(frame);
        } else if (f.is_text) {
            const pre = document.createElement('pre');
            pre.className = 'preview-text';
            pre.textContent = 'Loading text content...';
            body.appendChild(pre);

            fetch('/view/' + f.encoded)
                .then(r => r.text())
                .then(txt => {
                    pre.textContent = txt.slice(0, 100000) + (txt.length > 100000 ? '\\n\\n... (truncated)' : '');
                })
                .catch(() => {
                    pre.textContent = 'Unable to read file contents.';
                });
        } else {
            const generic = document.createElement('div');
            generic.style.textAlign = 'center';
            generic.style.padding = '24px 0';
            generic.innerHTML = `
                <div class="file-badge" style="width:56px;height:56px;font-size:1.1rem;margin:0 auto 12px;border-radius:10px;">${f.badge}</div>
                <div style="font-weight:600;font-size:0.95rem;margin-bottom:4px;color:var(--text-primary);">${f.name}</div>
                <div style="color:var(--text-muted);font-size:0.8rem;margin-bottom:16px;">${f.size} • ${f.time_str}</div>
                <a href="/download/${f.encoded}" download="${f.name}" class="btn btn-primary" style="height:34px;padding:0 18px;display:inline-flex;align-items:center;">Download File</a>
            `;
            body.appendChild(generic);
        }

        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
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
    max-width: 820px;
    margin: 0 auto;
    padding: 24px 16px 48px;
}
.header-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 18px;
}
.brand-block {
    display: flex;
    align-items: center;
    gap: 10px;
}
.brand-icon {
    width: 32px;
    height: 32px;
    border-radius: var(--btn-radius);
    background: var(--accent);
    color: var(--accent-text);
    display: flex;
    align-items: center;
    justify-content: center;
}
.brand-icon svg {
    width: 17px;
    height: 17px;
    stroke: currentColor;
    fill: none;
    stroke-width: 2.2;
}
.brand-text h1 {
    font-size: 1.12rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}
.header-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.update-banner {
    background: var(--card-bg);
    border: 1px solid var(--accent);
    border-radius: var(--card-radius);
    padding: 10px 14px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    box-shadow: 0 2px 10px var(--accent-soft);
    animation: fadeUp 0.25s ease forwards;
}
.update-banner-content {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
}
.update-badge {
    padding: 2px 7px;
    border-radius: 4px;
    background: var(--accent);
    color: var(--accent-text);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}
.update-text {
    font-size: 0.84rem;
    color: var(--text-primary);
}
.update-notes {
    display: block;
    font-size: 0.76rem;
    color: var(--text-muted);
}
.usb-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 8px;
}
.usb-drive-card {
    padding: 10px 12px;
    border-radius: var(--btn-radius);
    border: 1px solid var(--border-color);
    background: var(--btn-outline-bg);
    color: var(--text-primary);
    font-family: inherit;
    text-align: left;
    cursor: pointer;
    transition: all 0.15s ease;
}
.usb-drive-card:hover {
    background: var(--bg-hover);
    border-color: var(--accent);
}
.usb-drive-card.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
}
.active-badge {
    font-size: 0.68rem;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--accent);
    color: var(--accent-text);
}
.grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    align-items: stretch;
}
@media (max-width: 680px) {
    .grid-2 { grid-template-columns: 1fr; }
}
.qr-stage {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 12px;
    background: #ffffff;
    border-radius: var(--btn-radius);
    border: 1px solid var(--border-subtle);
    margin: 0 auto;
    width: fit-content;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.qr-stage svg {
    width: 190px;
    height: auto;
    display: block;
}
.timer-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.8rem;
    color: var(--text-secondary);
}
.seg-switch {
    display: inline-flex;
    background: var(--bg-subtle);
    padding: 2px;
    border-radius: 5px;
    border: 1px solid var(--border-subtle);
}
.seg-opt {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    padding: 2px 7px;
    border-radius: 3px;
    font-family: inherit;
    font-size: 0.72rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
}
.seg-opt.active {
    background: var(--accent);
    color: var(--accent-text);
}
.code-stage {
    background: var(--bg-subtle);
    border: 1px solid var(--border-subtle);
    border-radius: var(--btn-radius);
    padding: 18px 12px;
    text-align: center;
    margin-bottom: 12px;
}
.code-value {
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: 8px;
    color: var(--accent);
    font-family: Consolas, monospace;
    line-height: 1.1;
}
.info-strip {
    background: var(--bg-subtle);
    border: 1px solid var(--border-subtle);
    border-radius: var(--btn-radius);
    padding: 8px 12px;
    font-size: 0.8rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    word-break: break-all;
}
.toast-box {
    margin-top: 10px;
    padding: 9px 12px;
    border-radius: var(--btn-radius);
    background: var(--success-bg);
    border: 1px solid var(--success-border);
    color: var(--success-text);
    font-size: 0.8rem;
    font-weight: 500;
    display: none;
    word-break: break-all;
    animation: fadeUp 0.2s ease forwards;
}
.footer-strip {
    margin-top: 18px;
    padding: 12px 16px;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--card-radius);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 0.8rem;
    color: var(--text-secondary);
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
            <div class="brand-text" style="display:flex;align-items:center;gap:8px;">
                <h1>USB Transfer</h1>
                <span class="version-chip">v{{ current_version }}</span>
            </div>
        </div>
        <div class="header-controls">
            <div id="usbStatusPill" class="status-pill">
                <span class="status-dot"></span>
                <span id="usbStatusText">Checking USB...</span>
            </div>
            <button type="button" class="theme-toggle" id="pinBtn" onclick="installShortcuts()" title="Pin to Taskbar & Desktop">
                <svg viewBox="0 0 24 24"><path d="M12 2v20M2 12h20"/></svg>
                <span>Pin App</span>
            </button>
            <button type="button" class="theme-toggle" id="updateBtn" onclick="checkForUpdates(true)" title="Check for Updates">
                <svg id="updateIcon" viewBox="0 0 24 24"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                <span id="updateBtnText">Check Update</span>
            </button>
            <button type="button" class="theme-toggle" onclick="toggleTheme()">
                <svg id="themeIcon" viewBox="0 0 24 24"></svg>
                <span id="themeLabel">Light</span>
            </button>
        </div>
    </div>

    <div id="updateBanner" class="update-banner" style="display:none;">
        <div class="update-banner-content">
            <span id="updateBadge" class="update-badge">UPDATE</span>
            <div style="display:flex;flex-direction:column;gap:2px;">
                <span id="updateBannerMsg" class="update-text"><strong>New Version:</strong> <span id="newVerTag">v1.0.1</span></span>
                <span id="updateReleaseNotes" class="update-notes"></span>
            </div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
            <button type="button" class="btn btn-outline" style="height:28px;padding:0 10px;font-size:0.75rem;" onclick="dismissUpdateBanner()">Close</button>
            <button type="button" class="btn btn-primary" id="startUpdateBtn" style="height:28px;padding:0 12px;font-size:0.75rem;display:none;" onclick="applyUpdate()">Update Now</button>
        </div>
    </div>

    <div id="usbSelectorPanel" class="card animate-in delay-1" style="display:block;margin-bottom:16px;">
        <div class="card-head">
            <div class="card-title" id="usbSelectorTitle">Target USB Drive</div>
            <button type="button" class="btn btn-outline" style="height:26px;padding:0 9px;font-size:0.74rem;" onclick="refreshState(false, false)">Refresh</button>
        </div>
        <div class="card-body" style="padding:12px 16px;">
            <div id="usbSelectorSub" style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;display:none;"></div>
            <div id="usbGrid" class="usb-grid"></div>
        </div>
    </div>

    <div class="grid-2">
        <!-- Left: QR Code Content Dialog Card -->
        <div class="card animate-in delay-2" style="display:flex;flex-direction:column;justify-content:space-between;">
            <div>
                <div class="card-head">
                    <div class="card-title">QR Code</div>
                    <div class="timer-chip">
                        <span id="timerText" style="font-family:Consolas,monospace;font-weight:600;">05:00</span>
                        <div class="seg-switch">
                            <button type="button" id="btn5m" class="seg-opt active" onclick="changeInterval(5)">5m</button>
                            <button type="button" id="btn10m" class="seg-opt" onclick="changeInterval(10)">10m</button>
                        </div>
                    </div>
                </div>
                <div class="card-body" style="text-align:center;">
                    <div class="qr-stage" id="qrContainer">{{ qr_svg | safe }}</div>
                </div>
            </div>
            <div class="card-foot">
                <button type="button" class="btn btn-outline" style="width:100%;" onclick="refreshState(true, false)">Regenerate QR Code</button>
            </div>
        </div>

        <!-- Right: Access Code Content Dialog Card -->
        <div class="card animate-in delay-3" style="display:flex;flex-direction:column;justify-content:space-between;">
            <div>
                <div class="card-head">
                    <div class="card-title">Access Code</div>
                    <span style="font-size:0.76rem;color:var(--text-muted);">Security PIN</span>
                </div>
                <div class="card-body">
                    <div class="code-stage">
                        <div class="code-value" id="accessCodeText">{{ access_code }}</div>
                    </div>
                    <div class="info-strip">
                        <span style="color:var(--text-muted);">Server URL:</span>
                        <strong id="baseUrlText" style="color:var(--text-primary);font-family:Consolas,monospace;">{{ target_url }}</strong>
                    </div>
                    <div style="margin-top:14px;border-top:1px solid var(--border-color);padding-top:12px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                            <span style="font-size:0.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">Connection Mode</span>
                            <span id="modeStatusBadge" style="font-size:0.7rem;padding:2px 8px;border-radius:10px;background:var(--accent-soft);color:var(--accent);font-weight:600;">Active</span>
                        </div>
                        <div class="mode-switch-grid">
                            <button type="button" class="mode-btn{% if connection_mode == 'wifi' %} active{% endif %}" id="modeBtnWifi" onclick="switchConnectionMode('wifi')">
                                <span class="mode-btn-title">1. Same Wi-Fi</span>
                                <span class="mode-btn-sub" id="modeSubWifi">Local Router</span>
                            </button>
                            <button type="button" class="mode-btn{% if connection_mode == 'hotspot' %} active{% endif %}" id="modeBtnHotspot" onclick="switchConnectionMode('hotspot')">
                                <span class="mode-btn-title">2. Laptop Hotspot</span>
                                <span class="mode-btn-sub" id="modeSubHotspot">Windows Hotspot</span>
                            </button>
                            <button type="button" class="mode-btn{% if connection_mode == 'phone' %} active{% endif %}" id="modeBtnPhone" onclick="switchConnectionMode('phone')">
                                <span class="mode-btn-title">3. Phone Hotspot</span>
                                <span class="mode-btn-sub" id="modeSubPhone">Phone AP</span>
                            </button>
                            <button type="button" class="mode-btn{% if connection_mode == 'internet' %} active{% endif %}" id="modeBtnInternet" onclick="switchConnectionMode('internet')">
                                <span class="mode-btn-title">4. Internet (4G/5G)</span>
                                <span class="mode-btn-sub" id="modeSubInternet">Public HTTPS</span>
                            </button>
                        </div>
                    </div>
                    <div id="shareOutput" class="toast-box"></div>
                </div>
            </div>
            <div class="card-foot">
                <button type="button" class="btn btn-outline" onclick="refreshState(false, true)">New Code</button>
                <button type="button" class="btn btn-primary" onclick="createDirectLink()">Copy Direct Link</button>
            </div>
        </div>
    </div>

    <div class="footer-strip animate-in delay-3">
        <div>Folder: <strong id="savePathText" style="color:var(--text-primary);">{{ storage.upload_dir }}</strong></div>
        <a href="/" target="_blank" style="color:var(--accent);font-weight:500;text-decoration:none;">Open Web Uploader</a>
    </div>
</div>

<script>
""" + THEME_SCRIPT + """
let lastQrId = "{{ qr_id }}";
let lastTargetUrl = "{{ target_url }}";
let currentMode = "{{ connection_mode }}";
let isSwitchingMode = false;

function formatMMSS(totalSec) {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

async function switchConnectionMode(mode) {
    if (isSwitchingMode) return;
    isSwitchingMode = true;

    const badge = document.getElementById('modeStatusBadge');
    if (badge) {
        badge.textContent = (mode === 'internet') ? 'Starting Tunnel...' : 'Switching...';
    }

    try {
        const r = await fetch('/api/set-connection-mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        const d = await r.json();
        if (r.ok && d.ok) {
            currentMode = d.mode;
            await refreshState(true, false);
            if (badge) badge.textContent = (d.mode === 'internet') ? 'Tunnel Active' : 'Active';
        } else {
            const out = document.getElementById('shareOutput');
            if (out) {
                out.style.display = 'block';
                out.textContent = d.error || 'Failed to switch connection mode.';
            }
            if (badge) badge.textContent = 'Error';
        }
    } catch (e) {
        const out = document.getElementById('shareOutput');
        if (out) {
            out.style.display = 'block';
            out.textContent = 'Connection error when switching mode.';
        }
        if (badge) badge.textContent = 'Error';
    } finally {
        isSwitchingMode = false;
    }
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

        if (d.qr_id !== lastQrId || d.target_url !== lastTargetUrl || forceQr) {
            document.getElementById('qrContainer').innerHTML = d.qr_svg;
            lastQrId = d.qr_id;
            lastTargetUrl = d.target_url;
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
                            <span style="font-weight:600;font-size:0.88rem;">${u.display}</span>
                            ${active ? '<span class="active-badge">Active</span>' : ''}
                        </div>
                        <div style="font-size:0.76rem;color:var(--text-muted);margin-top:3px;">
                            ${u.free_space} free of ${u.total_space}
                        </div>
                    `;
                    btn.onclick = () => selectUsbDrive(u.drive);
                    grid.appendChild(btn);
                });
            }
        } else {
            pill.className = 'status-pill warn';
            pillText.textContent = 'No USB Connected';
            if (selPanel) selPanel.style.display = 'block';
            if (selTitle) selTitle.textContent = 'Target USB Drive';
            if (selSub) selSub.textContent = '';
            if (grid) {
                grid.innerHTML = `
                    <div style="grid-column:1/-1;padding:12px 14px;background:var(--danger-bg);border:1px solid var(--danger-border);border-radius:var(--btn-radius);color:var(--danger-text);font-size:0.82rem;">
                        No USB drive connected. Please plug in a USB flash drive.
                    </div>
                `;
            }
        }

        const activeMode = d.connection_mode || currentMode || 'wifi';
        currentMode = activeMode;

        const modeBtns = {
            'wifi': document.getElementById('modeBtnWifi'),
            'hotspot': document.getElementById('modeBtnHotspot'),
            'phone': document.getElementById('modeBtnPhone'),
            'internet': document.getElementById('modeBtnInternet')
        };

        for (const [key, btn] of Object.entries(modeBtns)) {
            if (btn) {
                if (key === activeMode) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        }

        if (d.network_modes) {
            const subWifi = document.getElementById('modeSubWifi');
            const subHotspot = document.getElementById('modeSubHotspot');
            const subPhone = document.getElementById('modeSubPhone');
            if (subWifi) subWifi.textContent = d.network_modes.wifi ? d.network_modes.wifi : 'Local Router';
            if (subHotspot) subHotspot.textContent = d.network_modes.hotspot ? d.network_modes.hotspot : '192.168.137.1';
            if (subPhone) subPhone.textContent = d.network_modes.phone ? d.network_modes.phone : 'Phone AP';
        }

        const subInternet = document.getElementById('modeSubInternet');
        const badge = document.getElementById('modeStatusBadge');
        if (d.tunnel_info && d.tunnel_info.active) {
            if (subInternet) subInternet.textContent = 'Active (HTTPS)';
            if (activeMode === 'internet' && badge && !isSwitchingMode) badge.textContent = 'Tunnel Active';
        } else if (activeMode === 'internet') {
            if (subInternet) subInternet.textContent = 'Connecting...';
            if (badge && !isSwitchingMode) badge.textContent = 'Connecting...';
        } else {
            if (subInternet) subInternet.textContent = 'Public HTTPS';
            if (badge && !isSwitchingMode) badge.textContent = 'Active';
        }

        if (activeMode === 'internet' && (!d.tunnel_info || !d.tunnel_info.active)) {
            setTimeout(() => refreshState(true, false), 1500);
        }
    } catch (e) {}
}

let updateDownloadUrl = "";

function dismissUpdateBanner() {
    const banner = document.getElementById('updateBanner');
    if (banner) banner.style.display = 'none';
}

async function checkForUpdates(manual = false) {
    const btnText = document.getElementById('updateBtnText');
    const icon = document.getElementById('updateIcon');
    if (manual && btnText) {
        btnText.textContent = 'Checking...';
        if (icon) icon.style.animation = 'spin 0.8s linear infinite';
    }
    try {
        const r = await fetch('/api/check-update');
        const d = await r.json();
        if (icon) icon.style.animation = 'none';
        if (r.ok && d.ok) {
            const banner = document.getElementById('updateBanner');
            const badge = document.getElementById('updateBadge');
            const msg = document.getElementById('updateBannerMsg');
            const notes = document.getElementById('updateReleaseNotes');
            const startBtn = document.getElementById('startUpdateBtn');

            if (d.has_update) {
                updateDownloadUrl = d.download_url;
                if (badge) {
                    badge.textContent = 'NEW';
                    badge.style.background = 'var(--accent)';
                }
                if (msg) msg.innerHTML = `<strong>Update Available:</strong> ${d.latest_version} (${d.asset_size_str})`;
                if (notes && d.release_notes) notes.textContent = d.release_notes;
                if (startBtn) startBtn.style.display = 'inline-flex';
                if (banner) banner.style.display = 'flex';
                if (btnText) btnText.textContent = 'Update Available';
            } else if (manual) {
                if (badge) {
                    badge.textContent = 'LATEST';
                    badge.style.background = 'var(--success-text)';
                }
                if (msg) msg.innerHTML = `<strong>Up to Date:</strong> You are running the latest version (v${d.current_version}).`;
                if (notes) notes.textContent = '';
                if (startBtn) startBtn.style.display = 'none';
                if (banner) banner.style.display = 'flex';
                if (btnText) btnText.textContent = 'Up to Date';
                setTimeout(() => {
                    if (btnText) btnText.textContent = 'Check Update';
                }, 3000);
            } else {
                if (btnText) btnText.textContent = 'Check Update';
            }
        } else if (manual) {
            if (icon) icon.style.animation = 'none';
            if (btnText) btnText.textContent = 'Check Update';
            const banner = document.getElementById('updateBanner');
            const badge = document.getElementById('updateBadge');
            const msg = document.getElementById('updateBannerMsg');
            const notes = document.getElementById('updateReleaseNotes');
            const startBtn = document.getElementById('startUpdateBtn');
            if (badge) {
                badge.textContent = 'OFFLINE';
                badge.style.background = 'var(--danger-text)';
            }
            if (msg) msg.innerHTML = `Could not reach GitHub update service.`;
            if (notes) notes.textContent = 'Please check your internet connection.';
            if (startBtn) startBtn.style.display = 'none';
            if (banner) banner.style.display = 'flex';
        }
    } catch (e) {
        if (icon) icon.style.animation = 'none';
        if (btnText) btnText.textContent = 'Check Update';
        if (manual) {
            const banner = document.getElementById('updateBanner');
            const badge = document.getElementById('updateBadge');
            const msg = document.getElementById('updateBannerMsg');
            const notes = document.getElementById('updateReleaseNotes');
            const startBtn = document.getElementById('startUpdateBtn');
            if (badge) {
                badge.textContent = 'ERROR';
                badge.style.background = 'var(--danger-text)';
            }
            if (msg) msg.innerHTML = `Connection error.`;
            if (notes) notes.textContent = '';
            if (startBtn) startBtn.style.display = 'none';
            if (banner) banner.style.display = 'flex';
        }
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
    q_param = request.args.get("q", "").strip()
    if q_param:
        now = time.time()
        state = check_and_rotate_state()
        is_valid_qr = (q_param == state.get("qr_id")) or (
            q_param == state.get("previous_qr_id") and now < state.get("previous_qr_expire", 0)
        )
        if is_valid_qr:
            session["verified_code"] = state["access_code"]
            return redirect(url_for("home_page"))

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
    target_base = get_active_target_url()
    qr_url = f"{target_base}/?q={state['qr_id']}"
    st = resolve_storage()
    return render_template_string(
        LAPTOP_QR_TEMPLATE,
        qr_svg=make_svg_qr(qr_url),
        qr_id=state["qr_id"],
        access_code=state["access_code"],
        target_url=target_base,
        storage=st,
        current_version=APP_VERSION,
        connection_mode=CONNECTION_MODE,
    )


@app.route("/api/check-update", methods=["GET"])
def api_check_update():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "USB-Transfer-App",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            if resp.status == 200:
                releases = json.loads(resp.read().decode("utf-8"))
                candidates = []
                for r in releases:
                    if r.get("draft") or r.get("prerelease"):
                        continue
                    tag = r.get("tag_name", "")
                    ver = parse_version(tag)
                    exe_asset = None
                    for a in r.get("assets", []):
                        aname = a.get("name", "").lower()
                        if aname == "usb_transfer.exe":
                            exe_asset = a
                            break
                        elif aname.endswith(".exe") and not exe_asset:
                            exe_asset = a
                    if exe_asset:
                        candidates.append((ver, tag, exe_asset, r))

                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best_ver, best_tag, best_asset, best_release = candidates[0]
                    current_ver = parse_version(APP_VERSION)
                    has_update = best_ver > current_ver
                    download_url = best_asset.get("browser_download_url", "")
                    asset_size = best_asset.get("size", 0)
                    body_text = best_release.get("body", "") or ""

                    return jsonify({
                        "ok": True,
                        "current_version": APP_VERSION,
                        "latest_version": best_tag,
                        "has_update": has_update and bool(download_url),
                        "download_url": download_url,
                        "asset_size_str": format_size(asset_size),
                        "release_notes": body_text[:280] if body_text else "",
                    })
                else:
                    return jsonify({
                        "ok": True,
                        "current_version": APP_VERSION,
                        "latest_version": f"v{APP_VERSION}",
                        "has_update": False,
                        "download_url": "",
                        "asset_size_str": "0 B",
                        "release_notes": "",
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


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    def _do_exit():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_do_exit, daemon=True).start()
    return jsonify({"ok": True, "message": "Shutting down..."})


@app.route("/api/qr-state", methods=["GET"])
def api_qr_state():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    force_qr = request.args.get("force_qr") == "1"
    force_code = request.args.get("force_code") == "1"
    state = check_and_rotate_state(force_qr=force_qr, force_code=force_code)
    
    target_base = get_active_target_url()
    qr_url = f"{target_base}/?q={state['qr_id']}"
    st = resolve_storage()
    modes = classify_network_modes()
    t_info = tunnel_mgr.get_info()

    return jsonify({
        "ok": True,
        "qr_id": state["qr_id"],
        "qr_svg": make_svg_qr(qr_url),
        "access_code": state["access_code"],
        "remaining": state["remaining"],
        "interval_sec": state["interval_sec"],
        "target_url": target_base,
        "connection_mode": CONNECTION_MODE,
        "network_modes": modes,
        "tunnel_info": t_info,
        "storage": st,
    })


@app.route("/api/set-connection-mode", methods=["POST"])
def api_set_connection_mode():
    if not is_local_request():
        return jsonify({"ok": False}), 403
    global CONNECTION_MODE, _CACHED_QR_KEY, _CACHED_QR_SVG
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "wifi").strip().lower()
    if mode not in ("wifi", "hotspot", "phone", "internet"):
        return jsonify({"ok": False, "error": "Invalid connection mode."}), 400

    if mode == "internet":
        url = tunnel_mgr.start()
        if not url:
            return jsonify({
                "ok": False,
                "error": tunnel_mgr.error or "Could not establish secure internet tunnel. Please verify internet connection."
            }), 500
    else:
        tunnel_mgr.stop()

    with STATE_LOCK:
        CONNECTION_MODE = mode
        _CACHED_QR_KEY = None
        _CACHED_QR_SVG = None

    return jsonify({
        "ok": True,
        "mode": CONNECTION_MODE,
        "target_url": get_active_target_url(),
        "tunnel_info": tunnel_mgr.get_info(),
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
    target_base = get_active_target_url()
    if file_target:
        share_url = f"{target_base}/?link={token}&file={file_target}"
    else:
        share_url = f"{target_base}/?link={token}"
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


@app.route("/view/<path:filename>", methods=["GET"])
@require_auth
def view_route(filename):
    st = resolve_storage()
    clean = os.path.basename(filename)
    target = os.path.join(st["upload_dir"], clean)
    if not os.path.isfile(target) or clean.endswith(".part"):
        return "<h3 style='color:#dc2626;text-align:center;font-family:sans-serif;'>File not found on USB drive.</h3>", 404
    try:
        return send_from_directory(st["upload_dir"], clean, as_attachment=False)
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
    import multiprocessing
    multiprocessing.freeze_support()
    try:
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
    except Exception as exc:
        try:
            log_p = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "crash.log")
            with open(log_p, "w", encoding="utf-8") as f:
                import traceback
                traceback.print_exc(file=f)
        except Exception:
            pass
