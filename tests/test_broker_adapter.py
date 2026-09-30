"""Paper broker contract, Alpaca bracket compatibility, and Robinhood isolation."""
from types import SimpleNamespace

import pytest

from bot.broker_adapter import BrokerAdapter, create_broker_adapter


def test_factory_rejects_live_or_unknown_brokers():
    for broker in ("robinhood", "robinhood_live", "alpaca_live", "", "ALPACA"):
        with pytest.raises(ValueError, match="Unsupported paper broker"):
            create_broker_adapter(broker)


def test_robinhood_is_offline_preview_even_when_keys_are_set(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_API_KEY", "unused-test-value")
    monkeypatch.setenv("ALPACA_API_KEY", "unused-test-value")
    adapter = create_broker_adapter("robinhood_dry_run")
    assert isinstance(adapter, BrokerAdapter)
    assert not adapter.connected
    assert adapter.get_account() is None
    assert adapter.get_positions() == []
    assert adapter.get_recent_orders() == []
    preview = adapter.execute_signal(
        "NVDA", "BUY", confidence=80, entry_price=100,
        stop_loss=90, take_profit=120, position_pct=5,
    )
    assert preview["status"] == "dry_run"
    assert preview["order_submitted"] is False
    assert preview["bracket_supported"] is False
    assert preview["stop_loss"] == 90
    assert preview["take_profit"] == 120
    assert adapter.close_position("NVDA")["order_submitted"] is False
    assert adapter.close_all()["order_submitted"] is False


def test_alpaca_factory_forces_paper_client(monkeypatch):
    from alpaca.trading import client as client_module

    created = []

    class FakeClient:
        def __init__(self, key, secret, paper):
            created.append((key, secret, paper))

    monkeypatch.setenv("ALPACA_API_KEY", "test-paper-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-paper-secret")
    monkeypatch.setattr(client_module, "TradingClient", FakeClient)
    adapter = create_broker_adapter("alpaca")
    assert isinstance(adapter, BrokerAdapter)
    assert adapter.connected
    assert created == [("test-paper-key", "test-paper-secret", True)]


def test_alpaca_bracket_order_behavior_unchanged(monkeypatch):
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from bot.alpaca_executor import AlpacaExecutor

    submitted = []

    class FakeClient:
        def get_account(self):
            return SimpleNamespace(portfolio_value="10000")

        def submit_order(self, order):
            submitted.append(order)
            return SimpleNamespace(id="paper-order-1")

    monkeypatch.setattr(AlpacaExecutor, "_make_client", lambda self: FakeClient())
    # A later paper PM gate may require a fresh quote for market-order sizing.
    monkeypatch.setattr(AlpacaExecutor, "_get_sizing_price", lambda self, ticker, side: 100.0, raising=False)
    monkeypatch.setattr(AlpacaExecutor, "_sync_to_paper_trader", lambda self, result: None)
    result = create_broker_adapter("alpaca").execute_signal(
        "NVDA", "BUY", confidence=80, entry_price=100,
        stop_loss=90.001, take_profit=120.001, position_pct=5,
    )
    assert result["status"] == "submitted"
    assert result["order_id"] == "paper-order-1"
    assert result["qty"] == 5
    assert len(submitted) == 1
    order = submitted[0]
    assert order.symbol == "NVDA"
    assert order.qty == 5
    assert order.side == OrderSide.BUY
    assert order.time_in_force == TimeInForce.DAY
    assert order.order_class == OrderClass.BRACKET
    assert float(order.take_profit.limit_price) == pytest.approx(120.0)
    assert float(order.stop_loss.stop_price) == pytest.approx(90.0)
