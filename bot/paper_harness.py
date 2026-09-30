"""Fixed SMA20/50 long-or-flat loop for an Alpaca PAPER account.

Dry-run is the default. No LLM is called. State and an append-only decision/fill
ledger live in logs/ (gitignored). Run once per market day after the open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from engine.token_budget import TokenBudget

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {"filled", "canceled", "expired", "rejected"}
BENCHMARK_BASIS = "hypothetical_prior_close_no_executable_entry"
CONDITIONAL_BASIS = "conditional_first_completed_buy_order_same_paper_fill_schedule"
RULE_VERSION = "sma20_50_long_flat_v1"
SOURCE_KINDS = frozenset({"alpaca_iex_daily_bars", "csv_date_close",
                          "caller_supplied_completed_closes"})


def _value(value) -> str:
    return str(getattr(value, "value", value)).lower()


def _completed_daily_closes(bars, now: datetime) -> list[float]:
    """Alpaca daily bars are stamped at UTC session midnight; exclude today."""
    today_ny = now.astimezone(NY).date()
    return [float(bar.close) for bar in bars
            if bar.timestamp.astimezone(timezone.utc).date() < today_ny and bar.close > 0]


class PaperGateway(Protocol):
    def market_open(self) -> bool: ...
    def last_completed_session(self, now: datetime) -> date | None: ...
    def position_qty(self, ticker: str) -> float: ...
    def submit_market(self, ticker: str, side: str, qty: int, client_id: str) -> dict: ...
    def by_client_id(self, client_id: str) -> dict | None: ...
    def order(self, order_id: str) -> dict: ...


class AlpacaPaperGateway:
    """Only constructs TradingClient(paper=True); no live URL override."""

    def __init__(self) -> None:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        key = os.environ.get("ALPACA_API_KEY", "")
        secret = os.environ.get("ALPACA_SECRET_KEY", "")
        if not key or not secret:
            raise ValueError("Alpaca PAPER credentials are required")
        from alpaca.trading.client import TradingClient
        self.client = TradingClient(key, secret, paper=True)
        from alpaca.data.historical import StockHistoricalDataClient
        self.data = StockHistoricalDataClient(key, secret)

    @staticmethod
    def _order(raw) -> dict:
        return {
            "id": str(raw.id),
            "status": _value(raw.status),
            "filled_qty": float(raw.filled_qty or 0),
            "filled_avg_price": float(raw.filled_avg_price or 0),
        }

    def market_open(self) -> bool:
        return bool(self.client.get_clock().is_open)

    def last_completed_session(self, now: datetime) -> date | None:
        """Read Alpaca's scheduled equity sessions; never trust a weekday guess."""
        from alpaca.trading.requests import GetCalendarRequest
        today = now.astimezone(NY).date()
        sessions = self.client.get_calendar(GetCalendarRequest(
            start=today - timedelta(days=14), end=today - timedelta(days=1)))
        dates = [session.date for session in sessions if session.date < today]
        return max(dates, default=None)

    def position_qty(self, ticker: str) -> float:
        for position in self.client.get_all_positions():
            if position.symbol == ticker:
                return float(position.qty)
        return 0.0

    def submit_market(self, ticker: str, side: str, qty: int, client_id: str) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
        request = MarketOrderRequest(
            symbol=ticker, qty=qty,
            side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY, client_order_id=client_id,
        )
        return self._order(self.client.submit_order(request))

    def by_client_id(self, client_id: str) -> dict | None:
        from alpaca.common.exceptions import APIError
        try:
            return self._order(self.client.get_order_by_client_id(client_id))
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def order(self, order_id: str) -> dict:
        return self._order(self.client.get_order_by_id(order_id))

    def completed_closes(self, ticker: str, now: datetime) -> list[float]:
        return self.completed_closes_with_dates(ticker, now)[0]

    def completed_closes_with_dates(self, ticker: str, now: datetime) -> tuple[list[float], date | None]:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        request = StockBarsRequest(
            symbol_or_symbols=ticker, timeframe=TimeFrame.Day,
            start=now - timedelta(days=130), end=now, feed=DataFeed.IEX,
        )
        bars = self.data.get_stock_bars(request).data.get(ticker, [])
        complete = [bar for bar in bars
                    if bar.timestamp.astimezone(timezone.utc).date() < now.astimezone(NY).date()
                    and bar.close > 0]
        complete.sort(key=lambda bar: bar.timestamp)
        return [float(bar.close) for bar in complete], (complete[-1].timestamp.astimezone(timezone.utc).date()
                                                       if complete else None)


class PaperLoop:
    def __init__(self, state_path: Path, ledger_path: Path, *, qty: int = 1,
                 broker: PaperGateway | None = None, submit_paper: bool = False):
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1 or qty > 100:
            raise ValueError("Fixed share quantity must be between 1 and 100")
        if submit_paper and broker is None:
            raise ValueError("Paper submission requires an Alpaca PAPER gateway")
        if submit_paper and os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes"):
            raise ValueError("Paper submission is disabled in demo mode")
        self.state_path = Path(state_path)
        self.ledger_path = Path(ledger_path)
        self.qty = qty
        self.broker = broker
        self.submit_paper = submit_paper
        # The fixed-rule loop never calls a model. A zero-cap budget makes that
        # constraint explicit, including for future extensions.
        self.token_budget = TokenBudget(cap_tokens=0, cap_usd=0.0, label="paper_fixed_rule")
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"tickers": {}}
        configured_qty = self.state.get("config", {}).get("qty")
        if configured_qty is None and self.state["tickers"]:
            raise ValueError("Existing pilot state lacks a recorded share quantity; start a new pilot")
        if configured_qty is not None and configured_qty != qty:
            raise ValueError("Fixed share quantity differs from the saved pilot configuration")
        self.state.setdefault("config", {"qty": qty})

    def _save(self) -> None:
        self._ensure_directory(self.state_path.parent)
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(self.state, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_path)
        self._fsync_directory(self.state_path.parent)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _ensure_directory(cls, path: Path) -> None:
        missing = []
        current = path
        while not current.exists():
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir()
            cls._fsync_directory(directory.parent)

    def _log(self, row: dict) -> None:
        self._ensure_directory(self.ledger_path.parent)
        with self.ledger_path.open("ab") as stream:
            stream.write(self._ledger_line(row))
            stream.flush()
            os.fsync(stream.fileno())
        self._fsync_directory(self.ledger_path.parent)

    @staticmethod
    def _ledger_line(row: dict) -> bytes:
        return (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")

    def _require_ledger_for_saved_tickers(self) -> None:
        if self.state["tickers"] and not self.ledger_path.exists():
            raise ValueError("Paper audit ledger is missing for existing pilot state")

    def _deliver_outbox(self) -> None:
        """Replay a saved row only after validating the entire append-only ledger.

        An interrupted append can leave even a valid JSON object without its final
        newline. Never append to, or treat as delivered, an ambiguous tail: the
        operator must preserve the evidence and repair the ledger explicitly.
        """
        row = self.state.get("outbox")
        if row is None:
            self._require_ledger_for_saved_tickers()
        if row is not None and (not isinstance(row, dict)
                                or not isinstance(row.get("event_id"), str)
                                or not row["event_id"]):
            raise ValueError("Saved paper audit outbox has no valid event_id")
        found = False
        seen: set[str] = set()
        if self.ledger_path.exists():
            with self.ledger_path.open("rb") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.endswith(b"\n"):
                        raise ValueError(f"Paper audit ledger row {number} has no final newline")
                    try:
                        existing = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise ValueError(f"Paper audit ledger row {number} is invalid JSON") from exc
                    if (not isinstance(existing, dict)
                            or not isinstance(existing.get("event_id"), str)
                            or not existing["event_id"]):
                        raise ValueError(f"Paper audit ledger row {number} has no valid event_id")
                    event_id = existing["event_id"]
                    if event_id in seen:
                        raise ValueError(f"Paper audit ledger row {number} has a duplicate event_id")
                    seen.add(event_id)
                    if row is not None and event_id == row["event_id"]:
                        if line != self._ledger_line(row):
                            raise ValueError(f"Paper audit ledger row {number} conflicts with saved outbox")
                        found = True
        if row is None:
            return
        if not found:
            self._log(row)
        self.state.pop("outbox")
        try:
            self._save()
        except Exception:
            # A caller may catch the I/O error and retry using this object.
            # Keep the persisted audit row in memory until it is checkpointed.
            self.state["outbox"] = row
            raise

    def _record(self, row: dict) -> None:
        """Checkpoint state and an audit row together through a durable outbox."""
        if self.state.get("outbox") is not None:
            raise RuntimeError("Unrecovered audit row blocks a new decision")
        row["event_id"] = uuid.uuid4().hex
        self.state["outbox"] = row
        self._save()
        self._deliver_outbox()

    def _mark(self, item: dict, price: float) -> tuple[float, float, float]:
        initial = item["benchmark_price"] * self.qty
        unrealized = item["position_qty"] * (price - item["entry_price"])
        equity = initial + item["realized_pnl"] + unrealized
        item["peak_equity"] = max(item["peak_equity"], equity)
        drawdown = (equity / item["peak_equity"] - 1) * 100 if item["peak_equity"] > 0 else 0.0
        buy_hold_pnl = self.qty * (price - item["benchmark_price"])
        return equity, drawdown, buy_hold_pnl

    def _conditional_mark(self, item: dict, price: float, mark_date: date | None) -> tuple[dict | None, str | None]:
        """Compare from the first complete BUY fill schedule at a later close."""
        if item.get("comparison_stale"):
            return None, item["comparison_stale"]
        if item.get("conditional_entry_exclusion"):
            return None, item["conditional_entry_exclusion"]
        entry = item.get("conditional_entry")
        if entry is None:
            return None, "no_completed_paper_buy_order"
        if mark_date is None:
            return None, "completed_bar_date_unavailable"
        last_fill = item.get("last_fill_observed_at", entry["last_observed_at"])
        if mark_date <= datetime.fromisoformat(last_fill).astimezone(NY).date():
            return None, "mark_not_after_last_observed_fill"
        strategy = (item["realized_pnl"] - entry["realized_pnl_before_entry"]
                    + item["position_qty"] * (price - item["entry_price"]))
        hold = entry["qty"] * (price - entry["entry_vwap"])
        return {"strategy_pnl_usd": strategy, "buy_hold_pnl_usd": hold,
                "difference_usd": strategy - hold, "entry_order_id": entry["order_id"],
                "first_fill_observed_at": entry["first_observed_at"],
                "completed_order_observed_at": entry["last_observed_at"],
                "entry_vwap_usd": entry["entry_vwap"], "mark_date": mark_date.isoformat()}, None

    def _reconcile(self, ticker: str, item: dict, row: dict) -> None:
        pending = item.get("pending")
        if not pending or self.broker is None:
            return
        order = self.broker.order(pending["id"])
        filled = float(order["filled_qty"])
        notional = filled * float(order["filled_avg_price"])
        delta_qty = filled - pending["accounted_qty"]
        if delta_qty < -1e-9:
            raise ValueError("Broker filled quantity went backwards")
        if delta_qty > 1e-9:
            if filled - delta_qty == 0 and pending["side"] == "BUY":
                pending["first_observed_at"] = row["timestamp"]
                pending["realized_pnl_before_entry"] = item["realized_pnl"]
            delta_price = (notional - pending["accounted_notional"]) / delta_qty
            if pending["side"] == "BUY":
                old_qty = item["position_qty"]
                item["entry_price"] = ((old_qty * item["entry_price"] + delta_qty * delta_price)
                                       / (old_qty + delta_qty))
                item["position_qty"] += delta_qty
            else:
                item["realized_pnl"] += delta_qty * (delta_price - item["entry_price"])
                item["position_qty"] -= delta_qty
                if abs(item["position_qty"]) < 1e-9:
                    item["position_qty"] = 0.0
                    item["entry_price"] = 0.0
            pending["accounted_qty"] = filled
            pending["accounted_notional"] = notional
            row["fill_price"] = delta_price
            row["filled_qty"] = delta_qty
            adverse = (delta_price - pending["signal_price"]) if pending["side"] == "BUY" else (pending["signal_price"] - delta_price)
            row["signal_to_fill_drift_bps"] = adverse / pending["signal_price"] * 10000
            row["realized_pnl_delta_usd"] = (delta_qty * (delta_price - pending["entry_price"])
                                             if pending["side"] == "SELL" else 0.0)
            item["last_fill_observed_at"] = row["timestamp"]
        row["order_status"] = order["status"]
        row["order_id"] = pending["id"]
        row["order_type"] = "market"
        row["qty"] = pending["qty"]
        if (order["status"] == "filled" and pending["side"] == "BUY"
                and "conditional_entry" not in item
                and "conditional_entry_exclusion" not in item
                and pending.get("first_observed_at") is not None
                and abs(item["position_qty"] - self.qty) < 1e-9):
            item["conditional_entry"] = {
                "order_id": pending["id"], "qty": self.qty,
                "entry_vwap": item["entry_price"],
                "realized_pnl_before_entry": pending["realized_pnl_before_entry"],
                "first_observed_at": pending["first_observed_at"],
                "last_observed_at": row["timestamp"],
            }
        if order["status"] in TERMINAL:
            if (pending["side"] == "BUY" and "conditional_entry" not in item
                    and 1e-9 < filled < pending["qty"] - 1e-9):
                item["conditional_entry_exclusion"] = "partial_buy_order_terminated_before_full_fill"
            item.pop("pending", None)

    @staticmethod
    def _attach_order(item: dict, order: dict, intent: dict) -> None:
        if not order.get("id"):
            raise ValueError("Broker order ID is unavailable")
        item["pending"] = {
            "id": order["id"], "side": intent["side"], "qty": intent["qty"],
            "signal_price": intent["signal_price"], "entry_price": intent["entry_price"],
            "accounted_qty": 0.0, "accounted_notional": 0.0,
        }
        item.pop("intent", None)

    def run_ticker(self, ticker: str, closes: list[float], *, now: datetime | None = None,
                   mark_date: date | None = None,
                   data_fetch_error_type: str | None = None,
                   source_kind: str = "caller_supplied_completed_closes") -> dict:
        self._deliver_outbox()  # Recover any fill record before reading the broker or making a decision.
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if mark_date is not None and mark_date >= now.astimezone(NY).date() and not self.submit_paper:
            raise ValueError("mark_date must be a completed earlier session")
        ticker = ticker.upper()
        if not re.fullmatch(r"[A-Z]{1,5}", ticker):
            raise ValueError("Invalid ticker")
        if source_kind not in SOURCE_KINDS:
            raise ValueError("Invalid completed-close source label")
        row = {
            "timestamp": now.isoformat(), "ticker": ticker,
            "signal": "HOLD", "signal_price": None, "sma20": None, "sma50": None,
            "order_type": None, "qty": 0, "order_id": None, "order_status": None,
            "filled_qty": 0.0, "fill_price": None, "signal_to_fill_drift_bps": None,
            "fees_usd": 0.0, "fees_source": "assumed_zero_paper_commission",
            "realized_pnl_delta_usd": 0.0, "realized_pnl_total_usd": 0.0,
            "strategy_equity_usd": None, "drawdown_pct": None,
            "buy_hold_pnl_usd": None, "buy_hold_return_pct": None,
            "benchmark_basis": BENCHMARK_BASIS,
            "conditional_benchmark_basis": CONDITIONAL_BASIS,
            "conditional_comparison": None,
            "conditional_comparison_excluded_reason": None,
            "comparison_valid": True,
            "llm_api_cost_usd_week": 0.0,
        }
        if data_fetch_error_type:
            row.update(data_status="paper_market_data_unavailable",
                       data_fetch_error_type=data_fetch_error_type,
                       error_type=data_fetch_error_type)
        item = self.state["tickers"].get(ticker)
        if item and item.get("intent"):
            # Resolve yesterday's client ID before considering today's signal or
            # data. A 404 is not proof that an accepted submission cannot appear.
            intent = item["intent"]
            row.update(event_type="intent_recovery", client_order_id=intent["client_id"],
                       order_type="market", qty=intent["qty"],
                       intent_signal_price=intent["signal_price"])
            if item.get("pending"):
                raise ValueError("Both an order intent and a pending order require review")
            if self.broker is None:
                row["order_status"] = "intent_requires_paper_broker"
            else:
                try:
                    order = self.broker.by_client_id(intent["client_id"])
                except Exception as exc:
                    row.update(order_status="intent_lookup_error", error_type=type(exc).__name__)
                else:
                    if order is None:
                        row["order_status"] = "intent_unresolved"
                    else:
                        self._attach_order(item, order, intent)
                        item["comparison_stale"] = "recovered_order_awaits_position_check"
                        self._save()  # Persist broker ID before polling its fills.
                        try:
                            self._reconcile(ticker, item, row)
                        except Exception as exc:
                            row.update(order_status="broker_error", error_type=type(exc).__name__)
                            item["comparison_stale"] = "broker_reconciliation_error"
            row["realized_pnl_total_usd"] = item["realized_pnl"]
            row["comparison_valid"] = False  # Recovery is not a new daily decision.
            row["conditional_comparison_excluded_reason"] = (
                item.get("comparison_stale") or "order_intent_recovery_not_daily_decision")
            self._record(row)
            return row

        if data_fetch_error_type or len(closes) < 50 or any(
                not math.isfinite(p) or p <= 0 for p in closes[-50:]):
            data_status = ("paper_market_data_unavailable" if data_fetch_error_type
                           else "insufficient_completed_bars")
            row["order_status"] = data_status
            row["conditional_comparison_excluded_reason"] = data_status
            item = self.state["tickers"].get(ticker)
            if self.submit_paper or data_fetch_error_type:
                row.update(data_status=data_status, comparison_valid=False)
            if self.submit_paper:
                self.state.setdefault("data_blocked", {})[ticker] = data_status
                if item:
                    item.setdefault("comparison_stale", data_status)
            if item and item.get("pending"):
                try:
                    self._reconcile(ticker, item, row)
                except Exception as exc:
                    row.update(order_status="broker_error", error_type=type(exc).__name__)
                    item["comparison_stale"] = "broker_reconciliation_error"
                row["realized_pnl_total_usd"] = item["realized_pnl"]
            if item and item.get("blocked_reason"):
                row["comparison_valid"] = False
                row["conditional_comparison_excluded_reason"] = "broker_position_mismatch"
            elif item and item.get("comparison_stale"):
                row["comparison_valid"] = False
                row["conditional_comparison_excluded_reason"] = item["comparison_stale"]
            self._record(row)
            return row

        if self.submit_paper:
            assert self.broker is not None
            expected = None
            if mark_date is None:
                data_status = "missing_completed_bar_date"
            elif mark_date >= now.astimezone(NY).date():
                data_status = "incomplete_completed_bar"
            else:
                try:
                    expected = self.broker.last_completed_session(now)
                except Exception as exc:
                    data_status = "paper_calendar_unavailable"
                    row["error_type"] = type(exc).__name__
                else:
                    if not isinstance(expected, date) or expected >= now.astimezone(NY).date():
                        data_status = "paper_calendar_unavailable"
                    elif mark_date != expected:
                        data_status = "stale_completed_bar"
                    else:
                        data_status = None
            if data_status:
                # A missing/stale source must never establish the benchmark or
                # reach submit_market. Existing fills still need reconciliation.
                row.update(data_status=data_status, order_status=data_status,
                           source_as_of_session=mark_date.isoformat() if mark_date else None,
                           expected_last_session=expected.isoformat() if isinstance(expected, date) else None,
                           comparison_valid=False,
                           conditional_comparison_excluded_reason=data_status)
                self.state.setdefault("data_blocked", {})[ticker] = data_status
                item = self.state["tickers"].get(ticker)
                if item:
                    item["comparison_stale"] = data_status
                    if item.get("pending"):
                        try:
                            self._reconcile(ticker, item, row)
                        except Exception as exc:
                            row.update(order_status="broker_error", error_type=type(exc).__name__)
                            item["comparison_stale"] = "broker_reconciliation_error"
                        row["realized_pnl_total_usd"] = item["realized_pnl"]
                self._record(row)
                return row
            self.state.get("data_blocked", {}).pop(ticker, None)

        # This is derived input evidence, not raw exchange bars. Persist the
        # exact float values used in the fixed rule for offline replay.
        input_closes = [float(value) for value in closes[-50:]]
        price = input_closes[-1]
        item = self.state["tickers"].setdefault(ticker, {
            "benchmark_price": price, "first_date": now.astimezone(NY).date().isoformat(),
            "position_qty": 0.0, "entry_price": 0.0,
            "realized_pnl": 0.0, "peak_equity": self.qty * price,
        })
        row["signal_price"] = price
        row["sma20"] = sum(input_closes[-20:]) / 20
        row["sma50"] = sum(input_closes) / 50
        row["signal"] = "BUY" if row["sma20"] > row["sma50"] else "SELL"
        row.update(event_type="decision", rule_version=RULE_VERSION,
                   source_kind=source_kind,
                   source_as_of_session=mark_date.isoformat() if mark_date else None,
                   input_closes=input_closes,
                   input_closes_sha256=hashlib.sha256(json.dumps(
                       input_closes, separators=(",", ":"), allow_nan=False).encode()).hexdigest())

        had_pending = bool(item.get("pending"))
        reconciliation_error = False
        if had_pending:
            try:
                self._reconcile(ticker, item, row)
                row["order_status"] = row["order_status"] or "pending"
            except Exception as exc:
                row.update(order_status="broker_error", error_type=type(exc).__name__)
                item["comparison_stale"] = "broker_reconciliation_error"
                reconciliation_error = True
        if had_pending and not item.get("pending") and not reconciliation_error:
            # Persist the prior order's fill before today's decision can log a new order.
            row.update(realized_pnl_total_usd=item["realized_pnl"],
                       event_type="reconciliation")
            if item.get("comparison_stale"):
                row["comparison_valid"] = False
                row["conditional_comparison_excluded_reason"] = item["comparison_stale"]
            else:
                equity, drawdown, buy_hold = self._mark(item, price)
                conditional, excluded = self._conditional_mark(item, price, mark_date)
                row.update(strategy_equity_usd=equity, drawdown_pct=drawdown,
                           buy_hold_pnl_usd=buy_hold,
                           buy_hold_return_pct=(price / item["benchmark_price"] - 1) * 100,
                           conditional_comparison=conditional,
                           conditional_comparison_excluded_reason=excluded)
            reconciliation_row = {**row}
            for field in ("rule_version", "source_kind", "source_as_of_session",
                          "input_closes", "input_closes_sha256"):
                reconciliation_row.pop(field, None)
            self._record(reconciliation_row)
            row = {**row, "event_type": "decision", "event_id": None,
                   "order_id": None, "order_status": None, "order_type": None,
                   "qty": 0, "filled_qty": 0.0, "fill_price": None,
                   "signal_to_fill_drift_bps": None, "realized_pnl_delta_usd": 0.0,
                   "conditional_comparison": None,
                   "conditional_comparison_excluded_reason": None}
        if item.get("blocked_reason"):
            row["order_status"] = item["blocked_reason"]
        elif not item.get("pending") and not reconciliation_error:
            desired = self.qty if row["signal"] == "BUY" else 0
            action = "BUY" if desired > 0 and item["position_qty"] == 0 else (
                "SELL" if desired == 0 and item["position_qty"] > 0 else None)
            if action is None:
                row["order_status"] = "no_change"
                if self.submit_paper:
                    try:
                        assert self.broker is not None
                        if abs(self.broker.position_qty(ticker) - item["position_qty"]) > 1e-6:
                            row["order_status"] = "position_mismatch"
                            item["blocked_reason"] = "position_mismatch_requires_review"
                        else:
                            item.pop("comparison_stale", None)
                            row["comparison_valid"] = True
                    except Exception as exc:
                        row.update(order_status="broker_error", error_type=type(exc).__name__)
                        item["comparison_stale"] = "broker_state_unverified"
            elif not self.submit_paper:
                row.update(order_type="market", qty=int(self.qty if action == "BUY" else item["position_qty"]),
                           order_status="dry_run")
            else:
                assert self.broker is not None
                order_qty = self.qty if action == "BUY" else item["position_qty"]
                client_id = f"orallexa-paper-{now.astimezone(NY):%Y%m%d}-{ticker}-{action}"
                row.update(order_type="market", qty=order_qty)
                can_submit = False
                order = None
                try:
                    # Look up today's ID and check broker position before
                    # preparing the durable intent. Broker errors are loggable;
                    # local audit I/O errors below must always propagate.
                    order = self.broker.by_client_id(client_id)
                    if order is None:
                        broker_qty = self.broker.position_qty(ticker)
                        if abs(broker_qty - item["position_qty"]) > 1e-6:
                            row["order_status"] = "position_mismatch"
                            item["blocked_reason"] = "position_mismatch_requires_review"
                        else:
                            item.pop("comparison_stale", None)
                            row["comparison_valid"] = True
                            if not self.broker.market_open():
                                row["order_status"] = "market_closed"
                            else:
                                can_submit = True
                except Exception as exc:
                    row.update(order_status="broker_error", error_type=type(exc).__name__)
                    item["comparison_stale"] = "broker_state_unverified"

                intent = {
                    "client_id": client_id, "side": action, "qty": order_qty,
                    "signal_price": price, "entry_price": item["entry_price"],
                    "rule_version": RULE_VERSION,
                    "source_as_of_session": mark_date.isoformat() if mark_date else None,
                    "input_closes_sha256": row["input_closes_sha256"],
                }
                if can_submit:
                    item["intent"] = intent
                    self._record({**row, "event_type": "order_intent",
                                  "client_order_id": client_id, "order_status": "prepared",
                                  "rule_version": RULE_VERSION,
                                  "source_as_of_session": intent["source_as_of_session"],
                                  "input_closes_sha256": intent["input_closes_sha256"]})
                    try:
                        order = self.broker.submit_market(ticker, action, order_qty, client_id)
                    except Exception as exc:
                        row.update(order_status="submission_unconfirmed",
                                   error_type=type(exc).__name__)
                if order is not None:
                    self._attach_order(item, order, intent)
                    self._save()  # Preserve order ID before polling fills.
                    try:
                        self._reconcile(ticker, item, row)
                    except Exception as exc:
                        row.update(order_status="broker_error", error_type=type(exc).__name__)
                        item["comparison_stale"] = "broker_reconciliation_error"

        row["realized_pnl_total_usd"] = item["realized_pnl"]
        if item.get("blocked_reason"):
            row["comparison_valid"] = False
            row["conditional_comparison_excluded_reason"] = "broker_position_mismatch"
        elif item.get("comparison_stale"):
            row["comparison_valid"] = False
            row["conditional_comparison_excluded_reason"] = item["comparison_stale"]
        elif item.get("intent"):
            row["comparison_valid"] = False
            row["conditional_comparison_excluded_reason"] = "unresolved_paper_order_intent"
        else:
            equity, drawdown, buy_hold = self._mark(item, price)
            row["strategy_equity_usd"] = equity
            row["drawdown_pct"] = drawdown
            row["buy_hold_pnl_usd"] = buy_hold
            row["buy_hold_return_pct"] = (price / item["benchmark_price"] - 1) * 100
            row["conditional_comparison"], row["conditional_comparison_excluded_reason"] = (
                self._conditional_mark(item, price, mark_date))
        self._record(row)
        return row

    def report(self, marks: dict[str, float], *, mark_dates: dict[str, date] | None = None) -> dict:
        """Keep pilot-start and conditional first-buy comparisons distinct."""
        if any(ticker not in self.state["tickers"]
               for ticker in self.state.get("data_blocked", {})):
            raise ValueError("Missing or stale paper bar invalidates the paper comparison")
        if self.state.get("outbox") is not None:
            raise ValueError("Unrecovered paper audit row invalidates the comparison")
        self._deliver_outbox()  # No outbox: validate without changing state or ledger.
        equity = buy_hold = initial = 0.0
        eligible: dict[str, dict] = {}
        excluded: dict[str, str] = {}
        for ticker, item in self.state["tickers"].items():
            if item.get("intent"):
                raise ValueError(f"{ticker}: unresolved paper order intent invalidates the comparison")
            if item.get("blocked_reason"):
                raise ValueError(f"{ticker}: broker position mismatch invalidates the paper comparison")
            if item.get("comparison_stale"):
                raise ValueError(f"{ticker}: unverified broker state invalidates the paper comparison")
            if ticker not in marks:
                excluded[ticker] = "missing_completed_mark"
                continue
            mark, _, hold = self._mark(item, marks[ticker])
            equity += mark
            buy_hold += hold
            initial += item["benchmark_price"] * self.qty
            comparison, reason = self._conditional_mark(item, marks[ticker], (mark_dates or {}).get(ticker))
            if comparison is None:
                excluded[ticker] = reason
            else:
                eligible[ticker] = comparison
        aggregate = None
        if eligible and not excluded:
            aggregate = {
                "strategy_pnl_usd": sum(row["strategy_pnl_usd"] for row in eligible.values()),
                "buy_hold_pnl_usd": sum(row["buy_hold_pnl_usd"] for row in eligible.values()),
                "difference_usd": sum(row["difference_usd"] for row in eligible.values()),
            }
        return {
            "periods": {k: v["first_date"] for k, v in self.state["tickers"].items() if k in marks},
            "strategy_pnl_usd": equity - initial,
            "buy_hold_pnl_usd": buy_hold,
            "initial_notional_usd": initial,
            "llm_api_cost_usd_week": 0.0,
            "llm_cap_usd": self.token_budget.cap_usd,
            "scope": "fixed_rule_harness_only",
            "benchmark_basis": BENCHMARK_BASIS,
            "conditional_benchmark_basis": CONDITIONAL_BASIS,
            "conditional_comparison_scope": "only_after_first_completed_paper_buy_excludes_initial_flat_period",
            "conditional_comparison_by_ticker": eligible,
            "conditional_comparison_excluded": excluded,
            "conditional_comparison_aggregate": aggregate,
        }


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default="NVDA,AAPL,TSLA,GOOG,META,INTC,QQQ")
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--submit-paper", action="store_true", help="Explicitly enable Alpaca PAPER orders")
    parser.add_argument("--bars-dir", type=Path, help="Local Date,Close CSV files for dry-run only")
    parser.add_argument("--state", type=Path, default=ROOT / "logs/paper_harness_state.json")
    parser.add_argument("--ledger", type=Path, default=ROOT / "logs/paper_harness.jsonl")
    args = parser.parse_args()
    if args.submit_paper and (args.bars_dir or os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")):
        parser.error("Paper submission requires live Alpaca data and DEMO_MODE off")
    gateway = AlpacaPaperGateway() if args.submit_paper or not args.bars_dir else None
    loop = PaperLoop(args.state, args.ledger, qty=args.qty, broker=gateway, submit_paper=args.submit_paper)
    now = datetime.now(timezone.utc)
    marks = {}
    mark_dates = {}
    recovered_intent = False
    invalid_paper_data = False
    for ticker in [s.strip().upper() for s in args.tickers.split(",") if s.strip()]:
        data_fetch_error_type = None
        if args.bars_dir:
            import pandas as pd
            df = pd.read_csv(args.bars_dir / f"{ticker}.csv", parse_dates=["Date"])
            df = df.loc[df["Date"].dt.date < now.astimezone(NY).date()].sort_values("Date")
            closes = df["Close"].astype(float).tolist()
            mark_date = df["Date"].dt.date.iloc[-1] if not df.empty else None
        else:
            assert gateway is not None
            try:
                closes, mark_date = gateway.completed_closes_with_dates(ticker, now)
            except Exception as exc:
                closes, mark_date = [], None
                data_fetch_error_type = type(exc).__name__
        row = loop.run_ticker(ticker, closes, now=now, mark_date=mark_date,
                              data_fetch_error_type=data_fetch_error_type,
                              source_kind="csv_date_close" if args.bars_dir else "alpaca_iex_daily_bars")
        if row.get("event_type") == "intent_recovery":
            recovered_intent = True
        elif row.get("data_status"):
            invalid_paper_data = True
        elif row["signal_price"] is not None:
            marks[ticker] = row["signal_price"]
            mark_dates[ticker] = mark_date
        print(json.dumps(row, sort_keys=True))
    if recovered_intent:
        print(json.dumps({"report_status": "withheld_intent_recovery_requires_fresh_mark"},
                         sort_keys=True))
    elif invalid_paper_data:
        print(json.dumps({"report_status": "withheld_missing_or_stale_paper_bar"},
                         sort_keys=True))
    else:
        print(json.dumps(loop.report(marks, mark_dates=mark_dates), sort_keys=True))


if __name__ == "__main__":
    main()
