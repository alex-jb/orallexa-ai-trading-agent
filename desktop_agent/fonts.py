"""
desktop_agent/fonts.py
──────────────────────────────────────────────────────────────────
Font loading for the desktop agent.

Loads Art Deco font stack from assets/fonts/ to match DESIGN.md:
  Display:  Josefin Sans (headings, labels, uppercase micro-text)
  Body:     Lato (body text, descriptions, chat)
  Data:     DM Mono (prices, percentages, metrics)

Falls back to system fonts if TTFs are missing.
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from core.logger import get_logger

logger = get_logger("fonts")

FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# Font family names after registration
FONT_HEADING = "Josefin Sans"
FONT_BODY = "Lato"
FONT_MONO = "DM Mono"

# Fallbacks
_FALLBACK_HEADING = "Segoe UI"
_FALLBACK_BODY = "Segoe UI"
_FALLBACK_MONO = "Consolas"

_loaded = False


def load_fonts() -> None:
    """Register custom TTF fonts with the OS so Tkinter can use them."""
    global _loaded, FONT_HEADING, FONT_BODY, FONT_MONO
    if _loaded:
        return

    if sys.platform != "win32":
        logger.info("Custom font loading only supported on Windows, using fallbacks")
        FONT_HEADING = _FALLBACK_HEADING
        FONT_BODY = _FALLBACK_BODY
        FONT_MONO = _FALLBACK_MONO
        _loaded = True
        return

    ttf_files = list(FONTS_DIR.glob("*.ttf"))
    if not ttf_files:
        logger.warning("No TTF fonts found in %s, using system fallbacks", FONTS_DIR)
        FONT_HEADING = _FALLBACK_HEADING
        FONT_BODY = _FALLBACK_BODY
        FONT_MONO = _FALLBACK_MONO
        _loaded = True
        return

    # Windows: AddFontResourceEx with FR_PRIVATE flag
    FR_PRIVATE = 0x10
    gdi32 = ctypes.windll.gdi32
    registered = 0

    for ttf in ttf_files:
        result = gdi32.AddFontResourceExW(str(ttf), FR_PRIVATE, 0)
        if result > 0:
            registered += 1
        else:
            logger.warning("Failed to register font: %s", ttf.name)

    if registered > 0:
        logger.info("Registered %d custom fonts from %s", registered, FONTS_DIR)
        # Verify which font families are available
        FONT_HEADING = "Josefin Sans"
        FONT_BODY = "Lato"
        FONT_MONO = "DM Mono"
    else:
        logger.warning("No fonts registered, using system fallbacks")
        FONT_HEADING = _FALLBACK_HEADING
        FONT_BODY = _FALLBACK_BODY
        FONT_MONO = _FALLBACK_MONO

    _loaded = True
