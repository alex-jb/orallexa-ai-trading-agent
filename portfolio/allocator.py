"""
portfolio/allocator.py
Updated to use correlation-aware selection.
"""
from skills.market_data import MarketDataSkill


def select_top_n(results, n=2):
    """Original selection by WF Sharpe — kept as fallback."""
    valid = []
    for row in results:
        if "error" in row:
            continue
        wf_sharpe = row.get("wf_metrics", {}).get("avg_test_sharpe", 0.0)
        if wf_sharpe is None:
            wf_sharpe = 0.0
        if wf_sharpe > 0:
            valid.append(row)

    valid = sorted(
        valid,
        key=lambda x: x.get("wf_metrics", {}).get("avg_test_sharpe", 0.0),
        reverse=True
    )
    return valid[:n]


def select_top_n_diversified(results, n=2, max_corr=0.75):
    """
    NEW: Select top N tickers by WF Sharpe, but filter out
    highly correlated pairs to ensure diversification.
    Falls back to select_top_n if correlation data unavailable.
    """
    try:
        from portfolio.correlation_filter import filter_by_correlation

        # Build ticker_dfs for correlation calculation
        valid = [r for r in results if "error" not in r]
        if not valid:
            return []

        ticker_dfs = {}
        for r in valid:
            try:
                df = MarketDataSkill(r["ticker"]).execute()
                ticker_dfs[r["ticker"]] = df
            except Exception:
                pass

        if not ticker_dfs:
            return select_top_n(results, n)

        selected = filter_by_correlation(
            results=valid,
            ticker_dfs=ticker_dfs,
            max_corr=max_corr,
            top_n=n,
        )

        # If correlation filter returns nothing, fall back
        return selected if selected else select_top_n(results, n)

    except Exception:
        return select_top_n(results, n)


def allocate_by_sharpe(selected_rows):
    if not selected_rows:
        return {}

    sharpes = {}
    for row in selected_rows:
        ticker = row["ticker"]
        sharpe = row.get("wf_metrics", {}).get("avg_test_sharpe", 0.0)
        sharpes[ticker] = max(float(sharpe), 0.0)

    total = sum(sharpes.values())

    if total <= 0:
        equal_weight = 1.0 / len(selected_rows)
        return {row["ticker"]: equal_weight for row in selected_rows}

    weights = {ticker: sharpe / total for ticker, sharpe in sharpes.items()}
    return weights
