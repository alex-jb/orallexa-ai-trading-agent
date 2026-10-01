import pandas as pd


def simple_backtest(
    df,
    params=None,
    signal_col="signal",
    price_col="Close",
    initial_cash=10000,
    transaction_cost=0.001,
    slippage=0.001,
    debug=False,
    execution_mode="legacy_close",
):
    data = df.copy()

    if price_col not in data.columns:
        if "Adj Close" in data.columns:
            price_col = "Adj Close"
        else:
            raise ValueError(f"Missing column: {price_col}")

    params = params or {}
    rsi_min = params.get("rsi_min", 30)
    rsi_max = params.get("rsi_max", 65)

    if signal_col not in data.columns:
        required_cols = {"RSI", "MA20", "MA50"}
        missing = [c for c in required_cols if c not in data.columns]
        if missing:
            raise ValueError(f"Missing indicator columns for signal generation: {missing}")

        data[signal_col] = (
            (data["RSI"] >= rsi_min) &
            (data["RSI"] <= rsi_max) &
            (data["MA20"] > data["MA50"])
        ).astype(int)

    data["return"] = data[price_col].pct_change().fillna(0.0)
    data["market_return"] = data["return"]

    if execution_mode == "next_open":
        if "Open" not in data.columns:
            raise ValueError("Next-open evaluation requires Open prices")
        if data[signal_col].isna().any() or not data[signal_col].isin([0, 1]).all():
            raise ValueError("Next-open evaluation requires finite long/flat signals")
        if (data["Open"] <= 0).any() or (data[price_col] <= 0).any():
            raise ValueError("Next-open evaluation requires positive prices")
        # A decision from close[t-1] becomes an order at open[t]. The
        # previously held position earns the intervening overnight return;
        # the new position earns open[t] -> close[t]. Cost is charged at open[t].
        position = data[signal_col].shift(1).fillna(0.0)
        prior_position = position.shift(1).fillna(0.0)
        previous_close = data[price_col].shift(1)
        overnight = (data["Open"] / previous_close - 1).fillna(0.0)
        intraday = data[price_col] / data["Open"] - 1
        overnight_factor = 1 + prior_position * overnight
        intraday_factor = 1 + position * intraday
        data["gross_strategy_return"] = overnight_factor * intraday_factor - 1
        data["position_change"] = (position - prior_position).abs()
    elif execution_mode == "legacy_close":
        shifted_signal = data[signal_col].shift(1).fillna(0.0)
        data["gross_strategy_return"] = shifted_signal * data["return"]
        data["position_change"] = data[signal_col].diff().abs().fillna(data[signal_col].abs())
    else:
        raise ValueError(f"Unknown execution_mode: {execution_mode}")
    data["trade_cost"] = data["position_change"] * (transaction_cost + slippage)

    if execution_mode == "next_open":
        data["net_strategy_return"] = overnight_factor * (1 - data["trade_cost"]) * intraday_factor - 1
    else:
        data["net_strategy_return"] = data["gross_strategy_return"] - data["trade_cost"]

    data["strategy_return"] = data["net_strategy_return"]

    data["Signal"] = data[signal_col]
    data["StrategyReturn"] = data["strategy_return"]
    data["MarketReturn"] = data["market_return"]

    data["CumulativeGrossStrategyReturn"] = (1 + data["gross_strategy_return"]).cumprod()
    data["CumulativeNetStrategyReturn"] = (1 + data["net_strategy_return"]).cumprod()
    data["CumulativeStrategyReturn"] = data["CumulativeNetStrategyReturn"]
    data["CumulativeMarketReturn"] = (1 + data["market_return"]).cumprod()

    data["gross_equity_curve"] = initial_cash * data["CumulativeGrossStrategyReturn"]
    data["net_equity_curve"] = initial_cash * data["CumulativeNetStrategyReturn"]
    data["equity_curve"] = data["net_equity_curve"]
    data["market_equity_curve"] = initial_cash * data["CumulativeMarketReturn"]

    if debug:
        print("Backtest completed.")
        print(
            data[
                [
                    price_col,
                    signal_col,
                    "gross_strategy_return",
                    "trade_cost",
                    "net_strategy_return"
                ]
            ].tail()
        )

    return data
