"""
desktop_agent/voice_handler.py
──────────────────────────────────────────────────────────────────
Microphone capture + OpenAI Whisper transcription.

Usage:
    vh = VoiceHandler()
    vh.start_recording()          # call when user presses mic button
    ...user speaks...
    text, lang = vh.stop_and_transcribe()   # "NVDA买入信号吗", "zh"

Language codes returned by Whisper: "en", "zh", "ja", etc.
"""
from __future__ import annotations

import io
import os
import threading
import wave
from typing import Optional

import numpy as np

from core.logger import get_logger

logger = get_logger("voice")

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16_000   # Hz  (Whisper prefers 16 kHz)
CHANNELS       = 1
DTYPE          = "int16"
MAX_SECONDS    = 30       # hard cap — auto-stop after this
SILENCE_DB     = -40      # dBFS below which audio is considered silence
SILENCE_SECS   = 1.5      # seconds of silence before auto-stop


class VoiceHandler:
    """
    Thread-safe push-to-talk recorder + Whisper transcriber.

    Public API
    ----------
    start_recording()            → starts mic capture in background thread
    stop_and_transcribe()        → stops capture, sends to Whisper, returns (text, lang)
    is_recording  (property)     → bool
    """

    def __init__(self) -> None:
        self._frames: list[np.ndarray] = []
        self._recording    = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event   = threading.Event()
        self._client       = self._make_client()

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start_recording(self) -> None:
        """Begin capturing from the default microphone.

        Raises RuntimeError if sounddevice is not installed.
        """
        if self._recording:
            return
        # Fail fast if dependency is missing
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            raise RuntimeError("sounddevice not installed — run: pip install sounddevice")
        self._frames     = []
        self._recording  = True
        self._stop_event = threading.Event()
        self._thread     = threading.Thread(target=self._capture, daemon=True)
        self._thread.start()

    def stop_and_transcribe(self) -> tuple[str, str]:
        """
        Stop recording, send audio to Whisper, return (text, lang_code).
        Blocks until transcription completes.
        Returns ("", "en") on any error.
        """
        self._stop_event.set()
        self._recording = False
        if self._thread:
            self._thread.join(timeout=5.0)

        if not self._frames:
            return "", "en"

        wav_bytes = self._frames_to_wav(self._frames)
        return self._transcribe(wav_bytes)

    # ── Recording thread ──────────────────────────────────────────────────────

    def _capture(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("sounddevice not installed — pip install sounddevice")
            self._recording = False
            return

        silence_frames = 0
        silence_limit  = int(SILENCE_SECS * SAMPLE_RATE / 1024)   # chunks
        max_chunks     = int(MAX_SECONDS * SAMPLE_RATE / 1024)
        total_chunks   = 0

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, blocksize=1024) as stream:
            while not self._stop_event.is_set():
                chunk, _ = stream.read(1024)
                self._frames.append(chunk.copy())
                total_chunks += 1

                # Auto-stop on silence
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                db  = 20 * np.log10(max(rms, 1e-9)) - 90   # rough dBFS
                if db < SILENCE_DB:
                    silence_frames += 1
                else:
                    silence_frames = 0

                if silence_frames >= silence_limit and total_chunks > 20:
                    break   # auto-stop after sustained silence
                if total_chunks >= max_chunks:
                    break   # hard cap

        self._recording = False

    # ── WAV conversion ────────────────────────────────────────────────────────

    @staticmethod
    def _frames_to_wav(frames: list[np.ndarray]) -> bytes:
        buf = io.BytesIO()
        audio = np.concatenate(frames, axis=0).flatten()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)           # int16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    # ── Whisper ───────────────────────────────────────────────────────────────

    def _transcribe(self, wav_bytes: bytes) -> tuple[str, str]:
        if self._client is None:
            return "[OpenAI API key not set]", "en"
        try:
            buf = io.BytesIO(wav_bytes)
            buf.name = "audio.wav"
            result = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=buf,
                response_format="verbose_json",
            )
            text = (result.text or "").strip()
            lang = getattr(result, "language", "en") or "en"
            return text, lang
        except Exception as exc:
            logger.warning("Whisper transcription error: %s", exc)
            return "", "en"

    @staticmethod
    def _make_client():
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — transcription disabled")
            return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=api_key)
        except ImportError:
            logger.warning("openai package not installed — transcription disabled")
            return None


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("VoiceHandler test — speak for up to 5 seconds then press Enter")
    vh = VoiceHandler()
    vh.start_recording()
    input("Recording... press Enter to stop\n")
    text, lang = vh.stop_and_transcribe()
    print(f"Text : {text!r}")
    print(f"Lang : {lang}")
