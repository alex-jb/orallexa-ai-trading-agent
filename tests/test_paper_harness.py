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
    assert buy["signal_to_fill_drift_bps"] == pytest.approx(10)
    assert buy["benchmark_basis"] == "hypothetical_prior_close_no_executable_entry"
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
    assert all(row["event_id"] for row in rows)


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
    assert second["order_status"] == "no_change"
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert rows[-2]["event_type"] == "reconciliation" and rows[-2]["filled_qty"] == 1
    assert rows[-2]["order_status"] == "filled"
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 1
    assert len(broker.submissions) == 1


def test_reconciled_buy_does_not_swallow_todays_sell_signal(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    row = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=1))
    assert row["signal"] == "SELL"
    assert broker.submissions == [("NVDA", "BUY", 1), ("NVDA", "SELL", 1.0)]
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert rows[-2]["event_type"] == "reconciliation"
    assert rows[-2]["fill_price"] == pytest.approx(110.11)
    assert rows[-1]["event_type"] == "decision"
    assert rows[-1]["order_id"] == "2" and rows[-1]["fill_price"] is None


def test_pending_fill_is_logged_even_when_bars_are_missing(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    row = harness.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=1))
    assert row["order_status"] == "filled" and row["filled_qty"] == 1
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 1
    assert len(broker.submissions) == 1


def test_done_for_day_waits_for_later_final_status(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    broker.orders["1"].update(status="done_for_day", filled_qty=0)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert harness.state["tickers"]["NVDA"]["pending"]["id"] == "1"
    broker.orders["1"].update(status="canceled")
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert any(row["order_status"] == "canceled" and row["order_id"] == "1" for row in rows)


def test_restart_with_different_fixed_quantity_fails_closed(tmp_path):
    broker = FakePaperGateway()
    loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY)
    with pytest.raises(ValueError, match="saved pilot configuration"):
        PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                  qty=2, broker=broker, submit_paper=True)
    assert len(broker.submissions) == 1


def test_old_state_without_quantity_requires_new_pilot(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"tickers": {"NVDA": {}}}))
    with pytest.raises(ValueError, match="lacks a recorded share quantity"):
        loop(tmp_path)


def test_no_change_detects_external_position_or_split(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    broker.positions["NVDA"] = 2.0
    row = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert row["order_status"] == "position_mismatch"
    assert row["comparison_valid"] is False
    assert row["strategy_equity_usd"] is None
    with pytest.raises(ValueError, match="invalidates the paper comparison"):
        harness.report({"NVDA": 110.0})
    broker.positions["NVDA"] = 1.0
    assert harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2))["order_status"] == "position_mismatch_requires_review"
    assert len(broker.submissions) == 1


def test_audit_outbox_replays_missing_fill_once_after_process_failure(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness._log = lambda row: (_ for _ in ()).throw(OSError("disk temporarily unavailable"))
    with pytest.raises(OSError, match="disk temporarily unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert not (tmp_path / "decisions.jsonl").exists()
    restarted = loop(tmp_path, broker, submit=True)
    restarted.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [row["order_status"] for row in rows] == ["filled", "no_change"]
    assert len({row["event_id"] for row in rows}) == 2
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_audit_outbox_deduplicates_crash_after_append(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    original_log = harness._log
    def fail_after_append(row):
        original_log(row)
        raise OSError("crash after append")
    harness._log = fail_after_append
    with pytest.raises(OSError, match="crash after append"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    restarted = loop(tmp_path, broker, submit=True)
    restarted.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [row["order_status"] for row in rows] == ["filled", "no_change"]
    assert len({row["event_id"] for row in rows}) == 2


def test_audit_outbox_remains_blocking_after_checkpoint_failure(tmp_path):
    harness = loop(tmp_path)
    original_save = harness._save
    def fail_after_append():
        if "outbox" not in harness.state:
            raise OSError("checkpoint failed")
        original_save()
    harness._save = fail_after_append
    with pytest.raises(OSError, match="checkpoint failed"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert harness.state["outbox"]["order_status"] == "dry_run"
    harness._save = original_save
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert len({row["event_id"] for row in rows}) == 2


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
