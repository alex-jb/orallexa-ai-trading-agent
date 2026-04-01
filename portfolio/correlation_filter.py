"""
portfolio/correlation_filter.py
────────────────────────────────────────────────────────────────────────────
Correlation-aware portfolio selection for Orallexa.
Avoids picking assets that are too correlated with each other
(which would defeat the purpose of diversification).

Usage:
    from portfolio.correlation_filter import filter_by_correlation
    selected = filter_by_correlation(results, ticker_dfs, max_corr=0.75, top_n=3)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def compute_return_correlation(ticker_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Compute pairwise return correlation matrix across tickers.
    ticker_dfs: {ticker: df_with_Close_column}
    """
    returns = {}
    for ticker, df in ticker_dfs.items():
        if "Close" in df.columns and len(df) > 10:
            returns[ticker] = df["Close"].pct_change().dropna()

    if len(returns) < 2:
        return pd.DataFrame()

    ret_df = pd.DataFrame(returns).dropna()
    return ret_df.corr()


def filter_by_correlation(
    results: List[Dict],
    ticker_dfs: Dict[str, pd.DataFrame],
    max_corr: float = 0.75,
    top_n: int = 3,
    rank_by: str = "wf_sharpe",
) -> List[Dict]:
    """
    Select top_n tickers while ensuring pairwise correlation < max_corr.

    Algorithm:
    1. Rank tickers by Sharpe (or chosen metric)
    2. Greedily add the next best ticker if it's not too correlated
       with any already-selected ticker

    Returns filtered list of result dicts.
    """
    valid = [r for r in results if "error" not in r]
    if not valid:
        return []

    # Rank by metric
    def get_rank_score(r):
        if rank_by == "wf_sharpe":
            return r.get("wf_metrics", {}).get("avg_test_sharpe", 0.0) or 0.0
        elif rank_by == "test_sharpe":
            return r.get("test_metrics", {}).get("net", {}).get("sharpe", 0.0) or 0.0
        return 0.0

    ranked = sorted(valid, key=get_rank_score, reverse=True)

    # Compute correlation
    corr_matrix = compute_return_correlation(ticker_dfs)

    selected = []
    selected_tickers = []

    for row in ranked:
        if len(selected) >= top_n:
            break

        ticker = row["ticker"]

        # Check correlation with already-selected tickers
        too_correlated = False
        for sel_ticker in selected_tickers:
            if (not corr_matrix.empty and
                ticker in corr_matrix.columns and
                sel_ticker in corr_matrix.columns):
                corr = abs(corr_matrix.loc[ticker, sel_ticker])
                if corr > max_corr:
                    too_correlated = True
                    break

        if not too_correlated:
            selected.append(row)
            selected_tickers.append(ticker)

    return selected


def correlation_report(ticker_dfs: Dict[str, pd.DataFrame]) -> Dict:
    """
    Return a human-readable correlation report for the Coach to use.
    """
    corr = compute_return_correlation(ticker_dfs)
    if corr.empty:
        return {"matrix": pd.DataFrame(), "high_pairs": [], "avg_correlation": 0.0}

    # Find highly correlated pairs
    tickers = list(corr.columns)
    high_pairs = []
    for i in range(len(tickers)):
        for j in range(i+1, len(tickers)):
            c = corr.iloc[i, j]
            if abs(c) > 0.7:
                high_pairs.append({
                    "pair": f"{tickers[i]}-{tickers[j]}",
                    "correlation": round(float(c), 3),
                    "level": "high" if abs(c) > 0.85 else "moderate",
                })

    # Average off-diagonal correlation
    n = len(tickers)
    if n > 1:
        upper = corr.values[np.triu_indices(n, k=1)]
        avg_corr = float(np.mean(np.abs(upper)))
    else:
        avg_corr = 0.0

    return {
        "matrix":          corr,
        "high_pairs":      high_pairs,
        "avg_correlation": round(avg_corr, 3),
        "diversification": "poor" if avg_corr > 0.7 else ("moderate" if avg_corr > 0.4 else "good"),
    }
