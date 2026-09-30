"""Paper loop lifecycle with a fake gateway: no network or broker calls."""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import bot.paper_harness as paper_harness
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
        self.calendar_dates = None

    def market_open(self):
        return True

    def last_completed_session(self, now):
        today = now.astimezone(paper_harness.NY).date()
        if self.calendar_dates is not None:
            return max((session for session in self.calendar_dates if session < today), default=None)
        previous = today - timedelta(days=1)
        while previous.weekday() >= 5:
            previous -= timedelta(days=1)
        return previous

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
    buy = harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert buy["signal"] == "BUY"
    assert buy["order_status"] == "filled"
    assert buy["order_type"] == "market" and buy["qty"] == 1
    assert buy["fill_price"] == pytest.approx(110.11)
    assert buy["signal_to_fill_drift_bps"] == pytest.approx(10)
    assert buy["benchmark_basis"] == "hypothetical_prior_close_no_executable_entry"
    assert buy["fees_usd"] == 0.0
    assert buy["realized_pnl_total_usd"] == 0.0

    hold = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                              mark_date=date(2026, 9, 29))
    assert hold["order_status"] == "no_change"
    assert len(broker.submissions) == 1

    sell = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=2),
                              mark_date=date(2026, 9, 30))
    assert sell["signal"] == "SELL" and sell["order_status"] == "filled"
    assert sell["realized_pnl_delta_usd"] == pytest.approx(-20.20)
    assert sell["buy_hold_pnl_usd"] == pytest.approx(-20.0)
    assert sell["drawdown_pct"] < 0
    assert harness.report({"NVDA": 90.0})["llm_api_cost_usd_week"] == 0.0
    assert harness.token_budget.allow() is False
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [r.get("event_type") for r in rows] == ["order_intent", "decision", "decision",
                                                     "order_intent", "decision"]
    assert all("timestamp" in row and "ticker" in row and "drawdown_pct" in row for row in rows)
    assert all(row["event_id"] for row in rows)


def test_conditional_hold_uses_first_buy_fill_only_after_later_close(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    first = harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    intent = json.loads((tmp_path / "decisions.jsonl").read_text().splitlines()[0])
    assert intent["source_as_of_session"] == "2026-09-28"
    assert first["conditional_comparison"] is None
    assert first["conditional_comparison_excluded_reason"] == "mark_not_after_last_observed_fill"
    assert harness.report({"NVDA": 110.0}, mark_dates={"NVDA": date(2026, 9, 28)})[
        "conditional_comparison_aggregate"] is None

    next_bars = BUY_BARS[:-1] + [115.0]
    later = harness.run_ticker("NVDA", next_bars, now=DAY + timedelta(days=2),
                               mark_date=date(2026, 9, 30))
    comparison = later["conditional_comparison"]
    assert comparison["entry_vwap_usd"] == pytest.approx(110.11)
    assert comparison["buy_hold_pnl_usd"] == pytest.approx(4.89)
    assert comparison["strategy_pnl_usd"] == pytest.approx(4.89)
    aggregate = harness.report({"NVDA": 115.0}, mark_dates={"NVDA": date(2026, 9, 30)})[
        "conditional_comparison_aggregate"]
    assert aggregate["difference_usd"] == pytest.approx(0.0)
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_conditional_hold_excludes_initially_flat_tickers_and_no_mark(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    harness.run_ticker("AAPL", SELL_BARS, now=DAY, mark_date=date(2026, 9, 28))
    comparison = harness.report({"NVDA": 115.0, "AAPL": 90.0},
                                mark_dates={"NVDA": date(2026, 9, 30),
                                            "AAPL": date(2026, 9, 30)})
    assert comparison["conditional_comparison_excluded"] == {
        "AAPL": "no_completed_paper_buy_order"}
    assert comparison["conditional_comparison_aggregate"] is None
    missing_mark = harness.report({"NVDA": 115.0}, mark_dates={"NVDA": date(2026, 9, 30)})
    assert missing_mark["conditional_comparison_excluded"]["AAPL"] == "missing_completed_mark"
    assert missing_mark["conditional_comparison_aggregate"] is None


def test_conditional_hold_mirrors_partial_buy_schedule_then_waits_after_sell(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                        qty=2, broker=broker, submit_paper=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="partially_filled", filled_qty=1,
                              filled_avg_price=110.0)
    broker.positions["NVDA"] = 1.0
    partial = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                                 mark_date=date(2026, 9, 29))
    assert partial["conditional_comparison_excluded_reason"] == "no_completed_paper_buy_order"
    assert len(broker.submissions) == 1

    harness = PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                        qty=2, broker=broker, submit_paper=True)
    broker.orders["1"].update(status="filled", filled_qty=2, filled_avg_price=111.0)
    broker.positions["NVDA"] = 2.0
    complete = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                                  mark_date=date(2026, 9, 30))
    assert complete["conditional_comparison_excluded_reason"] == "mark_not_after_last_observed_fill"
    assert harness.state["tickers"]["NVDA"]["conditional_entry"]["first_observed_at"] == (
        DAY + timedelta(days=1)).isoformat()
    assert harness.state["tickers"]["NVDA"]["conditional_entry"]["entry_vwap"] == pytest.approx(111.0)

    later = harness.run_ticker("NVDA", BUY_BARS[:-1] + [120.0],
                               now=DAY + timedelta(days=6), mark_date=date(2026, 10, 2))
    assert later["conditional_comparison"]["strategy_pnl_usd"] == pytest.approx(18.0)
    assert later["conditional_comparison"]["buy_hold_pnl_usd"] == pytest.approx(18.0)

    broker.immediate = True
    sell = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=7),
                              mark_date=date(2026, 10, 5))
    assert sell["order_status"] == "filled"
    assert sell["conditional_comparison_excluded_reason"] == "mark_not_after_last_observed_fill"
    later = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=9),
                               mark_date=date(2026, 10, 7))
    assert later["conditional_comparison"]["strategy_pnl_usd"] == pytest.approx(-42.18)
    assert later["conditional_comparison"]["buy_hold_pnl_usd"] == pytest.approx(-42.0)
    assert later["conditional_comparison"]["difference_usd"] == pytest.approx(-0.18)
    assert broker.submissions == [("NVDA", "BUY", 2), ("NVDA", "SELL", 2.0)]


def test_conditional_hold_excludes_partial_buy_canceled_before_later_full_buy(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                        qty=2, broker=broker, submit_paper=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="partially_filled", filled_qty=1, filled_avg_price=110.0)
    broker.positions["NVDA"] = 1.0
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                       mark_date=date(2026, 9, 29))
    broker.orders["1"]["status"] = "canceled"
    canceled = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                                  mark_date=date(2026, 9, 30))
    assert canceled["conditional_comparison_excluded_reason"] == (
        "partial_buy_order_terminated_before_full_fill")

    harness = PaperLoop(tmp_path / "state.json", tmp_path / "decisions.jsonl",
                        qty=2, broker=broker, submit_paper=True)
    broker.immediate = True
    harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=6),
                       mark_date=date(2026, 10, 2))
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=7),
                       mark_date=date(2026, 10, 5))
    later = harness.run_ticker("NVDA", BUY_BARS[:-1] + [120.0],
                               now=DAY + timedelta(days=9), mark_date=date(2026, 10, 7))
    assert later["conditional_comparison"] is None
    assert later["conditional_comparison_excluded_reason"] == (
        "partial_buy_order_terminated_before_full_fill")
    assert harness.report({"NVDA": 120.0}, mark_dates={"NVDA": date(2026, 10, 7)})[
        "conditional_comparison_aggregate"] is None
    assert broker.submissions == [("NVDA", "BUY", 2), ("NVDA", "SELL", 1.0),
                                  ("NVDA", "BUY", 2)]


def test_conditional_report_fails_closed_after_reconciliation_error(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert harness.report({"NVDA": 120.0}, mark_dates={"NVDA": date(2026, 9, 30)})[
        "conditional_comparison_aggregate"] is not None

    broker.immediate = False
    harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=2),
                       mark_date=date(2026, 9, 30))
    broker.order = lambda order_id: (_ for _ in ()).throw(RuntimeError("broker offline"))
    failed = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=3),
                                mark_date=date(2026, 10, 1))
    assert failed["order_status"] == "broker_error"
    assert failed["comparison_valid"] is False
    assert failed["conditional_comparison_excluded_reason"] == "broker_reconciliation_error"
    with pytest.raises(ValueError, match="unverified broker state"):
        harness.report({"NVDA": 90.0}, mark_dates={"NVDA": date(2026, 10, 1)})
    broker.order = lambda order_id: broker.orders[order_id]
    broker.orders["2"].update(status="filled", filled_qty=1, filled_avg_price=89.91)
    broker.positions["NVDA"] = 0.0
    recovered = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=6),
                                   mark_date=date(2026, 10, 2))
    assert recovered["comparison_valid"] is True
    assert recovered["conditional_comparison_excluded_reason"] == "mark_not_after_last_observed_fill"
    harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=8),
                       mark_date=date(2026, 10, 6))
    assert harness.report({"NVDA": 90.0}, mark_dates={"NVDA": date(2026, 10, 6)})[
        "conditional_comparison_aggregate"] is not None
    assert broker.submissions == [("NVDA", "BUY", 1), ("NVDA", "SELL", 1.0)]


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
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert row["order_status"] == "position_mismatch"
    assert broker.submissions == []


def test_pending_order_is_reconciled_without_resubmission(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    first = harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert first["order_status"] == "new"
    order = broker.orders["1"]
    order.update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    second = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(hours=1),
                                mark_date=date(2026, 9, 28))
    assert second["order_status"] == "no_change"
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert rows[-2]["event_type"] == "reconciliation" and rows[-2]["filled_qty"] == 1
    assert "input_closes" not in rows[-2]  # Fill observation is not another rule decision.
    assert rows[-2]["order_status"] == "filled"
    assert rows[-1]["event_type"] == "decision"
    assert rows[-1]["input_closes"] == BUY_BARS
    assert rows[-2]["conditional_comparison_excluded_reason"] == "mark_not_after_last_observed_fill"
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 1
    assert len(broker.submissions) == 1


def test_reconciled_buy_does_not_swallow_todays_sell_signal(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    row = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=1),
                             mark_date=date(2026, 9, 29))
    assert row["signal"] == "SELL"
    assert broker.submissions == [("NVDA", "BUY", 1), ("NVDA", "SELL", 1.0)]
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert rows[-3]["event_type"] == "reconciliation"
    assert rows[-3]["fill_price"] == pytest.approx(110.11)
    assert rows[-2]["event_type"] == "order_intent"
    assert rows[-1]["event_type"] == "decision"
    assert rows[-1]["order_id"] == "2" and rows[-1]["fill_price"] is None


def test_pending_fill_is_logged_even_when_bars_are_missing(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    row = harness.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=1))
    assert row["order_status"] == "filled" and row["filled_qty"] == 1
    assert row["conditional_comparison_excluded_reason"] == "insufficient_completed_bars"
    assert harness.state["tickers"]["NVDA"]["position_qty"] == 1
    assert len(broker.submissions) == 1


def test_done_for_day_waits_for_later_final_status(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="done_for_day", filled_qty=0)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                       mark_date=date(2026, 9, 29))
    assert harness.state["tickers"]["NVDA"]["pending"]["id"] == "1"
    broker.orders["1"].update(status="canceled")
    harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                       mark_date=date(2026, 9, 30))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert any(row["order_status"] == "canceled" and row["order_id"] == "1" for row in rows)


def test_restart_with_different_fixed_quantity_fails_closed(tmp_path):
    broker = FakePaperGateway()
    loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
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
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.positions["NVDA"] = 2.0
    row = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                             mark_date=date(2026, 9, 29))
    assert row["order_status"] == "position_mismatch"
    assert row["comparison_valid"] is False
    assert row["strategy_equity_usd"] is None
    with pytest.raises(ValueError, match="invalidates the paper comparison"):
        harness.report({"NVDA": 110.0})
    with pytest.raises(ValueError, match="invalidates the paper comparison"):
        harness.report({})
    broker.positions["NVDA"] = 1.0
    assert harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                              mark_date=date(2026, 9, 30))["order_status"] == "position_mismatch_requires_review"
    assert len(broker.submissions) == 1


def test_audit_outbox_replays_missing_fill_once_after_process_failure(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    harness._log = lambda row: (_ for _ in ()).throw(OSError("disk temporarily unavailable"))
    with pytest.raises(OSError, match="disk temporarily unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                           mark_date=date(2026, 9, 29))
    restarted = loop(tmp_path, broker, submit=True)
    restarted.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                         mark_date=date(2026, 9, 30))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [row["order_status"] for row in rows] == ["prepared", "new", "filled", "no_change"]
    assert len({row["event_id"] for row in rows}) == 4
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_audit_outbox_deduplicates_crash_after_append(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    original_log = harness._log
    def fail_after_append(row):
        original_log(row)
        raise OSError("crash after append")
    harness._log = fail_after_append
    with pytest.raises(OSError, match="crash after append"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                           mark_date=date(2026, 9, 29))
    restarted = loop(tmp_path, broker, submit=True)
    restarted.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                         mark_date=date(2026, 9, 30))
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [row["order_status"] for row in rows] == ["prepared", "new", "filled", "no_change"]
    assert len({row["event_id"] for row in rows}) == 4


def _crash_during_intent_append(tmp_path, *, corrupt):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    ledger = tmp_path / "decisions.jsonl"

    def interrupted_append(row):
        complete = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
        ledger.write_bytes(corrupt(complete))
        raise OSError("interrupted ledger append")

    harness._log = interrupted_append
    with pytest.raises(OSError, match="interrupted ledger append"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert broker.submissions == []
    assert json.loads((tmp_path / "state.json").read_text())["outbox"]["event_type"] == "order_intent"
    return broker, ledger


@pytest.mark.parametrize("corrupt, error", [
    (lambda complete: complete[:-1], "no final newline"),
    (lambda complete: complete[:24], "no final newline"),
    (lambda complete: complete[:24] + b"\n", "invalid JSON"),
])
def test_interrupted_intent_ledger_tail_blocks_paper_order(tmp_path, corrupt, error):
    broker, ledger = _crash_during_intent_append(tmp_path, corrupt=corrupt)
    original = ledger.read_bytes()
    with pytest.raises(ValueError, match=error):
        loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert ledger.read_bytes() == original
    assert "outbox" in json.loads((tmp_path / "state.json").read_text())
    assert broker.submissions == []


def test_outbox_event_id_requires_exact_saved_row_and_unique_ledger_ids(tmp_path):
    def changed_payload(complete):
        row = json.loads(complete)
        row["qty"] += 1  # Same event ID cannot attest to a different order intent.
        return (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")

    broker, ledger = _crash_during_intent_append(tmp_path, corrupt=changed_payload)
    with pytest.raises(ValueError, match="conflicts with saved outbox"):
        loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert broker.submissions == []

    saved = json.loads((tmp_path / "state.json").read_text())["outbox"]
    exact = (json.dumps(saved, sort_keys=True) + "\n").encode("utf-8")
    ledger.write_bytes(exact + exact)
    with pytest.raises(ValueError, match="duplicate event_id"):
        loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert broker.submissions == []
    assert json.loads((tmp_path / "state.json").read_text())["outbox"] == saved


def test_outbox_match_does_not_skip_corrupt_rows_after_it(tmp_path):
    broker, ledger = _crash_during_intent_append(tmp_path, corrupt=lambda complete: complete)
    ledger.write_bytes(ledger.read_bytes() + b'{"event_id":"another"}')
    with pytest.raises(ValueError, match="no final newline"):
        loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))
    assert broker.submissions == []
    assert "outbox" in json.loads((tmp_path / "state.json").read_text())


def test_prior_ledger_row_without_newline_blocks_new_paper_intent(tmp_path):
    harness = loop(tmp_path)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(ledger.read_bytes()[:-1])
    original = ledger.read_bytes()
    broker = FakePaperGateway()
    with pytest.raises(ValueError, match="no final newline"):
        loop(tmp_path, broker, submit=True).run_ticker("AAPL", BUY_BARS,
                                                      now=DAY + timedelta(days=1))
    assert broker.submissions == []
    assert ledger.read_bytes() == original
    assert "AAPL" not in json.loads((tmp_path / "state.json").read_text())["tickers"]


def test_missing_ledger_with_saved_ticker_blocks_order_and_report(tmp_path):
    harness = loop(tmp_path)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    (tmp_path / "decisions.jsonl").unlink()
    with pytest.raises(ValueError, match="audit ledger is missing"):
        harness.report({"NVDA": 110.0})

    broker = FakePaperGateway()
    with pytest.raises(ValueError, match="audit ledger is missing"):
        loop(tmp_path, broker, submit=True).run_ticker("AAPL", BUY_BARS,
                                                      now=DAY + timedelta(days=1))
    assert broker.submissions == []
    assert not (tmp_path / "decisions.jsonl").exists()
    assert "AAPL" not in json.loads((tmp_path / "state.json").read_text())["tickers"]


def test_direct_report_rejects_corrupt_saved_ledger(tmp_path):
    harness = loop(tmp_path)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b'{"event_id":"partial"}')
    original = ledger.read_bytes()
    restarted = loop(tmp_path)
    with pytest.raises(ValueError, match="no final newline"):
        restarted.report({"NVDA": 110.0})
    assert ledger.read_bytes() == original


def test_intent_audit_failure_prevents_submission_and_blocks_next_day(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness._log = lambda row: (_ for _ in ()).throw(OSError("audit unavailable"))
    with pytest.raises(OSError, match="audit unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert broker.submissions == []
    assert json.loads((tmp_path / "state.json").read_text())["tickers"]["NVDA"]["intent"]["side"] == "BUY"

    restarted = loop(tmp_path, broker, submit=True)
    row = restarted.run_ticker("NVDA", SELL_BARS[:49], now=DAY + timedelta(days=1))
    assert row["order_status"] == "intent_unresolved"
    assert broker.submissions == []
    with pytest.raises(ValueError, match="unresolved paper order intent"):
        restarted.report({"NVDA": 90.0})
    rows = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert rows[0]["event_type"] == "order_intent"
    assert rows[0]["rule_version"] == "sma20_50_long_flat_v1"
    assert len(rows[0]["input_closes_sha256"]) == 64


def test_intent_state_checkpoint_failure_prevents_submission(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness._save = lambda: (_ for _ in ()).throw(OSError("cannot checkpoint intent"))
    with pytest.raises(OSError, match="cannot checkpoint intent"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert broker.submissions == []
    assert not (tmp_path / "state.json").exists()


def test_intent_directory_sync_failure_prevents_submission(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness._fsync_directory = lambda path: (_ for _ in ()).throw(OSError("directory sync failed"))
    with pytest.raises(OSError, match="directory sync failed"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert broker.submissions == []
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["tickers"]["NVDA"]["intent"]["side"] == "BUY"


def test_accepted_order_before_state_checkpoint_recovers_old_id_cross_day(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    original_save = harness._save

    def fail_after_broker_acceptance():
        item = harness.state["tickers"].get("NVDA", {})
        if item.get("pending") and not item.get("intent"):
            raise OSError("state disk unavailable")
        original_save()

    harness._save = fail_after_broker_acceptance
    with pytest.raises(OSError, match="state disk unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert broker.submissions == [("NVDA", "BUY", 1)]
    persisted = json.loads((tmp_path / "state.json").read_text())["tickers"]["NVDA"]
    assert persisted["intent"]["client_id"].endswith("20260929-NVDA-BUY")
    assert "pending" not in persisted

    restarted = loop(tmp_path, broker, submit=True)
    row = restarted.run_ticker("NVDA", SELL_BARS[:49], now=DAY + timedelta(days=1))
    assert row["event_type"] == "intent_recovery"
    assert row["order_id"] == "1" and row["order_status"] == "new"
    assert restarted.state["tickers"]["NVDA"]["pending"]["id"] == "1"
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_recovered_intent_withholds_old_price_and_cli_summary(tmp_path, monkeypatch, capsys):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    original_save = harness._save

    def fail_after_broker_acceptance():
        if harness.state["tickers"].get("NVDA", {}).get("pending"):
            raise OSError("checkpoint unavailable")
        original_save()

    harness._save = fail_after_broker_acceptance
    with pytest.raises(OSError, match="checkpoint unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    broker.completed_closes_with_dates = lambda ticker, now: (
        BUY_BARS[:-1] + [115.0], now.date() - timedelta(days=1))
    monkeypatch.setattr(paper_harness, "AlpacaPaperGateway", lambda: broker)
    monkeypatch.setattr(sys, "argv", ["paper_harness", "--submit-paper", "--tickers", "NVDA",
                                  "--state", str(tmp_path / "state.json"),
                                  "--ledger", str(tmp_path / "decisions.jsonl")])
    paper_harness.main()
    row, status = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert row["event_type"] == "intent_recovery"
    assert row["intent_signal_price"] == 110.0 and row["signal_price"] is None
    assert status == {"report_status": "withheld_intent_recovery_requires_fresh_mark"}
    assert broker.submissions == [("NVDA", "BUY", 1)]
    with pytest.raises(ValueError, match="unverified broker state"):
        loop(tmp_path, broker, submit=True).report({"NVDA": 115.0})


def test_recovered_order_fill_lookup_failure_suppresses_comparison(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    original_save = harness._save

    def fail_after_acceptance():
        if harness.state["tickers"].get("NVDA", {}).get("pending"):
            raise OSError("checkpoint unavailable")
        original_save()

    harness._save = fail_after_acceptance
    with pytest.raises(OSError, match="checkpoint unavailable"):
        harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    original_order = broker.order
    broker.order = lambda order_id: (_ for _ in ()).throw(RuntimeError("broker offline"))
    restarted = loop(tmp_path, broker, submit=True)
    row = restarted.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=1))
    assert row["order_status"] == "broker_error"
    with pytest.raises(ValueError, match="unverified broker state"):
        restarted.report({"NVDA": 110.0})
    broker.order = original_order
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    restarted.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                         mark_date=date(2026, 9, 30))
    assert len(broker.submissions) == 1
    assert restarted.report({"NVDA": 110.0})["strategy_pnl_usd"] == pytest.approx(-0.11)


def test_stale_comparison_survives_fill_reconciliation_until_position_verified(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    original_order = broker.order
    broker.order = lambda order_id: (_ for _ in ()).throw(OSError("broker offline"))
    assert harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1))[
        "comparison_valid"] is False
    broker.order = original_order
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 3.0  # External broker activity invalidates local cost basis.
    without_bars = harness.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=2))
    assert without_bars["comparison_valid"] is False
    still_without_bars = harness.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=3))
    assert still_without_bars["comparison_valid"] is False
    with pytest.raises(ValueError, match="unverified broker state"):
        harness.report({"NVDA": 110.0})
    with_bars = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=4),
                                   mark_date=date(2026, 10, 2))
    assert with_bars["order_status"] == "position_mismatch"
    assert with_bars["comparison_valid"] is False
    with pytest.raises(ValueError, match="broker position mismatch"):
        harness.report({"NVDA": 110.0})
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_uncertain_submission_stays_blocked_until_old_id_is_found(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    original_submit = broker.submit_market

    def submit_then_timeout(*args):
        original_submit(*args)
        raise TimeoutError("response lost")

    broker.submit_market = submit_then_timeout
    row = harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert row["order_status"] == "submission_unconfirmed"
    assert len(broker.submissions) == 1

    restarted = loop(tmp_path, broker, submit=True)
    broker.by_client_id = lambda client_id: None
    row = restarted.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=1))
    assert row["order_status"] == "intent_unresolved"
    assert len(broker.submissions) == 1
    broker.by_client_id = lambda client_id: broker.orders[broker.ids[client_id]]
    row = restarted.run_ticker("NVDA", SELL_BARS[:49], now=DAY + timedelta(days=2))
    assert row["order_id"] == "1"
    assert len(broker.submissions) == 1


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
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", [100.0] * 49, now=DAY, mark_date=date(2026, 9, 28))
    assert row["order_status"] == "insufficient_completed_bars"
    broker.position_qty = lambda ticker: (_ for _ in ()).throw(RuntimeError("offline"))
    row = loop(tmp_path, broker, submit=True).run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    assert row["order_status"] == "broker_error"
    assert row["error_type"] == "RuntimeError"
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 2


def test_current_session_daily_bar_is_never_used():
    bars = [SimpleNamespace(timestamp=datetime(2026, 9, day, tzinfo=timezone.utc), close=day)
            for day in (28, 29)]
    assert _completed_daily_closes(bars, DAY) == [28.0]


def test_gateway_pairs_completed_bar_close_with_its_session_date():
    bars = [SimpleNamespace(timestamp=datetime(2026, 9, day, tzinfo=timezone.utc), close=float(day))
            for day in (29, 27, 28)]
    gateway = object.__new__(AlpacaPaperGateway)
    gateway.data = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data={"NVDA": bars}))
    closes, mark_date = gateway.completed_closes_with_dates("NVDA", DAY)
    assert closes == [27.0, 28.0]
    assert mark_date == date(2026, 9, 28)


def test_gateway_reads_only_prior_scheduled_paper_sessions():
    gateway = object.__new__(AlpacaPaperGateway)
    requests = []
    gateway.client = SimpleNamespace(get_calendar=lambda filters: (
        requests.append(filters) or [SimpleNamespace(date=date(2026, 9, 4))]))
    now = datetime(2026, 9, 8, 14, tzinfo=timezone.utc)  # Day after Labor Day.
    assert gateway.last_completed_session(now) == date(2026, 9, 4)
    assert requests[0].start == date(2026, 8, 25)
    assert requests[0].end == date(2026, 9, 7)


def test_paper_requires_dated_recent_bar_but_dry_run_can_explore_without_it(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    missing = harness.run_ticker("NVDA", BUY_BARS, now=DAY)
    assert missing["order_status"] == "missing_completed_bar_date"
    assert missing["comparison_valid"] is False
    assert broker.submissions == []
    assert harness.state["tickers"] == {}  # Do not set a stale benchmark.
    with pytest.raises(ValueError, match="Missing or stale paper bar"):
        harness.report({})
    assert loop(tmp_path / "dry").run_ticker("NVDA", BUY_BARS, now=DAY)["order_status"] == "dry_run"


def test_monday_rejects_thursday_bar_but_accepts_friday(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    monday = DAY + timedelta(days=6)  # 2026-10-05, previous session Friday.
    stale = harness.run_ticker("NVDA", BUY_BARS, now=monday, mark_date=date(2026, 10, 1))
    assert stale["order_status"] == "stale_completed_bar"
    assert stale["expected_last_session"] == "2026-10-02"
    assert broker.submissions == []
    assert harness.state["tickers"] == {}
    with pytest.raises(ValueError, match="Missing or stale paper bar"):
        loop(tmp_path, broker, submit=True).report({})
    fresh = harness.run_ticker("NVDA", BUY_BARS, now=monday,
                               mark_date=date(2026, 10, 2))
    assert fresh["order_status"] == "filled"
    assert broker.submissions == [("NVDA", "BUY", 1)]
    assert harness.report({"NVDA": 110.0})["strategy_pnl_usd"] == pytest.approx(-0.11)


def test_holiday_uses_actual_calendar_not_weekday_or_age_guess(tmp_path):
    broker = FakePaperGateway()
    broker.calendar_dates = [date(2026, 9, 3), date(2026, 9, 4)]
    harness = loop(tmp_path, broker, submit=True)
    tuesday = datetime(2026, 9, 8, 14, tzinfo=timezone.utc)
    stale = harness.run_ticker("NVDA", BUY_BARS, now=tuesday,
                               mark_date=date(2026, 9, 3))
    assert stale["order_status"] == "stale_completed_bar"
    assert broker.submissions == []
    current = harness.run_ticker("NVDA", BUY_BARS, now=tuesday,
                                 mark_date=date(2026, 9, 4))
    assert current["order_status"] == "filled"
    assert broker.submissions == [("NVDA", "BUY", 1)]


def test_calendar_failure_and_empty_calendar_block_paper_submission(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    broker.last_completed_session = lambda now: (_ for _ in ()).throw(ConnectionError("offline"))
    failed = harness.run_ticker("NVDA", BUY_BARS, now=DAY,
                                mark_date=date(2026, 9, 28))
    assert failed["order_status"] == "paper_calendar_unavailable"
    assert failed["error_type"] == "ConnectionError"
    broker.last_completed_session = lambda now: None
    empty = harness.run_ticker("NVDA", BUY_BARS, now=DAY,
                               mark_date=date(2026, 9, 28))
    assert empty["order_status"] == "paper_calendar_unavailable"
    assert broker.submissions == []
    assert harness.state["tickers"] == {}


def test_stale_bar_reconciles_fill_but_withholds_comparison_until_fresh(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    stale = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=1),
                               mark_date=date(2026, 9, 28))
    assert stale["order_status"] == "filled" and stale["filled_qty"] == 1
    assert stale["data_status"] == "stale_completed_bar"
    assert stale["signal_price"] is None and stale["comparison_valid"] is False
    assert broker.submissions == [("NVDA", "BUY", 1)]
    with pytest.raises(ValueError, match="unverified broker state"):
        harness.report({"NVDA": 110.0})
    fresh = harness.run_ticker("NVDA", BUY_BARS, now=DAY + timedelta(days=2),
                               mark_date=date(2026, 9, 30))
    assert fresh["comparison_valid"] is True
    assert harness.report({"NVDA": 110.0})["strategy_pnl_usd"] == pytest.approx(-0.11)


def test_incomplete_today_bar_does_not_prevent_pending_fill_reconciliation(tmp_path):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0
    row = harness.run_ticker("NVDA", SELL_BARS, now=DAY + timedelta(days=1),
                             mark_date=date(2026, 9, 30))  # The current day is incomplete.
    assert row["order_status"] == "filled" and row["filled_qty"] == 1
    assert row["data_status"] == "incomplete_completed_bar"
    assert broker.submissions == [("NVDA", "BUY", 1)]
    with pytest.raises(ValueError, match="unverified broker state"):
        harness.report({"NVDA": 90.0})


def test_missing_bars_withhold_existing_paper_comparison(tmp_path):
    broker = FakePaperGateway()
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    missing = harness.run_ticker("NVDA", BUY_BARS[:49], now=DAY + timedelta(days=1))
    assert missing["order_status"] == "insufficient_completed_bars"
    assert missing["data_status"] == "insufficient_completed_bars"
    assert missing["comparison_valid"] is False
    with pytest.raises(ValueError, match="unverified broker state"):
        harness.report({"NVDA": 110.0})


def test_cli_withholds_aggregate_after_stale_bar(tmp_path, monkeypatch, capsys):
    broker = FakePaperGateway()
    broker.completed_closes_with_dates = lambda ticker, now: (BUY_BARS, date(2026, 10, 1))
    monday = DAY + timedelta(days=6)
    monkeypatch.setattr(paper_harness, "datetime", SimpleNamespace(
        now=lambda tz: monday, fromisoformat=datetime.fromisoformat))
    monkeypatch.setattr(paper_harness, "AlpacaPaperGateway", lambda: broker)
    monkeypatch.setattr(sys, "argv", ["paper_harness", "--submit-paper", "--tickers", "NVDA",
                                  "--state", str(tmp_path / "state.json"),
                                  "--ledger", str(tmp_path / "decisions.jsonl")])
    paper_harness.main()
    row, status = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert row["order_status"] == "stale_completed_bar"
    assert status == {"report_status": "withheld_missing_or_stale_paper_bar"}
    assert broker.submissions == []


def test_cli_withholds_aggregate_after_insufficient_bars(tmp_path, monkeypatch, capsys):
    broker = FakePaperGateway()
    broker.completed_closes_with_dates = lambda ticker, now: ([110.0] * 49, None)
    monkeypatch.setattr(paper_harness, "AlpacaPaperGateway", lambda: broker)
    monkeypatch.setattr(sys, "argv", ["paper_harness", "--submit-paper", "--tickers", "NVDA",
                                  "--state", str(tmp_path / "state.json"),
                                  "--ledger", str(tmp_path / "decisions.jsonl")])
    paper_harness.main()
    row, status = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert row["data_status"] == "insufficient_completed_bars"
    assert status == {"report_status": "withheld_missing_or_stale_paper_bar"}
    assert broker.submissions == []


def test_cli_records_data_fetch_failure_and_still_reconciles_pending_fill(
        tmp_path, monkeypatch, capsys):
    broker = FakePaperGateway(immediate=False)
    harness = loop(tmp_path, broker, submit=True)
    harness.run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 28))
    broker.orders["1"].update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.positions["NVDA"] = 1.0

    def unavailable(ticker, now):
        raise RuntimeError("private feed message must never enter audit ledger")

    broker.completed_closes_with_dates = unavailable
    monkeypatch.setattr(paper_harness, "AlpacaPaperGateway", lambda: broker)
    monkeypatch.setattr(sys, "argv", ["paper_harness", "--submit-paper", "--tickers", "NVDA",
                                  "--state", str(tmp_path / "state.json"),
                                  "--ledger", str(tmp_path / "decisions.jsonl")])
    paper_harness.main()
    row, status = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert row["data_status"] == "paper_market_data_unavailable"
    assert row["data_fetch_error_type"] == "RuntimeError"
    assert row["order_status"] == "filled" and row["filled_qty"] == 1
    assert row["comparison_valid"] is False
    assert status == {"report_status": "withheld_missing_or_stale_paper_bar"}
    assert broker.submissions == [("NVDA", "BUY", 1)]
    assert row == json.loads((tmp_path / "decisions.jsonl").read_text().splitlines()[-1])
    assert "private feed message" not in (tmp_path / "decisions.jsonl").read_text()
    with pytest.raises(ValueError, match="unverified broker state"):
        loop(tmp_path, broker, submit=True).report({"NVDA": 110.0})


def test_cli_data_error_does_not_leak_into_next_ticker(tmp_path, monkeypatch, capsys):
    broker = FakePaperGateway()
    monday = DAY + timedelta(days=6)

    def feed(ticker, now):
        if ticker == "NVDA":
            raise ConnectionError("private")
        return BUY_BARS, date(2026, 10, 2)

    broker.completed_closes_with_dates = feed
    monkeypatch.setattr(paper_harness, "datetime", SimpleNamespace(
        now=lambda tz: monday, fromisoformat=datetime.fromisoformat))
    monkeypatch.setattr(paper_harness, "AlpacaPaperGateway", lambda: broker)
    monkeypatch.setattr(sys, "argv", ["paper_harness", "--submit-paper", "--tickers", "NVDA,AAPL",
                                  "--state", str(tmp_path / "state.json"),
                                  "--ledger", str(tmp_path / "decisions.jsonl")])
    paper_harness.main()
    failed, healthy, status = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert failed["order_status"] == "paper_market_data_unavailable"
    assert failed["data_fetch_error_type"] == "ConnectionError"
    assert healthy["order_status"] == "filled" and "data_fetch_error_type" not in healthy
    assert broker.submissions == [("AAPL", "BUY", 1)]
    assert status == {"report_status": "withheld_missing_or_stale_paper_bar"}


def test_same_session_mark_date_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="completed earlier session"):
        loop(tmp_path).run_ticker("NVDA", BUY_BARS, now=DAY, mark_date=date(2026, 9, 29))


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
