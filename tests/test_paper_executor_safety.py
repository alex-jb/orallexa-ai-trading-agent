"""Malformed actions cannot be turned into Alpaca paper short orders."""

from types import SimpleNamespace

import pytest

pytest.importorskip("alpaca.trading")
from alpaca.trading.enums import OrderSide

from bot.alpaca_executor import AlpacaExecutor


class FakePaperClient:
    def __init__(self):
        self.submitted = []
        self.account_reads = 0

    def get_account(self):
        self.account_reads += 1
        return SimpleNamespace(portfolio_value="10000")

    def submit_order(self, order):
        self.submitted.append(order)
        return SimpleNamespace(id="synthetic-paper-order")


def _executor(monkeypatch, client):
    monkeypatch.setattr(AlpacaExecutor, "_make_client", lambda self: client)
    monkeypatch.setattr(AlpacaExecutor, "_sync_to_paper_trader", lambda self, order: None)
    return AlpacaExecutor()


@pytest.mark.parametrize("decision", ["HOLD", "BUY ", "sell", "", "SELLL"])
def test_unknown_decision_never_reaches_broker(monkeypatch, decision):
    client = FakePaperClient()
    result = _executor(monkeypatch, client).execute_signal("NVDA", decision, confidence=80, entry_price=100)
    assert result["error"].startswith("Unsupported decision")
    assert client.account_reads == 0
    assert client.submitted == []


def test_valid_sell_keeps_existing_paper_short_semantics(monkeypatch):
    client = FakePaperClient()
    result = _executor(monkeypatch, client).execute_signal("NVDA", "SELL", confidence=80, entry_price=100)
    assert result["status"] == "submitted"
    assert len(client.submitted) == 1
    assert client.submitted[0].side == OrderSide.SELL
