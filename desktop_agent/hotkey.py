"""
desktop_agent/hotkey.py
──────────────────────────────────────────────────────────────────
Global hotkey listener for the desktop assistant.

Default: Ctrl+Shift+S  ->  screenshot + chart analysis

Uses the `keyboard` library for system-wide hotkey capture.
Runs in a background daemon thread.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

_HOTKEY = "ctrl+shift+s"


class HotkeyListener:
    """
    Registers a global hotkey and calls the callback when triggered.

    Usage:
        listener = HotkeyListener(on_screenshot=my_callback)
        listener.start()   # non-blocking, runs in background
        ...
        listener.stop()
    """

    def __init__(self, on_screenshot: Optional[Callable] = None) -> None:
        self._on_screenshot = on_screenshot
        self._running = False
        self._hook_id = None

    def start(self) -> None:
        """Register global hotkey in a background thread."""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._register, daemon=True).start()

    def stop(self) -> None:
        """Unregister the hotkey."""
        self._running = False
        try:
            import keyboard
            if self._hook_id is not None:
                keyboard.remove_hotkey(self._hook_id)
                self._hook_id = None
        except Exception as exc:
            try:
                from core.logger import get_logger
                get_logger("hotkey").warning("Failed to unregister hotkey: %s", exc)
            except Exception:
                pass

    def _register(self) -> None:
        try:
            import keyboard
            self._hook_id = keyboard.add_hotkey(
                _HOTKEY,
                self._on_trigger,
                suppress=False,
            )
            from core.logger import get_logger
            get_logger("hotkey").info("Registered %s for screenshot analysis", _HOTKEY)
        except ImportError:
            from core.logger import get_logger
            get_logger("hotkey").warning("`keyboard` package not installed — hotkey disabled")
        except Exception as e:
            from core.logger import get_logger
            get_logger("hotkey").error("Failed to register hotkey: %s", e)

    def _on_trigger(self) -> None:
        if self._on_screenshot:
            # Run callback in a new thread so it doesn't block the hook
            threading.Thread(target=self._on_screenshot, daemon=True).start()
