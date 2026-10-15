"""
Logging service for PhoneToUSB Windows Receiver.
Ensures zero-secrets logging and logs to both console and .phonetoUSB/logs/receiver.log.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

LOGGER_NAME = "PhoneToUSB"

def setup_logger(usb_root: Optional[Path] = None, debug: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(console_handler)

    # File Handler (if usb_root provided)
    if usb_root:
        try:
            log_dir = usb_root / ".phonetoUSB" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "receiver.log"

            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Failed to initialize file logger on USB: {e}")

    return logger

def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
