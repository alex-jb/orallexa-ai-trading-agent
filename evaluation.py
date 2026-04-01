import numpy as np
import pandas as pd


def evaluate(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
        }

    if "strategy_return" in df.columns:
        returns = df["strategy_return"].dropna()
    elif "StrategyReturn" in df.columns:
        returns = df["StrategyReturn"].dropna()
    else:
        raise ValueError("Missing strategy return column in backtest dataframe.")

    if len(returns) == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
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

    if "signal" in df.columns:
        num_trades = int((df["signal"] == 1).sum())
    elif "Signal" in df.columns:
        num_trades = int((df["Signal"] == 1).sum())
    else:
        num_trades = 0

    positive_returns = returns[returns > 0]
    win_rate = float(len(positive_returns) / len(returns)) if len(returns) > 0 else 0.0

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "num_trades": num_trades,
    }