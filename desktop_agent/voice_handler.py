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
SILENCE_DB     = -35      # dBFS below which audio is considered silence (relaxed)
SILENCE_SECS   = 3.0      # seconds of silence before auto-stop (longer tolerance)
MIN_CHUNKS     = 30       # minimum ~2 seconds before auto-stop can trigger


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
        self._actual_rate  = SAMPLE_RATE

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
            logger.warning("No audio frames captured — mic may not be working")
            return "", "en"

        logger.info("Transcribing %d frames...", len(self._frames))
        wav_bytes = self._frames_to_wav(self._frames)
        text, lang = self._transcribe(wav_bytes)
        logger.info("Transcription result: text=%r, lang=%s", text[:80] if text else "", lang)
        return text, lang

    # ── Recording thread ──────────────────────────────────────────────────────

    def _capture(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("sounddevice not installed — pip install sounddevice")
            self._recording = False
            return

        # Use device's native sample rate to avoid MME/WASAPI errors on Windows
        try:
            dev_info = sd.query_devices(sd.default.device[0])
            native_rate = int(dev_info["default_samplerate"])
        except Exception:
            native_rate = SAMPLE_RATE
        self._actual_rate = native_rate

        silence_frames = 0
        silence_limit  = int(SILENCE_SECS * native_rate / 1024)
        max_chunks     = int(MAX_SECONDS * native_rate / 1024)
        total_chunks   = 0
        peak_db        = -999.0

        logger.info("Recording started (rate=%d, silence_db=%d, silence_secs=%.1f)",
                     native_rate, SILENCE_DB, SILENCE_SECS)

        try:
            with sd.InputStream(samplerate=native_rate, channels=CHANNELS,
                                dtype=DTYPE, blocksize=1024) as stream:
                while not self._stop_event.is_set():
                    chunk, _ = stream.read(1024)
                    self._frames.append(chunk.copy())
                    total_chunks += 1

                    # Compute dB level
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    db  = 20 * np.log10(max(rms, 1e-9))
                    if db > peak_db:
                        peak_db = db

                    # Auto-stop on silence (only after minimum recording)
                    if db < SILENCE_DB:
                        silence_frames += 1
                    else:
                        silence_frames = 0

                    if silence_frames >= silence_limit and total_chunks > MIN_CHUNKS:
                        logger.info("Auto-stop: silence for %.1fs after %d chunks",
                                    SILENCE_SECS, total_chunks)
                        break

                    if total_chunks >= max_chunks:
                        logger.info("Auto-stop: max duration reached")
                        break
        except Exception as exc:
            logger.error("Recording error: %s", exc)

        duration = total_chunks * 1024 / native_rate
        logger.info("Recording stopped: %.1fs, %d chunks, peak=%.1f dB, frames=%d",
                     duration, total_chunks, peak_db, len(self._frames))

        self._recording = False

    # ── WAV conversion ────────────────────────────────────────────────────────

    def _frames_to_wav(self, frames: list[np.ndarray]) -> bytes:
        buf = io.BytesIO()
        audio = np.concatenate(frames, axis=0).flatten()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)           # int16 = 2 bytes
            wf.setframerate(self._actual_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    # ── Whisper ───────────────────────────────────────────────────────────────

    def _transcribe(self, wav_bytes: bytes) -> tuple[str, str]:
        if self._client is None:
            return "[OpenAI API key not set]", "en"
        import tempfile
        tmp_path = None
        try:
            # Write to temp file to avoid BytesIO encoding issues on Windows
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name
            with open(tmp_path, "rb") as f:
                result = self._client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                )
            text = (result.text or "").strip()
            lang = getattr(result, "language", "en") or "en"
            return text, lang
        except Exception as exc:
            logger.warning("Whisper transcription error: %s", exc)
            return "", "en"
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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
