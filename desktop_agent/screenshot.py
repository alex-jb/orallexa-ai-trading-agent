"""
desktop_agent/screenshot.py
──────────────────────────────────────────────────────────────────
One-shot screenshot capture for chart analysis.

Provides:
  - Full-screen capture
  - Clipboard image grab
"""
from __future__ import annotations

import io
from typing import Optional

from core.logger import get_logger

logger = get_logger("screenshot")


def capture_screen() -> Optional[bytes]:
    """
    Capture the full screen and return PNG bytes.
    Returns None if capture fails (e.g. no display).
    """
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        # Resize if too large (multi-monitor can produce huge images)
        max_w = 2560
        if img.width > max_w:
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning("Screen capture failed: %s", e)
        return None


def grab_clipboard() -> Optional[bytes]:
    """
    Grab an image from the clipboard and return PNG bytes.
    Returns None if clipboard has no image.
    """
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is None:
            return None
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning("Clipboard grab failed: %s", e)
        return None
