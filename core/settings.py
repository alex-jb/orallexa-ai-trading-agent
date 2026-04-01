"""
core/settings.py
──────────────────────────────────────────────────────────────────
Persistent user settings stored in a JSON file.

Usage:
    from core.settings import Settings
    s = Settings()
    s.get("ticker", "NVDA")
    s.set("ticker", "TSLA")
    s.save()
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SETTINGS_FILE = Path(__file__).parent.parent / "memory_data" / "user_settings.json"

_DEFAULTS: dict[str, Any] = {
    "ticker": "NVDA",
    "mode": "scalp",
    "account_size": 10000,
    "risk_pct": 1.0,
    "language": "en",
    "voice_on": True,
    "timeframe": "15m",
}


class Settings:
    """Thread-safe, file-backed user settings."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _SETTINGS_FILE
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, **kwargs: Any) -> None:
        self._data.update(kwargs)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)
