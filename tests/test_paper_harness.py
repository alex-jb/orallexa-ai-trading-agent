"""Paper loop lifecycle with a fake gateway: no network or broker calls."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.paper_harness import PaperLoop, _completed_daily_closes, AlpacaPaperGateway


BUY_BARS = [100.0] * 30 + [110.0] * 20
SELL_BARS = [110.0] * 30 + [90.0] * 20
DAY = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)


class FakePaperGateway:
    def __init__(self, *, immediate=True):
        self.immediate = immediate
        self.positions = {}
        self.orders = {}
        self.ids = {}
        self.submissions = []
        self.fill_prices = {"BUY": 110.11, "SELL": 89.91}

    def market_open(self):
        return True

    def position_qty(self, ticker):
        return self.positions.get(ticker, 0.0)

    def by_client_id(self, client_id):
        return self.orders.get(self.ids[client_id]) if client_id in self.ids else None

    def submit_market(self, ticker, side, qty, client_id):
        order_id = str(len(self.orders) + 1)
        self.ids[client_id] = order_id
        self.submissions.append((ticker, side, qty))
        if self.immediate:
            self.positions[ticker] = self.position_qty(ticker) + (qty if side == "BUY" else -qty)
        self.orders[order_id] = {
            "id": order_id, "status": "filled" if self.immediate else "new",
            "filled_qty": qty if self.immediate else 0,
            "filled_avg_price": self.fill_prices[side] if self.immediate else 0,
        }
        return self.orders[order_id]

    def order(self, order_id):
        return self.orders[order_id]


def loop(tmp_path, broker=None, submit=False):
    return PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                     broker=broker, submit_paper=submit)


def test_paper_buy_fill_sell_and_matched_buy_hold(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    buy = harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert buy["signal"] == "BUY"
    assert buy["order_status"] == "filled"
    assert buy["order_type"] == "market" and buy["qty"] == 1
    assert buy["fill_price"] == pytest.approx(110.11)
    assert buy["slippage_bps"] == pytest.approx(10)
    assert buy["fees_usd"] == 0.0
    assert buy["realized_pnl_total_usd"] == 0.0

    hold = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert hold["order_status"] == "no_change"
    assert len(broker.submissions) == 1

    sell = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=2))
    assert sell["signal"] == "SELL" and sell["order_status"] == "filled"
    assert sell["realized_pnl_delta_usd"] == pytest.approx(-20.20)
    assert sell["buy_hold_pnl_usd"] == pytest.approx(-20.0)
    assert sell["drawdown_pct"] < 0
    assert harness.report({"NVDA": 90.0})["llm_api_cost_usd_week"] == 0.0
    assert harness.token_budget.allow() is False
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert all("timestamp" in row and "ticker" in row and "drawdown_pct" in row for row in rows)


def test_dry_run_logs_intent_without_order_or_fill(tmp_path):
    harness = loop(tmp_path)
    row = harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert row["order_status"] == "dry_run"
    assert row["fill_price"] is None
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 0
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 1


def test_manual_broker_position_blocks_new_order(tmp_path):
    broker = FakePaperGateway()
    broker.positions["NVDA"] = 3.0
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY)
    assert row["order_status"] == "position_mismatch"
    assert broker.submissions == []


def test_pending_order_is_reconciled_without_resubmission(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    first = harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert first["order_status"] == "new"
    order = broker.orders["1"]
    order.update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    second = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(hours=1))
    assert second["filled_qty"] == 1
    assert second["order_status"] == "filled"
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 1
    assert len(broker.submissions) == 1


def test_insufficient_bars_and_broker_error_are_logged(tmp_path):
    broker = FakePaperGateway()
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", [100.0] * 49, now=DAY)
    assert row["order_status"] == "insufficient_completed_bars"
    broker.position_qty = lambda ticker: (_ for _ in ()).throw(RuntimeError("offline"))
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY)
    assert row["order_status"] == "broker_error"
    assert row["error_type"] == "RuntimeError"
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 2


def test_current_session_daily_bar_is_never_used():
    bars = [SimpleNamespace(timestamp=datetime(2026, 9, day, tzinfo=timezone.utc), close=day)
            for day in (28, 29)]
    assert _completed_daily_closes(bars, DAY) == [28.0]


def test_demo_mode_blocks_direct_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    with pytest.raises(ValueError, match="demo mode"):
        loop(tmp_path, FakePaperGateway(), submit=True)


def test_alpaca_gateway_forces_paper_client(monkeypatch):
    import alpaca.trading.client
    import alpaca.data.historical
    monkeypatch.setenv("ALPACA_API_KEY", "PK-test-only")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-only")
    arguments = {}
    monkeypatch.setattr(alpaca.trading.client, "TradingClient",
                        lambda *args, **kwargs: arguments.update(kwargs) or object())
    monkeypatch.setattr(alpaca.data.historical, "StockHistoricalDataClient",
                        lambda *args: object())
    AlpacaPaperGateway()
    assert arguments == {"paper": True}
