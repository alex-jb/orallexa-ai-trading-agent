"""Fixed SMA20/50 long-or-flat loop for an Alpaca PAPER account.

Dry-run is the default. No LLM is called. State and an append-only decision/fill
ledger live in logs/ (gitignored). Run once per market day after the open.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from engine.token_budget import TokenBudget

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day"}


def _value(value) -> str:
    return str(getattr(value, "value", value)).lower()


def _completed_daily_closes(bars, now: datetime) -> list[float]:
    """Alpaca daily bars are stamped at UTC session midnight; exclude today."""
    today_ny = now.astimezone(NY).date()
    return [float(bar.close) for bar in bars
            if bar.timestamp.astimezone(timezone.utc).date() < today_ny and bar.close > 0]


class PaperGateway(Protocol):
    def market_open(self) -> bool: ...
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
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        request = StockBarsRequest(
            symbol_or_symbols=ticker, timeframe=TimeFrame.Day,
            start=now - timedelta(days=130), end=now, feed=DataFeed.IEX,
        )
        bars = self.data.get_stock_bars(request).data.get(ticker, [])
        return _completed_daily_closes(bars, now)


class PaperLoop:
    def __init__(self, state_path: Path, ledger_path: Path, *, qty: int = 1,
                 broker: PaperGateway | None = None, submit_paper: bool = False):
        if qty < 1 or qty > 100:
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

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _log(self, row: dict) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    def _mark(self, item: dict, price: float) -> tuple[float, float, float]:
        initial = item["benchmark_price"] * self.qty
        unrealized = item["position_qty"] * (price - item["entry_price"])
        equity = initial + item["realized_pnl"] + unrealized
        item["peak_equity"] = max(item["peak_equity"], equity)
        drawdown = (equity / item["peak_equity"] - 1) * 100 if item["peak_equity"] > 0 else 0.0
        buy_hold_pnl = self.qty * (price - item["benchmark_price"])
        return equity, drawdown, buy_hold_pnl

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
            row["slippage_bps"] = adverse / pending["signal_price"] * 10000
            row["realized_pnl_delta_usd"] = (delta_qty * (delta_price - pending["entry_price"])
                                             if pending["side"] == "SELL" else 0.0)
        row["order_status"] = order["status"]
        row["order_id"] = pending["id"]
        row["order_type"] = "market"
        row["qty"] = pending["qty"]
        if order["status"] in TERMINAL:
            item.pop("pending", None)

    def run_ticker(self, ticker: str, closes: list[float], *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        ticker = ticker.upper()
        if not re.fullmatch(r"[A-Z]{1,5}", ticker):
            raise ValueError("Invalid ticker")
        row = {
            "timestamp": now.isoformat(), "ticker": ticker,
            "signal": "HOLD", "signal_price": None, "sma20": None, "sma50": None,
            "order_type": None, "qty": 0, "order_id": None, "order_status": None,
            "filled_qty": 0.0, "fill_price": None, "slippage_bps": None,
            "fees_usd": 0.0, "fees_source": "assumed_zero_paper_commission",
            "realized_pnl_delta_usd": 0.0, "realized_pnl_total_usd": 0.0,
            "strategy_equity_usd": None, "drawdown_pct": None,
            "buy_hold_pnl_usd": None, "buy_hold_return_pct": None,
            "llm_api_cost_usd_week": 0.0,
        }
        if len(closes) < 50 or any(p <= 0 for p in closes[-50:]):
            row["order_status"] = "insufficient_completed_bars"
            self._log(row)
            return row

        price = float(closes[-1])
        item = self.state["tickers"].setdefault(ticker, {
            "benchmark_price": price, "first_date": now.astimezone(NY).date().isoformat(),
            "position_qty": 0.0, "entry_price": 0.0,
            "realized_pnl": 0.0, "peak_equity": self.qty * price,
        })
        row["signal_price"] = price
        row["sma20"] = sum(closes[-20:]) / 20
        row["sma50"] = sum(closes[-50:]) / 50
        row["signal"] = "BUY" if row["sma20"] > row["sma50"] else "SELL"

        if item.get("pending"):
            try:
                self._reconcile(ticker, item, row)
                row["order_status"] = row["order_status"] or "pending"
            except Exception as exc:
                row.update(order_status="broker_error", error_type=type(exc).__name__)
        else:
            desired = self.qty if row["signal"] == "BUY" else 0
            action = "BUY" if desired > 0 and item["position_qty"] == 0 else (
                "SELL" if desired == 0 and item["position_qty"] > 0 else None)
            if action is None:
                row["order_status"] = "no_change"
            elif not self.submit_paper:
                row.update(order_type="market", qty=int(self.qty if action == "BUY" else item["position_qty"]),
                           order_status="dry_run")
            else:
                assert self.broker is not None
                order_qty = self.qty if action == "BUY" else item["position_qty"]
                client_id = f"orallexa-paper-{now.astimezone(NY):%Y%m%d}-{ticker}-{action}"
                row.update(order_type="market", qty=order_qty)
                try:
                    # Recover an order submitted before a process crash.
                    order = self.broker.by_client_id(client_id)
                    if order is None:
                        broker_qty = self.broker.position_qty(ticker)
                        if abs(broker_qty - item["position_qty"]) > 1e-6:
                            row["order_status"] = "position_mismatch"
                        elif not self.broker.market_open():
                            row["order_status"] = "market_closed"
                        else:
                            order = self.broker.submit_market(ticker, action, order_qty, client_id)
                    if order is not None:
                        item["pending"] = {
                            "id": order["id"], "side": action, "qty": order_qty,
                            "signal_price": price, "entry_price": item["entry_price"],
                            "accounted_qty": 0.0, "accounted_notional": 0.0,
                        }
                        self._save()  # Preserve order ID before polling fills.
                        self._reconcile(ticker, item, row)
                except Exception as exc:
                    row.update(order_status="broker_error", error_type=type(exc).__name__)

        equity, drawdown, buy_hold = self._mark(item, price)
        row["realized_pnl_total_usd"] = item["realized_pnl"]
        row["strategy_equity_usd"] = equity
        row["drawdown_pct"] = drawdown
        row["buy_hold_pnl_usd"] = buy_hold
        row["buy_hold_return_pct"] = (price / item["benchmark_price"] - 1) * 100
        self._save()
        self._log(row)
        return row

    def report(self, marks: dict[str, float]) -> dict:
        """Compare identical tickers, start dates, and fixed share quantities."""
        equity = buy_hold = initial = 0.0
        for ticker, item in self.state["tickers"].items():
            if ticker not in marks:
                continue
            mark, _, hold = self._mark(item, marks[ticker])
            equity += mark
            buy_hold += hold
            initial += item["benchmark_price"] * self.qty
        return {
            "periods": {k: v["first_date"] for k, v in self.state["tickers"].items() if k in marks},
            "strategy_pnl_usd": equity - initial,
            "buy_hold_pnl_usd": buy_hold,
            "initial_notional_usd": initial,
            "llm_api_cost_usd_week": 0.0,
            "llm_cap_usd": self.token_budget.cap_usd,
            "scope": "fixed_rule_harness_only",
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
    for ticker in [s.strip().upper() for s in args.tickers.split(",") if s.strip()]:
        if args.bars_dir:
            import pandas as pd
            df = pd.read_csv(args.bars_dir / f"{ticker}.csv", parse_dates=["Date"])
            df = df.loc[df["Date"].dt.date < now.astimezone(NY).date()]
            closes = df["Close"].astype(float).tolist()
        else:
            assert gateway is not None
            closes = gateway.completed_closes(ticker, now)
        row = loop.run_ticker(ticker, closes, now=now)
        if row["signal_price"] is not None:
            marks[ticker] = row["signal_price"]
        print(json.dumps(row, sort_keys=True))
    print(json.dumps(loop.report(marks), sort_keys=True))


if __name__ == "__main__":
    main()
