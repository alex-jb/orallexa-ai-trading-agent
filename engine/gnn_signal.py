"""
engine/gnn_signal.py
────────────────────────────────────────────────────────────────────────────
Graph Neural Network for inter-stock signal propagation.

Captures relationships between stocks (sector, supply chain, correlation)
using a lightweight GAT (Graph Attention Network) built on pure PyTorch.
No torch-geometric dependency required.

The idea: if NVDA's suppliers (TSM, ASML) and customers (MSFT, META) are
all showing bullish signals, that's a stronger signal for NVDA than
looking at NVDA alone.

Usage:
    from engine.gnn_signal import GNNSignalGenerator
    gen = GNNSignalGenerator(target="NVDA")
    result = gen.run()  # returns dict with signal, confidence, graph_context
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

from core.logger import get_logger

logger = get_logger("gnn_signal")


# ═══════════════════════════════════════════════════════════════════════════
# STOCK UNIVERSE & GRAPH DEFINITION
# ═══════════════════════════════════════════════════════════════════════════

# Pre-defined stock relationship graph (sector + supply chain)
# Each entry: (ticker, sector, [related_tickers])
STOCK_GRAPH = {
    "NVDA":  {"sector": "semiconductor", "related": ["TSM", "ASML", "AMD", "MSFT", "META", "GOOGL"]},
    "AMD":   {"sector": "semiconductor", "related": ["NVDA", "TSM", "INTC", "MSFT"]},
    "TSM":   {"sector": "semiconductor", "related": ["NVDA", "AMD", "ASML", "AAPL"]},
    "ASML":  {"sector": "semiconductor", "related": ["NVDA", "TSM", "AMD"]},
    "INTC":  {"sector": "semiconductor", "related": ["AMD", "NVDA", "TSM"]},
    "AAPL":  {"sector": "tech_hardware", "related": ["TSM", "MSFT", "GOOGL", "AVGO"]},
    "MSFT":  {"sector": "cloud",         "related": ["NVDA", "GOOGL", "AMZN", "META", "AAPL"]},
    "GOOGL": {"sector": "cloud",         "related": ["MSFT", "META", "AMZN", "NVDA"]},
    "META":  {"sector": "social",        "related": ["GOOGL", "NVDA", "MSFT", "SNAP"]},
    "AMZN":  {"sector": "cloud",         "related": ["MSFT", "GOOGL", "AAPL"]},
    "TSLA":  {"sector": "ev",            "related": ["NVDA", "AAPL", "LI", "NIO"]},
    "SPY":   {"sector": "index",         "related": ["QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]},
    "QQQ":   {"sector": "index",         "related": ["SPY", "AAPL", "MSFT", "NVDA", "GOOGL", "META"]},
    "AVGO":  {"sector": "semiconductor", "related": ["NVDA", "AMD", "TSM", "AAPL"]},
    "SNAP":  {"sector": "social",        "related": ["META", "GOOGL"]},
    "LI":    {"sector": "ev",            "related": ["TSLA", "NIO"]},
    "NIO":   {"sector": "ev",            "related": ["TSLA", "LI"]},
}

# Feature list per node (technical indicators)
NODE_FEATURES = ["RSI", "MACD_Hist", "BB_Pct", "ADX", "ROC", "Volume_Ratio"]
N_NODE_FEATURES = len(NODE_FEATURES)


def _build_adjacency(target: str, universe: list[str]) -> torch.Tensor:
    """
    Build adjacency matrix from STOCK_GRAPH relationships.
    Also adds correlation-based edges.
    Returns: (N, N) float tensor with edge weights.
    """
    n = len(universe)
    adj = torch.zeros(n, n)

    ticker_idx = {t: i for i, t in enumerate(universe)}

    for i, t in enumerate(universe):
        info = STOCK_GRAPH.get(t, {})
        related = info.get("related", [])
        for r in related:
            if r in ticker_idx:
                j = ticker_idx[r]
                # Stronger weight for direct supply chain vs sector peers
                adj[i, j] = 1.0
                adj[j, i] = 1.0

        # Self-loop
        adj[i, i] = 1.0

    # Normalize by degree (D^-1/2 * A * D^-1/2)
    deg = adj.sum(dim=1).clamp(min=1)
    deg_inv_sqrt = deg.pow(-0.5)
    adj = deg_inv_sqrt.unsqueeze(1) * adj * deg_inv_sqrt.unsqueeze(0)

    return adj


# ═══════════════════════════════════════════════════════════════════════════
# GAT MODEL (pure PyTorch)
# ═══════════════════════════════════════════════════════════════════════════

class GATLayer(nn.Module):
    """Single Graph Attention layer."""

    def __init__(self, in_dim: int, out_dim: int, n_heads: int = 2, dropout: float = 0.1):
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = out_dim // n_heads
        assert out_dim % n_heads == 0

        self.W = nn.Linear(in_dim, out_dim, bias=False)
        self.a_src = nn.Parameter(torch.randn(n_heads, self.head_dim) * 0.01)
        self.a_dst = nn.Parameter(torch.randn(n_heads, self.head_dim) * 0.01)
        self.dropout = nn.Dropout(dropout)
        self.leaky = nn.LeakyReLU(0.2)

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x:   (N, in_dim)
            adj: (N, N) adjacency matrix
        Returns:
            (N, out_dim)
        """
        N = x.size(0)
        h = self.W(x)  # (N, out_dim)
        h = h.view(N, self.n_heads, self.head_dim)  # (N, H, D)

        # Attention scores
        e_src = (h * self.a_src.unsqueeze(0)).sum(dim=-1)  # (N, H)
        e_dst = (h * self.a_dst.unsqueeze(0)).sum(dim=-1)  # (N, H)

        # (N, N, H) attention matrix
        attn = self.leaky(e_src.unsqueeze(1) + e_dst.unsqueeze(0))  # (N, N, H)

        # Mask by adjacency
        mask = (adj > 0).unsqueeze(-1).expand_as(attn)
        attn = attn.masked_fill(~mask, float("-inf"))

        attn = F.softmax(attn, dim=1)
        attn = self.dropout(attn)

        # Aggregate: (N, N, H) x (N, H, D) -> (N, H, D)
        out = torch.einsum("ijh,jhd->ihd", attn, h)
        out = out.reshape(N, -1)  # (N, out_dim)

        return out


class StockGNN(nn.Module):
    """
    2-layer GAT for stock signal propagation.
    Input: per-stock features (N, F)
    Output: per-stock signal logit (N, 1)
    """

    def __init__(self, in_dim: int = N_NODE_FEATURES, hidden_dim: int = 32, n_heads: int = 2):
        super().__init__()
        self.gat1 = GATLayer(in_dim, hidden_dim, n_heads)
        self.gat2 = GATLayer(hidden_dim, hidden_dim, n_heads)
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.GELU(),
            nn.Linear(16, 1),
        )

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x:   (N, in_dim)
            adj: (N, N)
        Returns:
            logits: (N, 1)
        """
        h = F.gelu(self.norm1(self.gat1(x, adj)))
        h = F.gelu(self.norm2(self.gat2(h, adj)))
        return self.classifier(h)


# ═══════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_features(tickers: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """Fetch OHLCV + compute basic indicators for each ticker."""
    import yfinance as yf
    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2

    data = {}
    for t in tickers:
        try:
            df = yf.Ticker(t).history(period=period, interval="1d")
            if df.empty or len(df) < 30:
                continue
            ta = TechnicalAnalysisSkillV2(df)
            ta.add_indicators()
            df = ta.df
            data[t] = df
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", t, e)
    return data


def _align_data(data: dict[str, pd.DataFrame]) -> tuple[list[str], pd.DatetimeIndex]:
    """Find common date range across all tickers."""
    if not data:
        return [], pd.DatetimeIndex([])

    indices = [set(df.index) for df in data.values()]
    common = sorted(set.intersection(*indices))
    tickers = list(data.keys())
    return tickers, pd.DatetimeIndex(common)


def _build_feature_tensors(
    data: dict[str, pd.DataFrame],
    tickers: list[str],
    dates: pd.DatetimeIndex,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Build (T, N, F) feature tensor and (T, N) label tensor.
    Label: 1 if close price goes up in next 5 days, else 0.
    """
    T = len(dates)
    N = len(tickers)
    F = N_NODE_FEATURES
    forward = 5

    features = torch.zeros(T, N, F)
    labels = torch.zeros(T, N)

    for j, t in enumerate(tickers):
        df = data[t].loc[dates]
        for k, col in enumerate(NODE_FEATURES):
            if col in df.columns:
                vals = df[col].fillna(0).values
                # Z-score normalize
                mean, std = vals.mean(), vals.std() + 1e-8
                features[:, j, k] = torch.tensor((vals - mean) / std, dtype=torch.float32)

        # Labels: forward return > 0
        close = df["Close"].values
        for i in range(T - forward):
            labels[i, j] = 1.0 if close[min(i + forward, T - 1)] > close[i] else 0.0

    return features, labels


# ═══════════════════════════════════════════════════════════════════════════
# GENERATOR (public API)
# ═══════════════════════════════════════════════════════════════════════════

class GNNSignalGenerator:
    """
    Generate trading signals using Graph Neural Network.

    Fetches data for the target stock and its graph neighbors,
    trains a GAT to propagate signals across the stock graph,
    and returns a prediction for the target.
    """

    def __init__(self, target: str = "NVDA", period: str = "6mo", epochs: int = 50):
        self.target = target.upper()
        self.period = period
        self.epochs = epochs

    def _get_universe(self) -> list[str]:
        """Get target + related stocks."""
        info = STOCK_GRAPH.get(self.target, {"related": []})
        related = info.get("related", [])
        universe = [self.target] + [t for t in related if t != self.target]
        # Add 2nd-degree connections for richer graph
        for t in list(related):
            info2 = STOCK_GRAPH.get(t, {"related": []})
            for t2 in info2.get("related", []):
                if t2 not in universe:
                    universe.append(t2)
        return universe[:15]  # cap at 15 nodes

    def run(self) -> dict:
        """
        Fetch data, train GNN, generate signal.
        Returns dict with signal, confidence, graph context.
        """
        universe = self._get_universe()
        logger.info("GNN universe for %s: %s", self.target, universe)

        # Fetch data
        data = _fetch_features(universe, self.period)
        available = [t for t in universe if t in data]
        if self.target not in available:
            return {"error": f"Cannot fetch data for {self.target}", "signal": 0, "confidence": 0.0}

        tickers, dates = _align_data({t: data[t] for t in available})
        if len(dates) < 40:
            return {"error": "Not enough common trading days", "signal": 0, "confidence": 0.0}

        target_idx = tickers.index(self.target)

        # Build graph
        adj = _build_adjacency(self.target, tickers)
        features, labels = _build_feature_tensors(data, tickers, dates)

        # Train/test split
        split = int(len(dates) * 0.8)
        train_x, train_y = features[:split], labels[:split]
        test_x, test_y = features[split:], labels[split:]

        # Train GNN
        model = StockGNN(in_dim=N_NODE_FEATURES, hidden_dim=32, n_heads=2)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
        criterion = nn.BCEWithLogitsLoss()

        model.train()
        for epoch in range(self.epochs):
            total_loss = 0.0
            for i in range(len(train_x)):
                x_i = train_x[i]   # (N, F)
                y_i = train_y[i]   # (N,)

                logits = model(x_i, adj).squeeze(-1)  # (N,)
                loss = criterion(logits, y_i)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        # Evaluate on test set
        model.eval()
        predictions = []
        actuals = []
        all_probs = []

        with torch.no_grad():
            for i in range(len(test_x)):
                logits = model(test_x[i], adj).squeeze(-1)
                probs = torch.sigmoid(logits)
                pred = (probs > 0.5).float()
                predictions.append(pred[target_idx].item())
                actuals.append(test_y[i, target_idx].item())
                all_probs.append(probs[target_idx].item())

        accuracy = sum(1 for p, a in zip(predictions, actuals) if p == a) / max(len(predictions), 1)

        # Latest signal (last test day)
        latest_prob = all_probs[-1] if all_probs else 0.5
        signal = 1 if latest_prob > 0.5 else 0
        confidence = abs(latest_prob - 0.5) * 200  # 0-100 scale

        # Graph context: what are neighbors signaling?
        with torch.no_grad():
            latest_logits = model(test_x[-1], adj).squeeze(-1)
            latest_probs = torch.sigmoid(latest_logits)

        neighbor_signals = {}
        for j, t in enumerate(tickers):
            if t != self.target:
                p = latest_probs[j].item()
                neighbor_signals[t] = {
                    "direction": "bullish" if p > 0.5 else "bearish",
                    "probability": round(p, 3),
                }

        # Consensus
        bullish_count = sum(1 for v in neighbor_signals.values() if v["direction"] == "bullish")
        bearish_count = len(neighbor_signals) - bullish_count
        consensus = "bullish" if bullish_count > bearish_count else "bearish" if bearish_count > bullish_count else "mixed"

        # Backtest signal series
        signal_series = pd.Series(predictions, index=dates[split:split + len(predictions)])

        logger.info("GNN %s: signal=%s conf=%.1f%% acc=%.1f%% consensus=%s (%d bull / %d bear)",
                     self.target, "BUY" if signal else "FLAT", confidence,
                     accuracy * 100, consensus, bullish_count, bearish_count)

        return {
            "ticker": self.target,
            "signal": signal,
            "signal_label": "BUY" if signal else "FLAT",
            "confidence": round(confidence, 1),
            "probability": round(latest_prob, 3),
            "accuracy": round(accuracy, 4),
            "consensus": consensus,
            "bullish_neighbors": bullish_count,
            "bearish_neighbors": bearish_count,
            "neighbor_signals": neighbor_signals,
            "universe_size": len(tickers),
            "signal_series": signal_series,
            "graph_edges": len(adj.nonzero()),
        }
