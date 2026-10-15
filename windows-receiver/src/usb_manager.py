"""
USB Volume Detector and Hardware State Manager for PhoneToUSB.
Dynamically resolves the active USB storage device, validates write access,
and prevents writes if the drive is unmounted.
"""

import os
import sys
import shutil
import ctypes
import platform
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

class USBStatus:
    READY = "READY"
    NOT_FOUND = "NOT_FOUND"
    READ_ONLY = "READ_ONLY"
    UNMOUNTED = "UNMOUNTED"
    INTERNAL_DRIVE = "INTERNAL_DRIVE"

class USBManager:
    def __init__(self, override_path: Optional[Path] = None):
        self.override_path = override_path
        self._current_usb_root: Optional[Path] = None
        self._volume_label: str = "USB Drive"
        self._drive_letter: str = ""
        self._is_ready: bool = False
        self._last_error: str = ""

    def detect_usb_root(self) -> Tuple[Optional[Path], str]:
        """
        Determines the USB root directory based on the running application location.
        Never hardcodes drive letters.
        """
        if self.override_path:
            target = Path(self.override_path).resolve()
        else:
            if getattr(sys, "frozen", False):
                # Running as compiled PyInstaller executable
                target = Path(sys.executable).resolve()
            else:
                # Running as Python script
                target = Path(__file__).resolve().parent.parent

        drive, _ = os.path.splitdrive(str(target))
        if not drive:
            self._is_ready = False
            self._last_error = "Could not identify volume drive letter"
            return None, USBStatus.NOT_FOUND

        root_path = Path(f"{drive}\\") if platform.system() == "Windows" else target

        # Check existence and writeability
        status = self.verify_volume(root_path)
        if status == USBStatus.READY:
            self._current_usb_root = root_path
            self._drive_letter = drive
            self._volume_label = self._get_volume_label(root_path)
            self._is_ready = True
            self._last_error = ""
            return root_path, USBStatus.READY
        else:
            self._current_usb_root = None
            self._is_ready = False
            return None, status

    def verify_volume(self, path: Optional[Path] = None) -> str:
        """
        Validates that the volume exists, is mounted, and is writable.
        """
        target = path or self._current_usb_root
        if not target or not target.exists():
            self._is_ready = False
            self._last_error = "Target volume does not exist or was ejected"
            return USBStatus.UNMOUNTED

        # Test writeability using a canary file inside .phonetoUSB/temp
        try:
            temp_dir = target / ".phonetoUSB" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            canary_file = temp_dir / ".canary_write_test"
            with open(canary_file, "w") as f:
                f.write("OK")
            canary_file.unlink(missing_ok=True)
            self._is_ready = True
            return USBStatus.READY
        except PermissionError:
            self._is_ready = False
            self._last_error = "Volume is Read-Only or write access is denied"
            return USBStatus.READ_ONLY
        except OSError as e:
            self._is_ready = False
            self._last_error = f"Volume access failed: {e}"
            return USBStatus.UNMOUNTED

    def get_storage_stats(self) -> Dict[str, Any]:
        """Returns total, free, and used space on the USB volume."""
        if not self._current_usb_root or not self._is_ready:
            return {
                "is_ready": False,
                "drive_letter": self._drive_letter,
                "volume_label": self._volume_label,
                "total_bytes": 0,
                "free_bytes": 0,
                "used_bytes": 0,
                "error": self._last_error
            }

        try:
            usage = shutil.disk_usage(str(self._current_usb_root))
            return {
                "is_ready": True,
                "drive_letter": self._drive_letter,
                "volume_label": self._volume_label,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_bytes": usage.used,
                "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0,
                "error": ""
            }
        except Exception as e:
            self._is_ready = False
            self._last_error = str(e)
            return {
                "is_ready": False,
                "drive_letter": self._drive_letter,
                "volume_label": self._volume_label,
                "total_bytes": 0,
                "free_bytes": 0,
                "used_bytes": 0,
                "error": str(e)
            }

    def _get_volume_label(self, path: Path) -> str:
        """Retrieves volume label on Windows via Win32 API, or defaults gracefully."""
        if platform.system() != "Windows":
            return "Test USB Drive"

        try:
            kernel32 = ctypes.windll.kernel32
            volume_name_buffer = ctypes.create_unicode_buffer(1024)
            fs_name_buffer = ctypes.create_unicode_buffer(1024)
            serial_number = ctypes.c_ulong()
            max_component_length = ctypes.c_ulong()
            file_system_flags = ctypes.c_ulong()

            res = kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(str(path)),
                volume_name_buffer,
                ctypes.sizeof(volume_name_buffer),
                ctypes.byref(serial_number),
                ctypes.byref(max_component_length),
                ctypes.byref(file_system_flags),
                fs_name_buffer,
                ctypes.sizeof(fs_name_buffer)
            )
            if res:
                label = volume_name_buffer.value
                return label if label else "USB Drive"
        except Exception:
            pass
        return "USB Drive"

    @property
    def usb_root(self) -> Optional[Path]:
        return self._current_usb_root

    @property
    def is_ready(self) -> bool:
        return self._is_ready
