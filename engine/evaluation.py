import numpy as np
import pandas as pd


def _calc_metrics_from_returns(returns: pd.Series, signal_series: pd.Series | None = None):
    returns = returns.dropna()

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

    if signal_series is not None:
        num_trades = int((signal_series == 1).sum())
    else:
        num_trades = 0

    positive_returns = returns[returns > 0]
    win_rate = float(len(positive_returns) / len(returns)) if len(returns) > 0 else 0.0

    # Sortino ratio (downside deviation only)
    downside = returns[returns < 0]
    downside_std = downside.std() if len(downside) > 0 else 0.0
    sortino = 0.0
    if downside_std != 0 and not np.isnan(downside_std):
        sortino = float((avg_return / downside_std) * np.sqrt(252))

    # Calmar ratio (annualized return / max drawdown)
    calmar = 0.0
    if max_drawdown != 0:
        calmar = float(annualized_return / abs(max_drawdown))

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "num_trades": num_trades,
    }


def evaluate(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return {
            "gross": _calc_metrics_from_returns(pd.Series(dtype=float)),
            "net": _calc_metrics_from_returns(pd.Series(dtype=float)),
            "cost_summary": {
                "total_trade_cost": 0.0,
                "avg_trade_cost": 0.0,
            },
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
        }

    if "signal" in df.columns:
        signal_series = df["signal"]
    elif "Signal" in df.columns:
        signal_series = df["Signal"]
    else:
        signal_series = None

    if "gross_strategy_return" in df.columns:
        gross_returns = df["gross_strategy_return"]
    else:
        gross_returns = pd.Series(dtype=float)

    if "net_strategy_return" in df.columns:
        net_returns = df["net_strategy_return"]
    elif "strategy_return" in df.columns:
        net_returns = df["strategy_return"]
    elif "StrategyReturn" in df.columns:
        net_returns = df["StrategyReturn"]
    else:
        raise ValueError("Missing strategy return column in backtest dataframe.")

    gross_metrics = _calc_metrics_from_returns(gross_returns, signal_series)
    net_metrics = _calc_metrics_from_returns(net_returns, signal_series)

    total_trade_cost = float(df["trade_cost"].sum()) if "trade_cost" in df.columns else 0.0
    avg_trade_cost = float(df["trade_cost"].mean()) if "trade_cost" in df.columns else 0.0

    return {
        "gross": gross_metrics,
        "net": net_metrics,
        "cost_summary": {
            "total_trade_cost": total_trade_cost,
            "avg_trade_cost": avg_trade_cost,
        },
        "total_return": net_metrics["total_return"],
        "annualized_return": net_metrics["annualized_return"],
        "sharpe": net_metrics["sharpe"],
        "max_drawdown": net_metrics["max_drawdown"],
        "win_rate": net_metrics["win_rate"],
        "num_trades": net_metrics["num_trades"],
    }