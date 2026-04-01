"""
desktop_agent/main.py
──────────────────────────────────────────────────────────────────
Entry point for the Bull Coach desktop assistant.

Run:
    python desktop_agent/main.py

Hotkey:
    Ctrl+Shift+S  ->  screenshot chart analysis

Environment variables required:
    OPENAI_API_KEY      -- Whisper transcription + TTS
    ANTHROPIC_API_KEY   -- Claude AI coaching

Optional:
    BULL_TICKER=NVDA    -- default ticker (default: NVDA)
    BULL_MODE=intraday  -- default mode: scalp | intraday | swing
    BULL_TF=15m         -- default timeframe
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from desktop_agent.i18n import t, get_lang, set_lang
from core.settings import Settings

from desktop_agent.brain_bridge    import BrainBridge
from desktop_agent.character_window import BullCharacter
from desktop_agent.chat_popover    import ChatPopover
from desktop_agent.tts_handler     import TTSHandler
from desktop_agent.voice_handler   import VoiceHandler
from desktop_agent.tray_icon       import TrayIcon
from desktop_agent.hotkey          import HotkeyListener

# Phase 1: Consistent timeout for auto-return to idle
AUTO_IDLE_MS = 10_000


def main() -> None:
    settings  = Settings()
    ticker    = os.environ.get("BULL_TICKER", settings.get("ticker", "NVDA")).upper()
    mode      = os.environ.get("BULL_MODE",   settings.get("mode", "intraday"))
    timeframe = os.environ.get("BULL_TF",     settings.get("timeframe", "15m"))
    set_lang(settings.get("language", "en"))

    tts   = TTSHandler()
    voice = VoiceHandler()
    brain = BrainBridge(
        default_ticker=ticker,
        default_mode=mode,
        default_tf=timeframe,
        auto_launch=True,
    )

    # ── Startup validation ─────────────────────────────────────────
    _api_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    _tts_ok = bool(os.environ.get("OPENAI_API_KEY"))
    if not _api_ok:
        from core.logger import get_logger
        get_logger("main").warning("ANTHROPIC_API_KEY not set — Claude features disabled")
    if not _tts_ok:
        from core.logger import get_logger
        get_logger("main").warning("OPENAI_API_KEY not set — voice/TTS disabled")

    # Phase 1: Analysis lock prevents concurrent hotkey spam
    _analysis_lock = threading.Lock()

    popover: ChatPopover | None = None

    def on_bull_click(x: int, y: int) -> None:
        nonlocal popover
        if popover is None:
            return
        if popover.is_visible():
            popover.hide()
        else:
            popover.show(anchor_x=x, anchor_y=y)

    bull = BullCharacter(on_click=on_bull_click)

    def on_state_change(decision: str, risk: str) -> None:
        upper = decision.upper()
        if upper == "THINKING":
            bull.set_state("thinking")
        elif upper == "LISTENING":
            bull.set_state("listening")
        elif upper == "BUY":
            bull.set_state_from_decision("BUY", risk)
        elif upper == "SELL":
            bull.set_state_from_decision("SELL", risk)
        elif upper == "WAIT":
            bull.set_state("wait")
        else:
            bull.set_state("idle")

        if upper not in ("THINKING", "LISTENING"):
            bull._win.after(AUTO_IDLE_MS, lambda: bull.set_state("idle"))

    popover = ChatPopover(brain, voice, tts)
    popover.build(bull._win, on_state_change=on_state_change)

    # ── Screenshot hotkey (Ctrl+Shift+S) ──────────────────────────

    def _on_screenshot_hotkey() -> None:
        bull._win.after(0, _run_screenshot_analysis)

    def _run_screenshot_analysis() -> None:
        # Phase 1: Prevent concurrent analysis
        if not _analysis_lock.acquire(blocking=False):
            bull.flash_state("warning", t("already_analyzing"), 2000)
            return

        # Phase 2: Instant feedback — flash listening before thinking
        bull.set_state("listening", t("capturing"))
        bull._win.after(200, lambda: bull.set_state("thinking", t("analyzing_chart")))

        def _do_analysis():
            try:
                from desktop_agent.screenshot import capture_screen
                img_bytes = capture_screen()
                if img_bytes is None:
                    bull._win.after(0, lambda: bull.flash_state(
                        "warning", t("capture_failed"), 3000))
                    return

                reply = brain.analyze_image(img_bytes, lang="en")
                result = getattr(brain, "last_chart_result", None)

                def _show():
                    if result:
                        dec = result.decision
                        rec = getattr(result, "recommendation", "")
                        short = f"{dec}"
                        if rec:
                            short += f"\n{rec[:55]}{'...' if len(rec) > 55 else ''}"
                        from desktop_agent.chat_popover import COL_BUY, COL_SELL, COL_WAIT
                        bull.set_state_from_decision(dec, result.risk_level)
                        bull._show_bubble(short,
                                         accent={"BUY": COL_BUY, "SELL": COL_SELL
                                                }.get(dec, COL_WAIT))

                        if popover and popover.is_visible():
                            popover._show_decision_card(result)
                            popover._add_message("bull", reply)
                            popover._update_header()

                        bull._win.after(AUTO_IDLE_MS, lambda: bull.set_state("idle"))
                    else:
                        bull.flash_state("warning", t("analysis_failed"), 3000)

                bull._win.after(0, _show)
            finally:
                _analysis_lock.release()

        threading.Thread(target=_do_analysis, daemon=True).start()

    # ── Voice toggle hotkey (K) ─────────────────────────────────
    _voice_active = False

    # Check voice dependencies at startup
    _voice_deps_ok = True
    _voice_dep_missing = []
    for _pkg in ["sounddevice", "openai"]:
        try:
            __import__(_pkg)
        except ImportError:
            _voice_deps_ok = False
            _voice_dep_missing.append(_pkg)

    if _voice_dep_missing:
        from core.logger import get_logger
        get_logger("main").warning(
            "Voice dependencies missing: %s — run: pip install %s",
            ", ".join(_voice_dep_missing), " ".join(_voice_dep_missing),
        )

    def _on_voice_toggle() -> None:
        """Toggle voice recording with K key. Press once to start, again to stop."""
        nonlocal _voice_active
        if popover is None:
            return

        # Don't capture K if the chat popover's text entry is focused
        try:
            focused = bull._win.focus_get()
            if focused and isinstance(focused, tk.Entry):
                return
        except Exception:
            pass

        if not _voice_deps_ok:
            bull._win.after(0, lambda: bull._show_bubble(
                f"pip install {' '.join(_voice_dep_missing)}",
                accent="#C44536"))
            bull._win.after(0, lambda: popover._add_status(
                f"[Voice disabled — missing: {', '.join(_voice_dep_missing)}]"))
            return

        if not _voice_active:
            # ── START recording ──────────────────────────────────
            _voice_active = True
            try:
                voice.start_recording()
            except Exception as exc:
                _voice_active = False
                bull._win.after(0, lambda: bull._show_bubble(
                    f"Mic error: {exc}", accent="#C44536"))
                return

            def _show_start():
                bull.set_state("listening")
                bull._show_bubble("\U0001F3A4 Voice ON  [K]", accent="#D4AF37")
                popover.show_voice_status(True)

            bull._win.after(0, _show_start)
        else:
            # ── STOP recording & transcribe ──────────────────────
            _voice_active = False

            def _show_processing():
                bull.set_state("thinking")
                bull._show_bubble("\u23F3 Transcribing...  [K]", accent="#8B7EC8")
                popover.show_voice_status(False)

            bull._win.after(0, _show_processing)

            def _finish_voice():
                try:
                    text, lang = voice.stop_and_transcribe()
                except Exception as exc:
                    bull._win.after(0, lambda: bull.set_state("idle"))
                    bull._win.after(0, lambda: bull._show_bubble(
                        f"Transcribe error", accent="#C44536"))
                    return

                if text:
                    def _send():
                        bull._show_bubble("\U0001F3A4 Voice OFF  [K]",
                                         accent="#A89F8B")
                        popover._process_input(
                            text, popover._effective_lang(lang))

                    bull._win.after(0, _send)
                else:
                    def _no_speech():
                        bull.set_state("idle")
                        bull._show_bubble("No speech detected  [K]",
                                         accent="#C44536")
                        popover._add_status("[K] No speech detected")

                    bull._win.after(0, _no_speech)

            threading.Thread(target=_finish_voice, daemon=True).start()

    hotkey = HotkeyListener(
        on_screenshot=_on_screenshot_hotkey,
        on_voice_toggle=_on_voice_toggle,
    )
    hotkey.start()

    # ── System tray ───────────────────────────────────────────────

    def _quit():
        hotkey.stop()
        tts.stop()
        bull.destroy()

    def _show():
        bull._win.deiconify()

    def _hide():
        bull._win.withdraw()
        if popover:
            popover.hide()

    def _mode_change(new_mode: str, new_tf: str):
        brain.update_mode(new_mode, new_tf)
        if popover:
            popover._update_header()

    def _ticker_change(new_ticker: str):
        brain.update_ticker(new_ticker)
        if popover:
            popover._update_header()

    # Phase 1: Screenshot in tray menu
    def _screenshot():
        _run_screenshot_analysis()

    tray = TrayIcon(
        on_quit=_quit,
        on_show=_show,
        on_hide=_hide,
        on_ticker_change=_ticker_change,
        on_mode_change=_mode_change,
        on_screenshot=_screenshot,
    )
    tray.start()

    bull._win.after(1500, bull.show_done)
    bull.run()


if __name__ == "__main__":
    main()
