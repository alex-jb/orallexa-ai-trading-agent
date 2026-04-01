"""
desktop_agent/tts_handler.py
──────────────────────────────────────────────────────────────────
Text-to-speech via OpenAI TTS-1-HD.
Plays audio in a background thread so the UI stays responsive.

Usage:
    tts = TTSHandler()
    tts.speak("NVDA 显示买入信号，置信度 72%")   # auto-detects language
    tts.speak("Strong bullish signal on NVDA", voice="echo")
    tts.stop()   # interrupt current playback
"""
from __future__ import annotations

import io
import os
import threading
from typing import Optional

from core.logger import get_logger

logger = get_logger("tts")

# Voice options per language
_VOICE_BY_LANG: dict[str, str] = {
    "zh":      "nova",    # works well for Chinese
    "en":      "echo",
    "default": "nova",
}

# Available voices (for UI selector)
VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


class TTSHandler:
    """
    Non-blocking TTS player.

    speak(text, lang, voice)  → plays audio in background thread
    stop()                    → cuts current playback
    is_speaking (property)    → bool
    """

    def __init__(self) -> None:
        self._client      = self._make_client()
        self._thread: Optional[threading.Thread] = None
        self._stop_event  = threading.Event()
        self._speaking    = False

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def speak(self, text: str, lang: str = "en", voice: str = "") -> None:
        """Generate and play TTS in a background thread."""
        if not text.strip():
            return
        self.stop()   # stop any current playback
        self._stop_event = threading.Event()
        v = voice or _VOICE_BY_LANG.get(lang, _VOICE_BY_LANG["default"])
        self._thread = threading.Thread(
            target=self._play, args=(text, v), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Interrupt playback."""
        self._stop_event.set()
        self._speaking = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _play(self, text: str, voice: str) -> None:
        if self._client is None:
            return
        self._speaking = True
        try:
            response = self._client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=text,
            )
            audio_bytes = response.read()
            if not self._stop_event.is_set():
                self._play_bytes(audio_bytes)
        except Exception as exc:
            logger.warning("TTS error: %s", exc)
        finally:
            self._speaking = False

    def _play_bytes(self, data: bytes) -> None:
        """Play raw MP3 bytes using pygame or playsound fallback."""
        try:
            import pygame
            pygame.mixer.init()
            buf = io.BytesIO(data)
            pygame.mixer.music.load(buf, "mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                pygame.time.wait(50)
        except ImportError:
            self._play_bytes_playsound(data)
        except Exception as exc:
            logger.warning("pygame playback error: %s", exc)
            self._play_bytes_playsound(data)

    def _play_bytes_playsound(self, data: bytes) -> None:
        """Fallback: write to temp file and play via playsound."""
        import tempfile
        try:
            from playsound import playsound
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(data)
                tmp = f.name
            if not self._stop_event.is_set():
                playsound(tmp, block=True)
        except ImportError:
            # Last resort: write and open with system player
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(data)
                tmp = f.name
            subprocess.Popen(["start", "", tmp], shell=True)
        except Exception as exc:
            logger.warning("playsound error: %s", exc)

    @staticmethod
    def _make_client():
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — TTS disabled")
            return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=api_key)
        except ImportError:
            logger.warning("openai package not installed — TTS disabled")
            return None


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    tts = TTSHandler()
    tts.speak("NVDA shows a strong bullish breakout signal today.", lang="en")
    import time; time.sleep(6)
    tts.speak("英伟达显示强烈的看涨突破信号。", lang="zh")
    time.sleep(6)
