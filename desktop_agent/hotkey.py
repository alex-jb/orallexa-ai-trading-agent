"""
desktop_agent/hotkey.py
──────────────────────────────────────────────────────────────────
Global hotkey listener for the desktop assistant.

Hotkeys:
    Ctrl+Shift+S  ->  screenshot + chart analysis
    K             ->  toggle voice input (push-to-talk)

Uses the `keyboard` library for system-wide hotkey capture.
Runs in a background daemon thread.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

_HOTKEY_SCREENSHOT = "ctrl+shift+s"
_HOTKEY_VOICE      = "k"


class HotkeyListener:
    """
    Registers global hotkeys and calls callbacks when triggered.

    Usage:
        listener = HotkeyListener(
            on_screenshot=my_screenshot_cb,
            on_voice_toggle=my_voice_cb,
        )
        listener.start()
        ...
        listener.stop()
    """

    def __init__(
        self,
        on_screenshot: Optional[Callable] = None,
        on_voice_toggle: Optional[Callable] = None,
    ) -> None:
        self._on_screenshot = on_screenshot
        self._on_voice_toggle = on_voice_toggle
        self._running = False
        self._hook_ids: list = []

    def start(self) -> None:
        """Register global hotkeys in a background thread."""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._register, daemon=True).start()

    def stop(self) -> None:
        """Unregister all hotkeys."""
        self._running = False
        try:
            import keyboard
            for hid in self._hook_ids:
                try:
                    keyboard.remove_hotkey(hid)
                except Exception:
                    pass
            self._hook_ids.clear()
        except Exception as exc:
            try:
                from core.logger import get_logger
                get_logger("hotkey").warning("Failed to unregister hotkeys: %s", exc)
            except Exception:
                pass

    def _register(self) -> None:
        try:
            import keyboard

            if self._on_screenshot:
                hid = keyboard.add_hotkey(
                    _HOTKEY_SCREENSHOT,
                    self._on_screenshot_trigger,
                    suppress=False,
                )
                self._hook_ids.append(hid)

            if self._on_voice_toggle:
                hid = keyboard.add_hotkey(
                    _HOTKEY_VOICE,
                    self._on_voice_trigger,
                    suppress=False,   # don't suppress — let K type normally
                )
                self._hook_ids.append(hid)

            from core.logger import get_logger
            get_logger("hotkey").info(
                "Registered hotkeys: %s (screenshot), %s (voice toggle)",
                _HOTKEY_SCREENSHOT, _HOTKEY_VOICE,
            )
        except ImportError:
            from core.logger import get_logger
            get_logger("hotkey").warning("`keyboard` package not installed — hotkeys disabled")
        except Exception as e:
            from core.logger import get_logger
            get_logger("hotkey").error("Failed to register hotkeys: %s", e)

    def _on_screenshot_trigger(self) -> None:
        if self._on_screenshot:
            threading.Thread(target=self._on_screenshot, daemon=True).start()

    def _on_voice_trigger(self) -> None:
        if self._on_voice_toggle:
            threading.Thread(target=self._on_voice_toggle, daemon=True).start()
