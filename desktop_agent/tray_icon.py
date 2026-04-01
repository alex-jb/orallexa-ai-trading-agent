"""
desktop_agent/tray_icon.py
──────────────────────────────────────────────────────────────────
System tray icon (Windows/macOS) via pystray.
Right-click menu: screenshot, ticker switch, mode switch, show/hide, quit.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from core.logger import get_logger
from desktop_agent.i18n import t, get_lang

logger = get_logger("tray_icon")

try:
    import pystray
    from pystray import MenuItem, Menu
    from PIL import Image
    _PYSTRAY_OK = True
except ImportError:
    _PYSTRAY_OK = False


ICON_PATH = Path(__file__).parent.parent / "assets" / "avatar" / "bull_idle.png"

_QUICK_TICKERS = ["NVDA", "TSLA", "AAPL", "SPY", "QQQ", "AMZN", "MSFT", "META"]


def _load_icon() -> "Image.Image":
    from PIL import Image
    if ICON_PATH.exists():
        img = Image.open(ICON_PATH).convert("RGBA")
        return img.resize((32, 32))
    img = Image.new("RGBA", (32, 32), (198, 30, 40, 255))
    return img


class TrayIcon:
    """
    System tray icon with menu.

    Callbacks (all optional):
        on_quit()
        on_show()
        on_hide()
        on_ticker_change(ticker: str)
        on_mode_change(mode: str, tf: str)
        on_screenshot()
    """

    def __init__(
        self,
        on_quit:          Optional[Callable]           = None,
        on_show:          Optional[Callable]           = None,
        on_hide:          Optional[Callable]           = None,
        on_ticker_change: Optional[Callable[[str], None]]      = None,
        on_mode_change:   Optional[Callable[[str, str], None]] = None,
        on_screenshot:    Optional[Callable]           = None,
    ) -> None:
        self._on_quit          = on_quit
        self._on_show          = on_show
        self._on_hide          = on_hide
        self._on_ticker_change = on_ticker_change
        self._on_mode_change   = on_mode_change
        self._on_screenshot    = on_screenshot
        self._icon: Optional["pystray.Icon"] = None
        self._visible = True

    def start(self) -> None:
        if not _PYSTRAY_OK:
            logger.warning("pystray not installed — tray icon disabled")
            return
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def set_tooltip(self, text: str) -> None:
        if self._icon:
            self._icon.title = text

    def update_state(self, ticker: str = "", mode: str = "",
                     timeframe: str = "", decision: str = "") -> None:
        """Update tray tooltip to reflect current analysis state."""
        parts = ["Bull Coach"]
        if ticker:
            parts.append(f"{ticker}")
        if mode:
            parts.append(f"{mode.title()} ({timeframe})" if timeframe else mode.title())
        if decision:
            parts.append(f"→ {decision}")
        self.set_tooltip(" · ".join(parts))

    def _run(self) -> None:
        icon_img = _load_icon()

        def _toggle_visibility(icon, item):
            self._visible = not self._visible
            if self._visible and self._on_show:
                self._on_show()
            elif not self._visible and self._on_hide:
                self._on_hide()

        def _set_mode(mode: str, tf: str):
            def _fn(icon, item):
                if self._on_mode_change:
                    self._on_mode_change(mode, tf)
            return _fn

        def _set_ticker(ticker: str):
            def _fn(icon, item):
                if self._on_ticker_change:
                    self._on_ticker_change(ticker)
                    logger.info("Ticker changed to %s via tray", ticker)
            return _fn

        def _screenshot(icon, item):
            if self._on_screenshot:
                self._on_screenshot()

        def _quit(icon, item):
            icon.stop()
            if self._on_quit:
                self._on_quit()

        ticker_submenu = Menu(
            *[MenuItem(tk, _set_ticker(tk)) for tk in _QUICK_TICKERS]
        )

        menu = Menu(
            MenuItem(t("bull_coach"), None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(t("tray_screenshot"), _screenshot),
            Menu.SEPARATOR,
            MenuItem(t("tray_ticker"), ticker_submenu),
            Menu.SEPARATOR,
            MenuItem(t("tray_show_hide"), _toggle_visibility),
            Menu.SEPARATOR,
            MenuItem(t("tray_scalp"),         _set_mode("scalp",    "5m")),
            MenuItem(t("tray_intraday_15m"),  _set_mode("intraday", "15m")),
            MenuItem(t("tray_intraday_1h"),   _set_mode("intraday", "1h")),
            MenuItem(t("tray_swing"),         _set_mode("swing",    "1D")),
            Menu.SEPARATOR,
            MenuItem(t("tray_quit"), _quit),
        )

        self._icon = pystray.Icon(
            name="BullCoach",
            icon=icon_img,
            title=t("bull_coach"),
            menu=menu,
        )
        self._icon.run()
