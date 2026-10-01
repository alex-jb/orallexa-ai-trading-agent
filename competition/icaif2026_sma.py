"""Offline SMA20/50 target weights for the ICAIF 2026 starter-kit watch contract.

``strategy(observation)`` reads a participant-supplied local daily-close file and
returns weights only. It never creates a broker order or a competition upload.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
MAX_INPUT_BYTES = 16 * 1024 * 1024
BAR_FILE_ENV = "ORALLEXA_ICAIF_BARS_FILE"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp with an offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp with an offset") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must include an offset")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _public_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return (parts.scheme == "https" and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment)


def _read_bars(as_of: datetime) -> dict:
    name = os.environ.get(BAR_FILE_ENV)
    if not name:
        raise ValueError(f"Set {BAR_FILE_ENV} to a private, locally prepared JSON file")
    path = Path(name)
    if not path.is_absolute() or path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError("daily-close file must use an absolute path outside the repository")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("daily-close file exceeds 16 MiB")
    data = json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite)
    if not isinstance(data, dict) or set(data) != {"bars", "source"} or not isinstance(data["bars"], dict):
        raise ValueError("daily-close file needs bars and source provenance")
    source = data["source"]
    if (not isinstance(source, dict)
            or set(source) != {"url", "terms_url", "access", "permission_basis",
                               "competition_use_confirmed", "verified_at"}
            or not _public_url(source["url"])
            or not _public_url(source["terms_url"])
            or source["access"] != "public_free"
            or source["competition_use_confirmed"] is not True
            or not isinstance(source["permission_basis"], str)
            or not source["permission_basis"].strip()
            or len(source["permission_basis"]) > 500):
        raise ValueError("source must document public free access and permitted competition use")
    checked = _instant(source["verified_at"], "source verification time")
    if not as_of - timedelta(days=30) <= checked <= as_of:
        raise ValueError("source terms must have been verified by the decision cutoff")
    return data["bars"]


def _context(observation: dict) -> tuple[list[str], datetime]:
    if not isinstance(observation, dict):
        raise ValueError("starter-kit observation must be an object")
    phase, round_info = observation.get("phase"), observation.get("round")
    symbols = observation.get("symbols")
    if phase not in ("validation", "official") or not isinstance(round_info, dict):
        raise ValueError("invalid competition phase or round")
    round_id = round_info.get("id")
    if not isinstance(round_id, str) or not re.fullmatch(
            rf"{phase}-\d{{4}}-\d{{2}}-\d{{2}}-r[1-7]", round_id):
        raise ValueError("round ID and phase disagree")
    if round_info.get("status") in ("CANCELLED", "CANCELED"):
        raise ValueError("cancelled round")
    if (not isinstance(symbols, list) or len(symbols) != 30
            or len(set(map(str, symbols))) != 30
            or any(not isinstance(s, str) or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,5}", s)
                   for s in symbols)):
        raise ValueError("expected the organizer-confirmed 30-symbol universe")
    as_of = _instant(observation.get("as_of"), "as_of")
    opens = _instant(round_info.get("opens_at"), "round opening")
    deadline = _instant(round_info.get("deadline"), "round deadline")
    if not opens <= as_of < deadline:
        raise ValueError("decision is outside this round's submission window")
    return symbols, as_of


def weights_from_bars(observation: dict, bars: dict) -> dict[str, float]:
    """Compute a long-or-cash daily baseline without requesting a submission.

    Each symbol must have at least 50 *available*, completed session closes.
    A missing symbol aborts the whole decision; a zero weight is an intentional
    sell target in this competition, not a safe fallback for missing data.
    """
    symbols, as_of = _context(observation)
    if not isinstance(bars, dict) or set(bars) != set(symbols):
        raise ValueError("daily-close file must contain exactly the 30 round symbols")
    bullish = []
    for symbol in symbols:
        records = bars[symbol]
        if not isinstance(records, list):
            raise ValueError(f"{symbol}: expected daily-close records")
        seen_sessions = set()
        eligible = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {"timestamp", "available_at", "close"}:
                raise ValueError(f"{symbol}: malformed daily close")
            timestamp = _instant(record["timestamp"], f"{symbol} timestamp")
            available = _instant(record["available_at"], f"{symbol} availability")
            price = record["close"]
            if (available < timestamp or type(price) not in (int, float)
                    or not math.isfinite(price) or price <= 0):
                raise ValueError(f"{symbol}: invalid close or availability")
            eastern = timestamp.astimezone(NY)
            # A 13:00 or 15:00 price on a normal day is a partial session.
            # Early closes need a separately verified exchange calendar.
            if eastern.time() != time(16, 0):
                raise ValueError(f"{symbol}: expected a 16:00 ET completed daily close")
            if eastern.date() in seen_sessions:
                raise ValueError(f"{symbol}: duplicate market session")
            seen_sessions.add(eastern.date())
            if timestamp <= as_of and available <= as_of:
                eligible.append((timestamp, float(price)))
        eligible.sort(key=lambda row: row[0])
        if len(eligible) < 50 or as_of - eligible[-1][0] > timedelta(days=7):
            raise ValueError(f"{symbol}: fewer than 50 current, available daily closes")
        last = [price for _, price in eligible[-50:]]
        # Scale before summing: valid large prices must not turn both SMAs
        # into infinity and silently become a sell target.
        sma20 = math.fsum(price / 20 for price in last[-20:])
        sma50 = math.fsum(price / 50 for price in last)
        if not math.isfinite(sma20) or not math.isfinite(sma50):
            raise ValueError(f"{symbol}: non-finite moving average")
        if sma20 > sma50:
            bullish.append(symbol)
    weight = min(0.30, 1.0 / len(bullish)) if bullish else 0.0
    return {symbol: weight if symbol in bullish else 0.0 for symbol in symbols}


def strategy(observation: dict) -> dict[str, float]:
    """Importable callable for the organizer's ``watch --strategy`` interface.

    The organizer's client owns credentials, validation and transport. This
    callable performs none of those operations and returns no order quantities.
    """
    _, as_of = _context(observation)
    return weights_from_bars(observation, _read_bars(as_of))
