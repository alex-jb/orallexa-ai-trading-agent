import pandas as pd
import numpy as np


def build_portfolio_curve(backtest_map: dict, weights: dict):
    """
    backtest_map:
        {
            "NVDA": bt_test_df,
            "AAPL": bt_test_df,
        }

    weights:
        {
            "NVDA": 0.7,
            "AAPL": 0.3
        }
    """

    if not backtest_map or not weights:
        return pd.DataFrame()

    aligned = []

    for ticker, df in backtest_map.items():
        if df is None or len(df) == 0:
            continue

        weight = weights.get(ticker, 0.0)
        if weight <= 0:
            continue

        temp = df.copy()

        if "net_strategy_return" not in temp.columns:
            raise ValueError(f"{ticker} missing net_strategy_return")

        if "market_return" not in temp.columns:
            raise ValueError(f"{ticker} missing market_return")

        temp = temp[["net_strategy_return", "market_return"]].copy()
        temp.columns = [
            f"{ticker}_net_strategy_return",
            f"{ticker}_market_return"
        ]
        aligned.append(temp)

    if not aligned:
        return pd.DataFrame()

    portfolio_df = pd.concat(aligned, axis=1, join="inner").dropna().copy()

    if len(portfolio_df) == 0:
        return pd.DataFrame()

    portfolio_df["portfolio_net_return"] = 0.0
    portfolio_df["portfolio_market_return"] = 0.0

    for ticker, weight in weights.items():
        net_col = f"{ticker}_net_strategy_return"
        mkt_col = f"{ticker}_market_return"

        if net_col in portfolio_df.columns:
            portfolio_df["portfolio_net_return"] += portfolio_df[net_col] * weight

        if mkt_col in portfolio_df.columns:
            portfolio_df["portfolio_market_return"] += portfolio_df[mkt_col] * weight

    portfolio_df["PortfolioNetCumulative"] = (1 + portfolio_df["portfolio_net_return"]).cumprod()
    portfolio_df["PortfolioMarketCumulative"] = (1 + portfolio_df["portfolio_market_return"]).cumprod()

    return portfolio_df


def evaluate_portfolio(portfolio_df: pd.DataFrame):
    if portfolio_df is None or len(portfolio_df) == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }

    returns = portfolio_df["portfolio_net_return"].dropna()

    if len(returns) == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }

    total_return = float((1 + returns).prod() - 1)

    avg_return = returns.mean()
    std_return = returns.std()

    sharpe = 0.0
    if std_return != 0 and not np.isnan(std_return):
        sharpe = float((avg_return / std_return) * np.sqrt(252))

    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    annualized_return = float((1 + total_return) ** (252 / max(len(returns), 1)) - 1)

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }