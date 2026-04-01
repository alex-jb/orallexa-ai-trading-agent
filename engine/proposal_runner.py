from engine.backtest import simple_backtest
from engine.evaluation import evaluate


def proposal_to_params(proposal: dict, fallback_params: dict | None = None) -> dict:
    fallback_params = fallback_params or {}

    return {
        "rsi_min": int(proposal.get("rsi_min", fallback_params.get("rsi_min", 35))),
        "rsi_max": int(proposal.get("rsi_max", fallback_params.get("rsi_max", 65))),
        "stop_loss": float(proposal.get("stop_loss", fallback_params.get("stop_loss", 0.03))),
        "take_profit": float(proposal.get("take_profit", fallback_params.get("take_profit", 0.08))),
    }


def run_proposal_backtest(
    df,
    proposal: dict,
    fallback_params: dict | None = None,
    transaction_cost: float = 0.001,
    slippage: float = 0.001,
):
    params = proposal_to_params(proposal, fallback_params=fallback_params)

    bt = simple_backtest(
        df,
        params=params,
        debug=False,
        transaction_cost=transaction_cost,
        slippage=slippage
    )
    metrics = evaluate(bt)

    return {
        "params": params,
        "backtest": bt,
        "metrics": metrics
    }


def compare_metric_block(current_metrics: dict, proposal_metrics: dict) -> dict:
    current_net = current_metrics.get("net", {})
    proposal_net = proposal_metrics.get("net", {})

    return {
        "current_sharpe": current_net.get("sharpe", 0.0),
        "proposal_sharpe": proposal_net.get("sharpe", 0.0),
        "delta_sharpe": proposal_net.get("sharpe", 0.0) - current_net.get("sharpe", 0.0),

        "current_return": current_net.get("total_return", 0.0),
        "proposal_return": proposal_net.get("total_return", 0.0),
        "delta_return": proposal_net.get("total_return", 0.0) - current_net.get("total_return", 0.0),

        "current_drawdown": current_net.get("max_drawdown", 0.0),
        "proposal_drawdown": proposal_net.get("max_drawdown", 0.0),
        "delta_drawdown": proposal_net.get("max_drawdown", 0.0) - current_net.get("max_drawdown", 0.0),
    }


def proposal_is_better(current_metrics: dict, proposal_metrics: dict) -> bool:
    current_net = current_metrics.get("net", {})
    proposal_net = proposal_metrics.get("net", {})

    current_sharpe = current_net.get("sharpe", 0.0)
    proposal_sharpe = proposal_net.get("sharpe", 0.0)

    current_return = current_net.get("total_return", 0.0)
    proposal_return = proposal_net.get("total_return", 0.0)

    current_dd = current_net.get("max_drawdown", 0.0)
    proposal_dd = proposal_net.get("max_drawdown", 0.0)

    sharpe_better = proposal_sharpe > current_sharpe
    return_better = proposal_return >= current_return
    dd_not_much_worse = proposal_dd >= current_dd - 0.03

    return sharpe_better and return_better and dd_not_much_worse