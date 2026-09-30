"""Broker-backed paper PM gate: synthetic clients, no network or order submission."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api_server
from bot.alpaca_executor import AlpacaExecutor


class FakePaperClient:
    def __init__(self, *, equity="10000", positions=(), account_error=False,
                 positions_error=False, orders=(), orders_error=False,
                 orders_unavailable=False, advertise_submitted=False):
        self.equity = equity
        self.positions = positions
        self.account_error = account_error
        self.positions_error = positions_error
        self.account_reads = 0
        self.position_reads = 0
        self.order_reads = 0
        self.orders = orders
        self.orders_error = orders_error
        self.orders_unavailable = orders_unavailable
        self.advertise_submitted = advertise_submitted
        self.submitted = []

    def get_account(self):
        self.account_reads += 1
        if self.account_error:
            raise RuntimeError("Synthetic account failure")
        return SimpleNamespace(equity=self.equity, portfolio_value=self.equity)

    def get_all_positions(self):
        self.position_reads += 1
        if self.positions_error:
            raise RuntimeError("Synthetic position failure")
        return self.positions

    def get_orders(self, request):
        from alpaca.trading.enums import QueryOrderStatus

        self.order_reads += 1
        assert request.status == QueryOrderStatus.OPEN
        assert request.symbols == ["NVDA"]
        assert request.limit == 1
        assert request.nested is False
        if self.orders_error:
            raise RuntimeError("Synthetic open-order failure")
        if self.orders_unavailable:
            return None
        return [o for o in self.orders if o.symbol == "NVDA"] + (
            [SimpleNamespace(symbol="NVDA") for _ in self.submitted]
            if self.advertise_submitted else []
        )

    def submit_order(self, order):
        self.submitted.append(order)
        return SimpleNamespace(id="synthetic-paper-order")


def _position(ticker, market_value):
    return SimpleNamespace(symbol=ticker, market_value=market_value)


@pytest.fixture
def request_paper(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    # Master reads this at import; PR #13 reads the environment per request.
    if hasattr(api_server, "_API_KEY"):
        monkeypatch.setattr(api_server, "_API_KEY", "paper-test-secret")

    def request(broker, data, *, pm=None):
        monkeypatch.setattr(AlpacaExecutor, "_make_client", lambda self: broker)
        monkeypatch.setattr(AlpacaExecutor, "_get_sizing_price", lambda self, ticker, side: 100.0)
        monkeypatch.setattr(AlpacaExecutor, "_sync_to_paper_trader", lambda self, order: None)
        if pm is not None:
            monkeypatch.setattr("engine.portfolio_manager.approve_decision", pm)
        with TestClient(api_server.app) as client:
            response = client.post("/api/alpaca/execute", data=data,
                                   headers={"X-API-Key": "paper-test-secret"})
        return response

    return request


def _form(**changes):
    return {"ticker": "NVDA", "decision": "BUY", "confidence": "80",
            "entry_price": "100", "position_pct": "10", **changes}


def test_ui_style_omission_uses_paper_positions_and_scales_order(request_paper):
    broker = FakePaperClient(positions=[_position("NVDA", "1500")])
    response = request_paper(broker, _form())
    assert response.status_code == 200
    verdict = response.json()["portfolio_manager"]
    assert verdict["checks"]["existing_position_pct"] == 15.0
    assert response.json()["qty"] == 5
    # The executor re-reads account value for its existing sizing behavior.
    assert broker.account_reads == 2
    assert broker.position_reads == 1
    assert len(broker.submitted) == 1


def test_caller_price_cannot_inflate_paper_market_order(request_paper):
    broker = FakePaperClient()
    response = request_paper(broker, _form(entry_price="0.01", position_pct="5"))
    assert response.status_code == 200
    assert response.json()["qty"] == 5
    assert response.json()["entry_price"] == 100.0
    assert len(broker.submitted) == 1
    assert broker.submitted[0].qty == 5


def test_sizing_quote_is_side_specific_and_recent(monkeypatch):
    from alpaca.data import historical

    seen = []
    quote = SimpleNamespace(timestamp=datetime.now(timezone.utc),
                            ask_price=101.0, bid_price=99.0)

    class FakeDataClient:
        def __init__(self, key, secret):
            seen.append((key, secret))

        def get_stock_latest_quote(self, request):
            assert request.symbol_or_symbols == "NVDA"
            return {"NVDA": quote}

    monkeypatch.setenv("ALPACA_API_KEY", "synthetic-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "synthetic-secret")
    monkeypatch.setattr(historical, "StockHistoricalDataClient", FakeDataClient)
    executor = object.__new__(AlpacaExecutor)
    assert executor._get_sizing_price("NVDA", "BUY") == 101.0
    assert executor._get_sizing_price("NVDA", "SELL") == 99.0
    assert len(seen) == 2

    quote.timestamp = datetime.now(timezone.utc) - timedelta(minutes=3)
    with pytest.raises(ValueError, match="stale"):
        executor._get_sizing_price("NVDA", "BUY")

    quote.timestamp = datetime.now(timezone.utc)
    quote.bid_price = float("nan")
    with pytest.raises(ValueError, match="valid"):
        executor._get_sizing_price("NVDA", "SELL")


def test_spoofed_caller_portfolio_cannot_bypass_real_concentration(request_paper):
    broker = FakePaperClient(positions=[_position("NVDA", "3000")])
    response = request_paper(broker, _form(
        portfolio_json='[{"ticker":"NVDA","value_usd":1}]',
        portfolio_value="1000000",
    ))
    assert response.status_code == 409
    assert response.json()["status"] == "blocked"
    assert response.json()["error"]
    assert response.json()["portfolio_manager"]["checks"]["existing_position_pct"] == 30.0
    assert broker.submitted == []


@pytest.mark.parametrize("broker", [
    FakePaperClient(account_error=True), FakePaperClient(positions_error=True),
    FakePaperClient(equity="nan"), FakePaperClient(positions=None),
    FakePaperClient(positions=[_position("NVDA", "nan")]),
])
def test_missing_or_invalid_broker_snapshot_blocks_order(request_paper, broker):
    response = request_paper(broker, _form())
    assert response.status_code == 503
    assert response.json()["status"] == "blocked"
    assert response.json()["error"]
    assert response.json()["reason"] == "paper_portfolio_manager_unavailable"
    assert broker.submitted == []


@pytest.mark.parametrize("order", [
    SimpleNamespace(symbol="NVDA", side="buy"),
    SimpleNamespace(symbol="NVDA", side="sell", order_class="bracket"),
])
def test_open_order_or_bracket_exit_blocks_same_symbol(request_paper, order):
    broker = FakePaperClient(orders=[order])
    response = request_paper(broker, _form())
    assert response.status_code == 409
    assert response.json()["reason"] == "paper_open_order_exists"
    assert broker.submitted == []


@pytest.mark.parametrize("broker", [
    FakePaperClient(orders_error=True), FakePaperClient(orders_unavailable=True),
])
def test_unavailable_open_order_query_blocks(request_paper, broker):
    response = request_paper(broker, _form())
    assert response.status_code == 503
    assert response.json()["reason"] == "paper_portfolio_manager_unavailable"
    assert broker.submitted == []


def test_malformed_open_order_response_blocks(request_paper):
    broker = FakePaperClient()
    broker.get_orders = lambda request: {}
    response = request_paper(broker, _form())
    assert response.status_code == 503
    assert broker.submitted == []


def test_other_symbol_open_order_does_not_block_target(request_paper):
    broker = FakePaperClient(orders=[SimpleNamespace(symbol="AAPL")])
    response = request_paper(broker, _form())
    assert response.status_code == 200
    assert broker.order_reads == 1
    assert len(broker.submitted) == 1


def test_concurrent_requests_recheck_open_orders_after_first_submit(monkeypatch):
    broker = FakePaperClient(advertise_submitted=True)
    entered_submit = Event()
    release_submit = Event()
    original_submit = broker.submit_order

    def delayed_submit(order):
        entered_submit.set()
        assert release_submit.wait(timeout=5)
        return original_submit(order)

    broker.submit_order = delayed_submit
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    monkeypatch.setattr(AlpacaExecutor, "_make_client", lambda self: broker)
    monkeypatch.setattr(AlpacaExecutor, "_get_sizing_price", lambda self, ticker, side: 100.0)
    monkeypatch.setattr(AlpacaExecutor, "_sync_to_paper_trader", lambda self, order: None)

    with TestClient(api_server.app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        send = lambda: client.post("/api/alpaca/execute", data=_form(),
                                   headers={"X-API-Key": "paper-test-secret"})
        first = pool.submit(send)
        assert entered_submit.wait(timeout=5)
        second = pool.submit(send)
        try:
            # The second request has no opportunity to check stale positions
            # until the first leaves the critical section.
            assert not second.done()
        finally:
            release_submit.set()
        responses = [first.result(timeout=5), second.result(timeout=5)]
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert broker.order_reads == 2
    assert len(broker.submitted) == 1


def test_pm_exception_blocks_order(request_paper):
    broker = FakePaperClient()

    def broken_pm(**kwargs):
        raise RuntimeError("Synthetic PM failure")

    response = request_paper(broker, _form(), pm=broken_pm)
    assert response.status_code == 503
    assert broker.submitted == []


def test_pm_zero_sizing_is_not_replaced_with_requested_size(request_paper):
    broker = FakePaperClient()
    response = request_paper(broker, _form(), pm=lambda **kwargs: {
        "approved": True, "scaled_position_pct": 0.0,
    })
    assert response.status_code == 409
    assert response.json()["reason"] == "portfolio_manager_zero_size"
    assert broker.submitted == []


def test_overweight_long_sell_with_zero_pm_size_cannot_submit(request_paper):
    broker = FakePaperClient(positions=[_position("NVDA", "3000")])
    response = request_paper(broker, _form(decision="SELL"))
    assert response.status_code == 409
    assert response.json()["reason"] == "portfolio_manager_zero_size"
    assert response.json()["portfolio_manager"]["approved"] is True
    assert response.json()["portfolio_manager"]["scaled_position_pct"] == 0
    assert broker.submitted == []


def test_skip_pm_is_disabled_before_broker_access(request_paper):
    broker = FakePaperClient()
    response = request_paper(broker, _form(skip_pm="true"))
    assert response.status_code == 403
    assert broker.account_reads == 0
    assert broker.submitted == []


def test_invalid_decision_blocks_before_broker_access(request_paper):
    broker = FakePaperClient()
    response = request_paper(broker, _form(decision="HOLD"))
    assert response.status_code == 422
    assert broker.account_reads == 0
    assert broker.submitted == []


def test_approved_sell_keeps_paper_short_behavior(request_paper):
    from alpaca.trading.enums import OrderSide

    broker = FakePaperClient()
    response = request_paper(broker, _form(decision="SELL"))
    assert response.status_code == 200
    assert broker.submitted[0].side == OrderSide.SELL
