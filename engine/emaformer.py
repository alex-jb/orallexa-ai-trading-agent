"""
engine/emaformer.py
────────────────────────────────────────────────────────────────────────────
EMAformer: Embedding Armor Transformer for Time Series Forecasting
Based on AAAI 2026 paper (arXiv 2511.08396).

Self-contained implementation — no external repo dependency.
Architecture: iTransformer (inverted) + Channel/Phase/Joint embeddings.

Usage:
    from engine.emaformer import EMAformerPredictor
    predictor = EMAformerPredictor(seq_len=96, pred_len=5, n_features=5)
    predictor.fit(train_df)           # train on OHLCV DataFrame
    signals = predictor.predict(test_df)  # returns pd.Series of {0, 1}
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

from core.logger import get_logger

logger = get_logger("emaformer")


# ═══════════════════════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════════════════════

class EMAformerModel(nn.Module):
    """
    EMAformer: iTransformer backbone + 3 auxiliary embeddings.

    Input:  (B, seq_len, N_channels)   — multivariate time series
    Output: (B, pred_len, N_channels)  — predicted future values
    """

    def __init__(
        self,
        seq_len: int = 96,
        pred_len: int = 5,
        enc_in: int = 5,
        d_model: int = 128,
        n_heads: int = 4,
        e_layers: int = 2,
        d_ff: int = 256,
        dropout: float = 0.1,
        cycle: int = 5,
    ):
        super().__init__()
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.enc_in = enc_in
        self.d_model = d_model
        self.cycle = cycle

        # ── Inverted embedding: (B, L, N) -> (B, N, D) ──
        self.enc_embedding = nn.Linear(seq_len, d_model)

        # ── 3 Auxiliary Embeddings (the "Armor") ──
        # 1. Channel Embedding — learnable per-channel representation
        self.channel_emb = nn.Parameter(torch.randn(enc_in, d_model) * 0.02)

        # 2. Phase Embedding — periodic position within cycle
        self.phase_emb = nn.Embedding(cycle, d_model)

        # 3. Joint Channel-Phase Embedding — cross-axis
        self.joint_emb = nn.Embedding(cycle, enc_in * d_model)

        # ── Transformer Encoder ──
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=e_layers)

        # ── MLP Projector: D -> pred_len ──
        self.projector = nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model * 2, d_model * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model * 4, pred_len),
        )

        # ── Instance Normalization ──
        self.norm = nn.LayerNorm(d_model)

    def forward(
        self,
        x: torch.Tensor,
        cycle_idx: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            x:         (B, seq_len, N_channels)
            cycle_idx: (B,) — int in [0, cycle-1]
        Returns:
            (B, pred_len, N_channels)
        """
        B, L, N = x.shape

        # Instance normalization (RevIN-style)
        means = x.mean(dim=1, keepdim=True)
        stdev = x.std(dim=1, keepdim=True) + 1e-5
        x = (x - means) / stdev

        # Inverted embedding: transpose to (B, N, L) then project to (B, N, D)
        x = x.permute(0, 2, 1)                    # (B, N, L)
        x = self.enc_embedding(x)                  # (B, N, D)

        # Add auxiliary embeddings
        # 1. Channel embedding: (N, D) -> broadcast to (B, N, D)
        x = x + self.channel_emb.unsqueeze(0)

        # 2. Phase embedding: (B,) -> (B, D) -> (B, 1, D) -> broadcast
        phase = self.phase_emb(cycle_idx)          # (B, D)
        x = x + phase.unsqueeze(1)

        # 3. Joint embedding: (B,) -> (B, N*D) -> (B, N, D)
        joint = self.joint_emb(cycle_idx)          # (B, N*D)
        joint = joint.view(B, N, self.d_model)     # (B, N, D)
        x = x + joint

        # Layer norm
        x = self.norm(x)

        # Transformer encoder with residual
        enc_out = self.encoder(x)                  # (B, N, D)
        enc_out = enc_out + x                      # residual

        # MLP projector: (B, N, D) -> (B, N, pred_len)
        out = self.projector(enc_out)              # (B, N, pred_len)

        # Transpose back: (B, pred_len, N)
        out = out.permute(0, 2, 1)

        # De-normalize
        out = out * stdev + means

        return out


# ═══════════════════════════════════════════════════════════════════════════
# DATASET
# ═══════════════════════════════════════════════════════════════════════════

class TimeSeriesDataset(Dataset):
    """Sliding window dataset for OHLCV data."""

    def __init__(
        self,
        data: np.ndarray,
        seq_len: int,
        pred_len: int,
        cycle: int = 5,
    ):
        self.data = data.astype(np.float32)
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.cycle = cycle

    def __len__(self) -> int:
        return max(0, len(self.data) - self.seq_len - self.pred_len + 1)

    def __getitem__(self, idx: int):
        s_begin = idx
        s_end = s_begin + self.seq_len
        r_end = s_end + self.pred_len

        x = self.data[s_begin:s_end]
        y = self.data[s_end:r_end]
        cycle_idx = idx % self.cycle

        return (
            torch.tensor(x, dtype=torch.float32),
            torch.tensor(y, dtype=torch.float32),
            torch.tensor(cycle_idx, dtype=torch.long),
        )


# ═══════════════════════════════════════════════════════════════════════════
# PREDICTOR (public API)
# ═══════════════════════════════════════════════════════════════════════════

_OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


class EMAformerPredictor:
    """
    Train EMAformer on stock OHLCV data and generate directional signals.

    Parameters:
        seq_len:     input window length (default 60 trading days)
        pred_len:    prediction horizon (default 5 days)
        n_features:  number of input channels (default 5 = OHLCV)
        d_model:     transformer hidden dim (default 128)
        n_heads:     attention heads (default 4)
        e_layers:    encoder layers (default 2)
        cycle:       periodic cycle for phase embedding (default 5 = trading week)
        epochs:      training epochs (default 30)
        batch_size:  training batch size (default 32)
        lr:          learning rate (default 1e-3)
    """

    def __init__(
        self,
        seq_len: int = 60,
        pred_len: int = 5,
        n_features: int = 5,
        d_model: int = 128,
        n_heads: int = 4,
        e_layers: int = 2,
        cycle: int = 5,
        epochs: int = 30,
        batch_size: int = 32,
        lr: float = 1e-3,
    ):
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.n_features = n_features
        self.d_model = d_model
        self.n_heads = n_heads
        self.e_layers = e_layers
        self.cycle = cycle
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr

        self.model: Optional[EMAformerModel] = None
        self._mean: Optional[np.ndarray] = None
        self._std: Optional[np.ndarray] = None

    def _df_to_array(self, df: pd.DataFrame) -> np.ndarray:
        """Extract OHLCV columns, return (T, N) array."""
        cols = [c for c in _OHLCV_COLS if c in df.columns]
        if len(cols) < 2:
            raise ValueError(f"Need at least Open/Close columns, got: {list(df.columns)}")
        return df[cols].values.astype(np.float32)

    def fit(self, train_df: pd.DataFrame) -> float:
        """
        Train EMAformer on OHLCV data.
        Returns final training loss.
        """
        data = self._df_to_array(train_df)
        n_features = data.shape[1]

        # Normalize
        self._mean = data.mean(axis=0)
        self._std = data.std(axis=0) + 1e-8
        data_norm = (data - self._mean) / self._std

        dataset = TimeSeriesDataset(data_norm, self.seq_len, self.pred_len, self.cycle)
        if len(dataset) < 10:
            logger.warning("Too few samples (%d) for EMAformer training", len(dataset))
            return float("inf")

        # Split: 90% train, 10% val
        val_size = max(1, len(dataset) // 10)
        train_size = len(dataset) - val_size
        train_ds, val_ds = torch.utils.data.random_split(
            dataset, [train_size, val_size],
            generator=torch.Generator().manual_seed(42),
        )

        train_loader = DataLoader(train_ds, batch_size=self.batch_size, shuffle=True)
        val_loader = DataLoader(val_ds, batch_size=self.batch_size, shuffle=False)

        self.model = EMAformerModel(
            seq_len=self.seq_len,
            pred_len=self.pred_len,
            enc_in=n_features,
            d_model=self.d_model,
            n_heads=self.n_heads,
            e_layers=self.e_layers,
            d_ff=self.d_model * 2,
            dropout=0.1,
            cycle=self.cycle,
        )
        self.model.train()

        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)
        criterion = nn.MSELoss()

        best_val_loss = float("inf")
        patience_counter = 0
        patience = 5

        for epoch in range(self.epochs):
            # Train
            self.model.train()
            train_loss = 0.0
            for x, y, c in train_loader:
                optimizer.zero_grad()
                pred = self.model(x, c)
                loss = criterion(pred, y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()
            scheduler.step()

            # Validate
            self.model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for x, y, c in val_loader:
                    pred = self.model(x, c)
                    val_loss += criterion(pred, y).item()

            avg_val = val_loss / max(len(val_loader), 1)

            # Early stopping
            if avg_val < best_val_loss:
                best_val_loss = avg_val
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("EMAformer early stop at epoch %d (val_loss=%.6f)", epoch + 1, best_val_loss)
                    break

        avg_train = train_loss / max(len(train_loader), 1)
        logger.info("EMAformer trained: %d epochs, train_loss=%.6f, val_loss=%.6f",
                     epoch + 1, avg_train, best_val_loss)
        return avg_train

    def predict(self, test_df: pd.DataFrame, full_close: pd.Series = None) -> Optional[pd.Series]:
        """
        Generate directional signals for each test day.
        Returns pd.Series of {0, 1} aligned with test_df.index.
        """
        if self.model is None or self._mean is None:
            return None

        self.model.eval()
        data = self._df_to_array(test_df)
        data_norm = (data - self._mean) / self._std

        # We need seq_len history before each test point
        # Use beginning of test_df as context
        signals = []
        close_idx = _OHLCV_COLS.index("Close") if "Close" in _OHLCV_COLS else 3

        for i in range(len(test_df)):
            if i < self.seq_len:
                # Not enough history yet — default to hold
                signals.append(0)
                continue

            window = data_norm[i - self.seq_len:i]
            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)  # (1, L, N)
            c = torch.tensor([i % self.cycle], dtype=torch.long)

            with torch.no_grad():
                pred = self.model(x, c)  # (1, pred_len, N)

            # Predicted close at end of horizon (de-normalized)
            pred_close = float(pred[0, -1, close_idx]) * self._std[close_idx] + self._mean[close_idx]
            current_close = float(data[i, close_idx])

            signals.append(1 if pred_close > current_close else 0)

        return pd.Series(signals, index=test_df.index)

    def predict_with_context(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> Optional[pd.Series]:
        """
        Predict using train_df as context for early test points.
        More accurate than predict() alone.
        """
        if self.model is None or self._mean is None:
            return None

        self.model.eval()

        train_data = self._df_to_array(train_df)
        test_data = self._df_to_array(test_df)
        full_data = np.concatenate([train_data, test_data], axis=0)
        full_norm = (full_data - self._mean) / self._std

        close_idx = _OHLCV_COLS.index("Close") if "Close" in _OHLCV_COLS else 3
        train_len = len(train_data)

        signals = []
        for i in range(len(test_df)):
            global_idx = train_len + i
            if global_idx < self.seq_len:
                signals.append(0)
                continue

            window = full_norm[global_idx - self.seq_len:global_idx]
            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
            c = torch.tensor([global_idx % self.cycle], dtype=torch.long)

            with torch.no_grad():
                pred = self.model(x, c)

            pred_close = float(pred[0, -1, close_idx]) * self._std[close_idx] + self._mean[close_idx]
            current_close = float(full_data[global_idx, close_idx])

            signals.append(1 if pred_close > current_close else 0)

        return pd.Series(signals, index=test_df.index)
