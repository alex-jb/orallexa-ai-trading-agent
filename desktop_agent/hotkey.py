"""
desktop_agent/hotkey.py
──────────────────────────────────────────────────────────────────
Global hotkey listener for the desktop assistant.

Hotkeys:
    Ctrl+Shift+S  ->  screenshot + chart analysis
    Hold Ctrl+K   ->  hold to record voice, release to stop & transcribe

Uses the `keyboard` library for system-wide hotkey capture.
Runs in a background daemon thread.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

_HOTKEY_SCREENSHOT = "ctrl+shift+s"


class HotkeyListener:
    """
    Registers global hotkeys and calls callbacks when triggered.

    Voice: Hold Ctrl+K to record, release K to stop and transcribe.
    """

    def __init__(
        self,
        on_screenshot: Optional[Callable] = None,
        on_voice_start: Optional[Callable] = None,
        on_voice_stop: Optional[Callable] = None,
    ) -> None:
        self._on_screenshot = on_screenshot
        self._on_voice_start = on_voice_start
        self._on_voice_stop = on_voice_stop
        self._running = False
        self._hook_ids: list = []
        self._recording = False
        self._key_hooks: list = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._register, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        try:
            import keyboard
            for hid in self._hook_ids:
                try:
                    keyboard.remove_hotkey(hid)
                except Exception:
                    pass
            self._hook_ids.clear()
            for hook in self._key_hooks:
                try:
                    keyboard.unhook(hook)
                except Exception:
                    pass
            self._key_hooks.clear()
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

            if self._on_voice_start and self._on_voice_stop:
                h1 = keyboard.on_press_key("k", self._on_voice_key_down, suppress=False)
                h2 = keyboard.on_release_key("k", self._on_voice_key_up, suppress=False)
                self._key_hooks.extend([h1, h2])

            from core.logger import get_logger
            get_logger("hotkey").info(
                "Registered: %s (screenshot), Ctrl+K hold (voice)",
                _HOTKEY_SCREENSHOT,
            )
        except ImportError:
            from core.logger import get_logger
            get_logger("hotkey").warning("`keyboard` package not installed")
        except Exception as e:
            from core.logger import get_logger
            get_logger("hotkey").error("Failed to register hotkeys: %s", e)

    def _on_screenshot_trigger(self) -> None:
        if self._on_screenshot:
            threading.Thread(target=self._on_screenshot, daemon=True).start()

    def _on_voice_key_down(self, _event) -> None:
        """Called when K is pressed — start recording only if Ctrl is held."""
        try:
            import keyboard as kb
            if not kb.is_pressed("ctrl"):
                return
        except Exception:
            return
        if self._recording:
            return
        self._recording = True
        if self._on_voice_start:
            self._on_voice_start()

    def _on_voice_key_up(self, _event) -> None:
        """Called when K is released — stop recording and transcribe."""
        if not self._recording:
            return
        self._recording = False
        if self._on_voice_stop:
            threading.Thread(target=self._on_voice_stop, daemon=True).start()
