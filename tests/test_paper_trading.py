"""Tests for bot/paper_trading.py — PaperTrader journal logic."""
import pytest
from pathlib import Path
from bot.paper_trading import PaperTrader, PaperTrade


def _make_trade(ticker="NVDA", direction="LONG", entry=100.0, sl=95.0, tp=110.0):
    return PaperTrade(
        timestamp="2026-04-02T10:00:00", ticker=ticker, direction=direction,
        entry_price=entry, stop_loss=sl, take_profit=tp,
        confidence=75.0, source="test", position_size=1000.0,
    )


@pytest.fixture
def trader(tmp_path):
    return PaperTrader(tmp_path / "trades.json")


class TestPaperTrader:
    def test_open_trade(self, trader):
        idx = trader.open_trade(_make_trade())
        assert idx == 0
        assert len(trader.get_open_trades()) == 1

    def test_close_trade_win(self, trader):
        trader.open_trade(_make_trade(entry=100.0))
        result = trader.close_trade(0, 110.0)
        assert result is not None
        assert result["status"] == "WIN"
        assert result["pnl_pct"] == 10.0

    def test_close_trade_loss(self, trader):
        trader.open_trade(_make_trade(entry=100.0))
        result = trader.close_trade(0, 90.0)
        assert result is not None
        assert result["status"] == "LOSS"
        assert result["pnl_pct"] == -10.0

    def test_close_invalid_index(self, trader):
        assert trader.close_trade(99, 100.0) is None

    def test_close_already_closed(self, trader):
        trader.open_trade(_make_trade())
        trader.close_trade(0, 110.0)
        assert trader.close_trade(0, 120.0) is None

    def test_get_stats_empty(self, trader):
        stats = trader.get_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_get_stats_with_trades(self, trader):
        trader.open_trade(_make_trade("NVDA", entry=100.0))
        trader.close_trade(0, 110.0)
        trader.open_trade(_make_trade("AAPL", entry=200.0))
        trader.close_trade(1, 190.0)
        stats = trader.get_stats()
        assert stats["total_trades"] == 2
        assert stats["wins"] == 1
        assert stats["losses"] == 1
        assert stats["win_rate"] == 50.0

    def test_profit_factor(self, trader):
        trader.open_trade(_make_trade("A", entry=100.0))
        trader.close_trade(0, 120.0)  # +20%
        trader.open_trade(_make_trade("B", entry=100.0))
        trader.close_trade(1, 95.0)   # -5%
        stats = trader.get_stats()
        assert stats["profit_factor"] == 4.0  # 20/5

    def test_persistence(self, tmp_path):
        path = tmp_path / "trades.json"
        t1 = PaperTrader(path)
        t1.open_trade(_make_trade())
        t1.close_trade(0, 110.0)
        t2 = PaperTrader(path)
        assert t2.get_stats()["total_trades"] == 1

    def test_short_trade_pnl(self, trader):
        trader.open_trade(_make_trade(direction="SHORT", entry=100.0))
        result = trader.close_trade(0, 90.0)
        assert result["pnl_pct"] > 0  # Short wins when price drops
        assert result["status"] == "WIN"

    def test_open_and_closed_separation(self, trader):
        trader.open_trade(_make_trade("NVDA"))
        trader.open_trade(_make_trade("AAPL"))
        trader.close_trade(0, 110.0)
        assert len(trader.get_open_trades()) == 1
        assert len(trader.get_closed_trades()) == 1
        assert len(trader.get_all_trades()) == 2
