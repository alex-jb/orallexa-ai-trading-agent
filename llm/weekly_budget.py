"""Shared, durable admission budget for the API's paid Anthropic calls.

Reserve a conservative estimate *before* invoking the SDK. SQLite's immediate
transaction serializes requests across threads and workers sharing one file.
Successful calls release unused reservation using the provider's usage fields;
failed calls retain their reservation because a provider may still bill them.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from urllib.parse import quote


class WeeklyBudgetExceeded(RuntimeError):
    """A model call was blocked before a billable request was sent."""


_active_budget: WeeklyLLMBudget | None = None
_active_lock = threading.Lock()


def activate_weekly_budget(cap_usd: str, path: Path) -> None:
    """Enable one server-wide budget, with a persistent shared SQLite file."""
    global _active_budget
    with _active_lock:
        if (_active_budget is not None and _active_budget.path == Path(path)
                and _active_budget.cap_micro == WeeklyLLMBudget.parse_cap(cap_usd)):
            # Every authenticated paid request checks that the same ledger is
            # still present. Broker-only requests do not depend on this file.
            with _active_budget._connect() as conn:
                conn.execute("SELECT 1 FROM llm_reservations LIMIT 1")
            return
        _active_budget = WeeklyLLMBudget(cap_usd=cap_usd, path=path)


def reserve_if_active(model: str, max_tokens: int, messages: list, rates: dict) -> str | None:
    budget = _active_budget
    if budget is None:
        return None  # CLI callers are outside the API server's spend boundary.
    return budget.reserve(model, max_tokens, messages, rates)


def settle_if_active(reservation_id: str | None, actual_cost_usd: float) -> None:
    if reservation_id is not None:
        budget = _active_budget
        if budget is None:
            raise RuntimeError("Weekly LLM budget was disabled during an active call")
        budget.settle(reservation_id, actual_cost_usd)


class WeeklyLLMBudget:
    def __init__(self, cap_usd: str, path: Path):
        self.cap_micro = self.parse_cap(cap_usd)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS llm_reservations (
                id TEXT PRIMARY KEY, week_start TEXT NOT NULL, amount_micro INTEGER NOT NULL,
                model TEXT NOT NULL, reserved_at TEXT NOT NULL, actual_micro INTEGER
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS llm_reservations_week ON llm_reservations(week_start)")
        stat = self.path.stat()
        self._file_identity = (stat.st_dev, stat.st_ino)

    @staticmethod
    def parse_cap(cap_usd: str) -> int:
        try:
            cap = Decimal(str(cap_usd))
            if not cap.is_finite() or cap < 0:
                raise ValueError
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("ORALLEXA_WEEKLY_LLM_BUDGET_USD must be a nonnegative finite amount") from exc
        return int((cap * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))

    def _connect(self):
        stat = self.path.stat()
        if (stat.st_dev, stat.st_ino) != self._file_identity:
            raise RuntimeError("Weekly LLM budget ledger was replaced")
        # mode=rw prevents a deleted database from silently restarting the
        # weekly counter at zero while the server is running.
        return sqlite3.connect(f"file:{quote(str(self.path.resolve()))}?mode=rw", uri=True, timeout=10)

    @staticmethod
    def week_start(now: datetime) -> str:
        utc = now.astimezone(timezone.utc)
        return (utc.date() - timedelta(days=utc.weekday())).isoformat()

    @staticmethod
    def _micro(usd: float | Decimal) -> int:
        amount = Decimal(str(usd))
        if not amount.is_finite() or amount < 0:
            raise ValueError("LLM cost must be a nonnegative finite amount")
        return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))

    def reserve(self, model: str, max_tokens: int, messages: list, rates: dict) -> str:
        if model not in rates:
            raise WeeklyBudgetExceeded(f"Unknown LLM model pricing: {model}")
        price = rates[model]
        if max_tokens <= 0 or not isinstance(max_tokens, int):
            raise WeeklyBudgetExceeded("Invalid max_tokens for paid LLM call")
        if not all(math.isfinite(float(price[k])) and float(price[k]) >= 0 for k in ("input", "output")):
            raise WeeklyBudgetExceeded("Invalid LLM pricing configuration")

        # UTF-8 bytes are a conservative text token proxy. Image base64 is
        # included, plus an additional margin for image/tokens and wire roles.
        payload = json.dumps(messages, ensure_ascii=False).encode("utf-8")
        contains_image = b'"type": "image"' in payload
        input_upper = len(payload) + (8_192 if contains_image else 1_024)
        amount_micro = self._micro(
            Decimal(input_upper) * Decimal(str(price["input"]))
            + Decimal(max_tokens) * Decimal(str(price["output"]))
        )
        if amount_micro <= 0:
            raise WeeklyBudgetExceeded("Unknown or zero LLM call price")
        now = datetime.now(timezone.utc)
        week = self.week_start(now)
        reservation_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            used = conn.execute(
                "SELECT COALESCE(SUM(amount_micro), 0) FROM llm_reservations WHERE week_start=?", (week,)
            ).fetchone()[0]
            if used + amount_micro > self.cap_micro:
                raise WeeklyBudgetExceeded("Weekly API LLM budget exhausted")
            conn.execute(
                "INSERT INTO llm_reservations VALUES (?, ?, ?, ?, ?, NULL)",
                (reservation_id, week, amount_micro, model, now.isoformat()),
            )
        return reservation_id

    def settle(self, reservation_id: str, actual_cost_usd: float) -> None:
        actual_micro = self._micro(actual_cost_usd)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT amount_micro, actual_micro FROM llm_reservations WHERE id=?", (reservation_id,)
            ).fetchone()
            if row is None or row[1] is not None:
                raise RuntimeError("Unknown or settled LLM budget reservation")
            # If the provider reports more than the estimate, preserve the
            # truthful amount and block future calls. Invoice precision is
            # provider-dependent, so this is an admission gate, not billing.
            conn.execute(
                "UPDATE llm_reservations SET amount_micro=?, actual_micro=? WHERE id=?",
                (actual_micro, actual_micro, reservation_id),
            )
