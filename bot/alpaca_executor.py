"""
bot/alpaca_executor.py
──────────────────────────────────────────────────────────────────
Alpaca Paper Trading integration — executes signals as real paper orders.

Connects Orallexa's DecisionOutput to Alpaca's paper trading API.
All trades are paper (simulated) — no real money involved.

Setup:
    1. Create free account at https://app.alpaca.markets
    2. Generate API keys (paper trading)
    3. Add to .env:
       ALPACA_API_KEY=...
       ALPACA_SECRET_KEY=...

Usage:
    from bot.alpaca_executor import AlpacaExecutor
    executor = AlpacaExecutor()
    result = executor.execute_signal(decision_output, ticker="NVDA")
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Optional

from core.logger import get_logger

logger = get_logger("alpaca")

# Alpaca paper trading base URL
PAPER_BASE_URL = "https://paper-api.alpaca.markets"


class AlpacaExecutor:
    """
    Execute trading signals via Alpaca paper trading API.

    Features:
    - Market and limit orders
    - Position sizing from investment plan
    - Automatic bracket orders (stop-loss + take-profit)
    - Position monitoring and auto-close
    - Trade journal sync with PaperTrader
    """

    def __init__(self) -> None:
        self._client = self._make_client()

    def _make_client(self):
        """Create Alpaca TradingClient. Returns None if keys not set."""
        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret_key = os.environ.get("ALPACA_SECRET_KEY", "")

        if not api_key or not secret_key:
            logger.warning("ALPACA_API_KEY or ALPACA_SECRET_KEY not set — paper trading disabled")
            return None

        try:
            from alpaca.trading.client import TradingClient
            client = TradingClient(api_key, secret_key, paper=True)
            logger.info("Alpaca paper trading connected")
            return client
        except ImportError:
            logger.warning("alpaca-py not installed — run: pip install alpaca-py")
            return None
        except Exception as e:
            logger.warning("Alpaca connection failed: %s", e)
            return None

    @property
    def connected(self) -> bool:
        return self._client is not None

    def get_account(self) -> Optional[dict]:
        """Get paper trading account info."""
        if not self._client:
            return None
        try:
            account = self._client.get_account()
            return {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "day_trade_count": int(account.daytrade_count),
                "status": account.status,
            }
        except Exception as e:
            logger.warning("Failed to get account: %s", e)
            return None

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        if not self._client:
            return []
        try:
            positions = self._client.get_all_positions()
            return [{
                "ticker": p.symbol,
                "qty": float(p.qty),
                "side": p.side,
                "entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
            } for p in positions]
        except Exception as e:
            logger.warning("Failed to get positions: %s", e)
            return []

    def get_risk_snapshot(self) -> dict:
        """Fetch a strict PAPER account snapshot for the pre-order risk gate.

        Unlike the dashboard helpers, failures must propagate: an empty list
        is a valid portfolio, but a failed position query is not.
        """
        if self._client is None:
            raise RuntimeError("Alpaca PAPER account is not connected")
        account = self._client.get_account()
        equity = float(account.equity)
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("Invalid Alpaca PAPER account equity")
        raw_positions = self._client.get_all_positions()
        if raw_positions is None:
            raise ValueError("Alpaca PAPER positions are unavailable")
        positions = []
        for position in raw_positions:
            symbol = str(position.symbol).strip().upper()
            value = float(position.market_value)
            if not symbol or symbol == "NONE" or not math.isfinite(value):
                raise ValueError("Invalid Alpaca PAPER position")
            # Market value of a short can be negative; count gross exposure.
            positions.append({"ticker": symbol, "value_usd": abs(value)})
        return {"portfolio_value": equity, "positions": positions}

    def has_open_order(self, ticker: str) -> bool:
        """Check for an unsettled PAPER order on this symbol, failing closed.

        Query each leg separately: an exit leg of a filled bracket order is
        still an active order and must prevent another order on the symbol.
        """
        if self._client is None:
            raise RuntimeError("Alpaca PAPER account is not connected")
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        orders = self._client.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.OPEN, symbols=[ticker], limit=1, nested=False,
        ))
        if not isinstance(orders, list):
            raise ValueError("Alpaca PAPER open orders are unavailable")
        return bool(orders)

    def _get_sizing_price(self, ticker: str, decision: str) -> float:
        """Use a recent market-data quote, never a caller's signal price, for sizing.

        The submitted order is a market order. A quote can bound the *estimated*
        allocation, but it cannot guarantee its eventual fill notional.
        """
        from alpaca.data.requests import StockLatestQuoteRequest
        from alpaca.data.historical import StockHistoricalDataClient

        data_client = StockHistoricalDataClient(
            os.environ.get("ALPACA_API_KEY", ""), os.environ.get("ALPACA_SECRET_KEY", ""),
        )
        quotes = data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=ticker)
        )
        quote = quotes.get(ticker) if isinstance(quotes, dict) else None
        stamp = getattr(quote, "timestamp", None)
        if not isinstance(stamp, datetime) or stamp.tzinfo is None:
            raise ValueError("Alpaca quote timestamp is unavailable")
        age_seconds = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        if age_seconds < -5 or age_seconds > 120:
            raise ValueError("Alpaca quote is stale")
        price = float(getattr(quote, "ask_price" if decision == "BUY" else "bid_price", 0))
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Alpaca quote has no valid executable-side price")
        return price

    def execute_signal(
        self,
        ticker: str,
        decision: str,
        confidence: float = 50.0,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        position_pct: float = 5.0,
    ) -> dict:
        """
        Execute a trading signal as a paper order.

        Args:
            ticker: stock symbol (e.g. "NVDA")
            decision: "BUY" | "SELL" | "WAIT"
            confidence: 0-100
            entry_price: target entry (0 = market order)
            stop_loss: stop-loss price
            take_profit: take-profit price
            position_pct: % of portfolio to allocate

        Returns:
            dict with order details or error
        """
        if not self._client:
            return {"error": "Alpaca not connected. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"}

        if decision == "WAIT":
            return {"status": "skipped", "reason": "WAIT signal — no action"}

        if confidence < 40:
            return {"status": "skipped", "reason": f"Confidence too low ({confidence:.0f}%)"}

        try:
            from alpaca.trading.requests import (
                MarketOrderRequest, LimitOrderRequest,
                TakeProfitRequest, StopLossRequest,
            )
            from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

            # Calculate position size
            account = self._client.get_account()
            portfolio_value = float(account.portfolio_value)
            if not math.isfinite(portfolio_value) or portfolio_value <= 0:
                raise ValueError("Invalid Alpaca PAPER portfolio value")
            allocation = portfolio_value * (position_pct / 100)

            # entry_price is an untrusted signal/reference price. Market orders
            # always size from a fresh broker-data quote, even when it is set.
            entry_price = self._get_sizing_price(ticker, decision)

            qty = int(allocation / entry_price)
            if qty < 1:
                return {"status": "skipped", "reason": f"Position too small (${allocation:.0f} / ${entry_price:.2f} = 0 shares)"}

            side = OrderSide.BUY if decision == "BUY" else OrderSide.SELL

            # Build order — bracket if stop/take provided
            if stop_loss > 0 and take_profit > 0:
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=round(take_profit, 2)),
                    stop_loss=StopLossRequest(stop_price=round(stop_loss, 2)),
                )
            else:
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )

            order = self._client.submit_order(order_data)

            result = {
                "status": "submitted",
                "order_id": str(order.id),
                "ticker": ticker,
                "side": decision,
                "qty": qty,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "allocation": round(allocation, 2),
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
            }

            logger.info("Order submitted: %s %d %s @ $%.2f (conf=%.0f%%, stop=$%.2f, target=$%.2f)",
                         decision, qty, ticker, entry_price, confidence, stop_loss, take_profit)

            # Sync to local paper trader
            self._sync_to_paper_trader(result)

            return result

        except Exception as e:
            logger.warning("Order failed for %s: %s", ticker, e)
            return {"error": str(e), "ticker": ticker, "decision": decision}

    def close_position(self, ticker: str) -> dict:
        """Close an open position by ticker."""
        if not self._client:
            return {"error": "Not connected"}
        try:
            self._client.close_position(ticker)
            logger.info("Closed position: %s", ticker)
            return {"status": "closed", "ticker": ticker}
        except Exception as e:
            return {"error": str(e)}

    def close_all(self) -> dict:
        """Close all open positions."""
        if not self._client:
            return {"error": "Not connected"}
        try:
            self._client.close_all_positions(cancel_orders=True)
            logger.info("Closed all positions")
            return {"status": "all_closed"}
        except Exception as e:
            return {"error": str(e)}

    def get_recent_orders(self, limit: int = 10) -> list[dict]:
        """Get recent orders."""
        if not self._client:
            return []
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
            orders = self._client.get_orders(req)
            return [{
                "id": str(o.id),
                "ticker": o.symbol,
                "side": str(o.side),
                "qty": float(o.qty) if o.qty else 0,
                "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                "filled_price": float(o.filled_avg_price) if o.filled_avg_price else 0,
                "status": str(o.status),
                "submitted_at": str(o.submitted_at),
                "type": str(o.type),
            } for o in orders]
        except Exception as e:
            logger.warning("Failed to get orders: %s", e)
            return []

    def _sync_to_paper_trader(self, order: dict) -> None:
        """Sync Alpaca order to local PaperTrader journal."""
        try:
            from bot.paper_trading import PaperTrader, PaperTrade
            trader = PaperTrader()
            trade = PaperTrade(
                timestamp=order["timestamp"],
                ticker=order["ticker"],
                direction="LONG" if order["side"] == "BUY" else "SHORT",
                entry_price=order["entry_price"],
                stop_loss=order.get("stop_loss", 0),
                take_profit=order.get("take_profit", 0),
                confidence=order.get("confidence", 0),
                source=f"alpaca_{order.get('order_id', '')}",
                position_size=order.get("qty", 0),
            )
            trader.open_trade(trade)
        except Exception as e:
            logger.warning("Failed to sync to paper trader: %s", e)
