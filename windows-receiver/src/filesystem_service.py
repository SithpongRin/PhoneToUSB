"""
Filesystem Service for PhoneToUSB Windows Receiver.
Enforces strict sandboxing to the USB user root, protects against directory traversal,
filters out private internal files, and provides live directory operations.
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

HIDDEN_SYSTEM_PATHS = {
    ".phonetoUSB",
    "PhoneToUSB.exe",
    "System Volume Information",
    "$RECYCLE.BIN",
    "autorun.inf"
}

class SecurityViolation(Exception):
    pass

class FilesystemService:
    def __init__(self, usb_root: Path, user_data_subfolder: Optional[str] = None):
        self.usb_root = Path(usb_root).resolve()
        if user_data_subfolder:
            self.user_root = (self.usb_root / user_data_subfolder).resolve()
            self.user_root.mkdir(parents=True, exist_ok=True)
        else:
            self.user_root = self.usb_root

    def sanitize_and_resolve(self, relative_path: str) -> Path:
        """
        Validates that the relative path does not escape the USB user root
        and contains no reserved device names or invalid path sequences.
        """
        if not relative_path or relative_path.strip() in ("", ".", "/"):
            return self.user_root

        # Normalize slashes and clean leading/trailing slashes
        clean = relative_path.replace("\\", "/").strip("/")

        # Check for traversal indicators
        parts = clean.split("/")
        for part in parts:
            if part in ("..", ""):
                raise SecurityViolation("Path traversal attempt detected")
            stem = part.split(".")[0].upper()
            if stem in RESERVED_NAMES:
                raise SecurityViolation(f"Use of reserved device name '{part}' is forbidden")

        resolved = (self.user_root / clean).resolve()

        # Strict containment check
        try:
            if not resolved.is_relative_to(self.user_root):
                raise SecurityViolation("Target path escapes authorized USB directory")
        except AttributeError:
            # Fallback for older python Path compatibility if needed
            if not str(resolved).startswith(str(self.user_root)):
                raise SecurityViolation("Target path escapes authorized USB directory")

        # Disallow access to hidden reserved internal directories
        rel_to_usb = resolved.relative_to(self.usb_root)
        top_component = rel_to_usb.parts[0] if rel_to_usb.parts else ""
        if top_component in HIDDEN_SYSTEM_PATHS:
            raise SecurityViolation("Access to reserved PhoneToUSB internal files is denied")

        return resolved

    def list_directory(
        self,
        relative_path: str = "",
        sort_by: str = "name",
        sort_asc: bool = True,
        search_query: str = "",
        page: int = 1,
        page_size: int = 200
    ) -> Dict[str, Any]:
        """
        Retrieves real-time file and folder listings from the USB filesystem.
        """
        target_dir = self.sanitize_and_resolve(relative_path)
        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {relative_path}")
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target is not a directory: {relative_path}")

        items = []
        with os.scandir(target_dir) as it:
            for entry in it:
                # Filter out system and application internal paths
                if entry.name in HIDDEN_SYSTEM_PATHS:
                    continue

                if search_query and search_query.lower() not in entry.name.lower():
                    continue

                try:
                    stat_info = entry.stat()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    rel_path = str(Path(entry.path).relative_to(self.user_root)).replace("\\", "/")

                    items.append({
                        "name": entry.name,
                        "relative_path": rel_path,
                        "is_dir": is_dir,
                        "size": stat_info.st_size if not is_dir else 0,
                        "modified_timestamp": int(stat_info.st_mtime),
                        "extension": Path(entry.name).suffix.lower().lstrip(".") if not is_dir else ""
                    })
                except (PermissionError, OSError):
                    # Skip items that cannot be read
                    continue

        # Sort: directories first, then files, sorted by specified attribute
        def sort_key(item):
            val = item.get(sort_by, item["name"])
            if isinstance(val, str):
                val = val.lower()
            return (0 if item["is_dir"] else 1, val)

        items.sort(key=sort_key, reverse=not sort_asc)

        # Pagination
        total_items = len(items)
        start_idx = (page - 1) * page_size
        paginated_items = items[start_idx : start_idx + page_size]

        rel_current = str(target_dir.relative_to(self.user_root)).replace("\\", "/")
        if rel_current == ".":
            rel_current = ""

        return {
            "current_path": rel_current,
            "parent_path": str(target_dir.parent.relative_to(self.user_root)).replace("\\", "/") if target_dir != self.user_root else None,
            "total_items": total_items,
            "page": page,
            "page_size": page_size,
            "items": paginated_items
        }

    def create_directory(self, relative_path: str) -> Dict[str, Any]:
        """Creates a new directory inside the USB user root."""
        target = self.sanitize_and_resolve(relative_path)
        if target.exists():
            raise FileExistsError(f"Directory already exists: {relative_path}")
        target.mkdir(parents=True, exist_ok=False)
        return {
            "success": True,
            "relative_path": str(target.relative_to(self.user_root)).replace("\\", "/")
        }

    def rename_item(self, old_relative_path: str, new_name: str) -> Dict[str, Any]:
        """Renames a file or directory within its parent directory."""
        source = self.sanitize_and_resolve(old_relative_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {old_relative_path}")
        if source == self.user_root:
            raise SecurityViolation("Cannot rename user root")

        # Destination is in the same parent directory
        parent = source.parent
        # Clean new name to prevent path separator injections
        clean_name = Path(new_name).name
        if clean_name in HIDDEN_SYSTEM_PATHS or clean_name.split(".")[0].upper() in RESERVED_NAMES:
            raise SecurityViolation("Invalid target file name")

        destination = parent / clean_name
        if destination.exists():
            raise FileExistsError(f"Target '{clean_name}' already exists")

        source.rename(destination)
        return {
            "success": True,
            "old_path": old_relative_path,
            "new_path": str(destination.relative_to(self.user_root)).replace("\\", "/")
        }

    def move_item(self, source_relative_path: str, target_dir_relative_path: str) -> Dict[str, Any]:
        """Moves a file or directory to a different folder inside the user root."""
        source = self.sanitize_and_resolve(source_relative_path)
        target_dir = self.sanitize_and_resolve(target_dir_relative_path)

        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source_relative_path}")
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target folder not found: {target_dir_relative_path}")
        if source == self.user_root:
            raise SecurityViolation("Cannot move user root")

        dest = target_dir / source.name
        if dest.exists():
            raise FileExistsError(f"Target already contains an item named '{source.name}'")

        shutil.move(str(source), str(dest))
        return {
            "success": True,
            "new_path": str(dest.relative_to(self.user_root)).replace("\\", "/")
        }

    def delete_item(self, relative_path: str, recursive: bool = False) -> Dict[str, Any]:
        """Safely deletes a file or directory with safeguards against root deletion."""
        target = self.sanitize_and_resolve(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"File or directory not found: {relative_path}")
        if target == self.user_root:
            raise SecurityViolation("Deleting the USB root is prohibited")

        if target.is_dir():
            if recursive:
                shutil.rmtree(str(target))
            else:
                target.rmdir()
        else:
            target.unlink()

        return {
            "success": True,
            "deleted_path": relative_path
        }
