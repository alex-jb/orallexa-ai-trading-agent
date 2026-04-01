"""
engine/diffusion_signal.py
────────────────────────────────────────────────────────────────────────────
Denoising Diffusion Probabilistic Model (DDPM) for stock price forecasting.

Instead of a single point prediction, generates N possible future price
paths and computes probabilistic signals (up/down distribution, VaR, etc.).

Architecture: 1D U-Net conditioned on recent price context.
Pure PyTorch — no external diffusion library needed.

Usage:
    from engine.diffusion_signal import DiffusionPredictor
    pred = DiffusionPredictor(context_len=60, pred_len=5)
    pred.fit(train_df)
    result = pred.predict(test_df)
    # result: {"signal": 1, "up_prob": 0.72, "paths": [...], ...}
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

logger = get_logger("diffusion")


# ═══════════════════════════════════════════════════════════════════════════
# NOISE SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════

def _cosine_beta_schedule(timesteps: int, s: float = 0.008) -> torch.Tensor:
    """Cosine noise schedule (Nichol & Dhariwal 2021)."""
    steps = timesteps + 1
    x = torch.linspace(0, timesteps, steps)
    alphas_cumprod = torch.cos(((x / timesteps) + s) / (1 + s) * math.pi * 0.5) ** 2
    alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
    betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
    return betas.clamp(0.0001, 0.9999)


# ═══════════════════════════════════════════════════════════════════════════
# 1D U-NET (noise predictor)
# ═══════════════════════════════════════════════════════════════════════════

class SinusoidalPosEmb(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        half = self.dim // 2
        emb = math.log(10000) / (half - 1)
        emb = torch.exp(torch.arange(half, device=t.device) * -emb)
        emb = t[:, None].float() * emb[None, :]
        return torch.cat([emb.sin(), emb.cos()], dim=-1)


class ResBlock1D(nn.Module):
    def __init__(self, channels: int, time_dim: int):
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, 3, padding=1)
        self.conv2 = nn.Conv1d(channels, channels, 3, padding=1)
        self.norm1 = nn.GroupNorm(min(8, channels), channels)
        self.norm2 = nn.GroupNorm(min(8, channels), channels)
        self.time_mlp = nn.Linear(time_dim, channels)

    def forward(self, x: torch.Tensor, t_emb: torch.Tensor) -> torch.Tensor:
        h = self.norm1(x)
        h = F.gelu(h)
        h = self.conv1(h)
        h = h + self.time_mlp(t_emb).unsqueeze(-1)
        h = self.norm2(h)
        h = F.gelu(h)
        h = self.conv2(h)
        return x + h


class NoisePredictor(nn.Module):
    """
    Conditional 1D U-Net: predicts noise given noisy future + context.

    Input:  noisy_future (B, 1, pred_len) + context (B, 1, context_len)
    Output: predicted noise (B, 1, pred_len)
    """

    def __init__(self, context_len: int = 60, pred_len: int = 5, hidden: int = 64, time_dim: int = 32):
        super().__init__()
        self.pred_len = pred_len
        self.context_len = context_len

        # Time embedding
        self.time_mlp = nn.Sequential(
            SinusoidalPosEmb(time_dim),
            nn.Linear(time_dim, time_dim * 2),
            nn.GELU(),
            nn.Linear(time_dim * 2, time_dim),
        )

        # Context encoder
        self.ctx_encoder = nn.Sequential(
            nn.Conv1d(1, hidden // 2, 3, padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool1d(pred_len),
            nn.Conv1d(hidden // 2, hidden, 1),
        )

        # Input projection (noisy future + context features)
        self.input_proj = nn.Conv1d(1 + hidden, hidden, 1)

        # Residual blocks
        self.block1 = ResBlock1D(hidden, time_dim)
        self.block2 = ResBlock1D(hidden, time_dim)
        self.block3 = ResBlock1D(hidden, time_dim)

        # Output
        self.out = nn.Sequential(
            nn.GroupNorm(min(8, hidden), hidden),
            nn.GELU(),
            nn.Conv1d(hidden, 1, 1),
        )

    def forward(self, x_noisy: torch.Tensor, context: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x_noisy: (B, 1, pred_len) — noisy future prices
            context: (B, 1, context_len) — recent price history
            t:       (B,) — diffusion timestep
        Returns:
            (B, 1, pred_len) — predicted noise
        """
        t_emb = self.time_mlp(t)  # (B, time_dim)

        # Encode context
        ctx = self.ctx_encoder(context)  # (B, hidden, pred_len)

        # Concatenate noisy input with context features
        h = torch.cat([x_noisy, ctx], dim=1)  # (B, 1+hidden, pred_len)
        h = self.input_proj(h)  # (B, hidden, pred_len)

        # Residual blocks
        h = self.block1(h, t_emb)
        h = self.block2(h, t_emb)
        h = self.block3(h, t_emb)

        return self.out(h)  # (B, 1, pred_len)


# ═══════════════════════════════════════════════════════════════════════════
# DATASET
# ═══════════════════════════════════════════════════════════════════════════

class PriceDataset(Dataset):
    def __init__(self, prices: np.ndarray, context_len: int, pred_len: int):
        self.prices = prices.astype(np.float32)
        self.context_len = context_len
        self.pred_len = pred_len

    def __len__(self) -> int:
        return max(0, len(self.prices) - self.context_len - self.pred_len + 1)

    def __getitem__(self, idx):
        ctx = self.prices[idx:idx + self.context_len]
        fut = self.prices[idx + self.context_len:idx + self.context_len + self.pred_len]

        # Normalize: log returns relative to last context price (bounded)
        ref = ctx[-1] + 1e-8
        ctx_norm = np.log(ctx / ref + 1e-8)
        fut_norm = np.log(fut / ref + 1e-8)

        return (
            torch.tensor(ctx_norm, dtype=torch.float32).unsqueeze(0),  # (1, ctx_len)
            torch.tensor(fut_norm, dtype=torch.float32).unsqueeze(0),  # (1, pred_len)
            torch.tensor(ref, dtype=torch.float32),
        )


# ═══════════════════════════════════════════════════════════════════════════
# PREDICTOR (public API)
# ═══════════════════════════════════════════════════════════════════════════

class DiffusionPredictor:
    """
    DDPM-based probabilistic price forecaster.

    Generates multiple possible future price paths and computes:
    - Up/down probability distribution
    - Expected return
    - Value at Risk (VaR)
    - Confidence interval

    Parameters:
        context_len:  lookback window (default 60)
        pred_len:     forecast horizon (default 5)
        n_steps:      diffusion timesteps (default 100)
        n_samples:    paths to generate (default 50)
        epochs:       training epochs (default 40)
        batch_size:   training batch size (default 32)
    """

    def __init__(
        self,
        context_len: int = 60,
        pred_len: int = 5,
        n_steps: int = 100,
        n_samples: int = 50,
        epochs: int = 40,
        batch_size: int = 32,
    ):
        self.context_len = context_len
        self.pred_len = pred_len
        self.n_steps = n_steps
        self.n_samples = n_samples
        self.epochs = epochs
        self.batch_size = batch_size

        self.model: Optional[NoisePredictor] = None

        # Precompute noise schedule
        betas = _cosine_beta_schedule(n_steps)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0)

        self._betas = betas
        self._sqrt_alphas_cumprod = torch.sqrt(alphas_cumprod)
        self._sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - alphas_cumprod)
        self._sqrt_recip_alphas = torch.sqrt(1.0 / alphas)
        self._posterior_variance = betas * (1.0 - torch.cat([torch.tensor([1.0]), alphas_cumprod[:-1]])) / (1.0 - alphas_cumprod)

    def fit(self, train_df: pd.DataFrame) -> float:
        """Train the diffusion model. Returns final loss."""
        close = train_df["Close"].values if "Close" in train_df.columns else train_df.iloc[:, 3].values
        dataset = PriceDataset(close, self.context_len, self.pred_len)

        if len(dataset) < 10:
            logger.warning("Too few samples (%d) for diffusion training", len(dataset))
            return float("inf")

        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        self.model = NoisePredictor(
            context_len=self.context_len,
            pred_len=self.pred_len,
            hidden=64,
            time_dim=32,
        )
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)

        self.model.train()
        final_loss = 0.0

        for epoch in range(self.epochs):
            epoch_loss = 0.0
            for ctx, fut, ref in loader:
                B = ctx.size(0)

                # Sample random timesteps
                t = torch.randint(0, self.n_steps, (B,))

                # Add noise
                noise = torch.randn_like(fut)
                sqrt_ac = self._sqrt_alphas_cumprod[t].view(B, 1, 1)
                sqrt_1mac = self._sqrt_one_minus_alphas_cumprod[t].view(B, 1, 1)
                noisy = sqrt_ac * fut + sqrt_1mac * noise

                # Predict noise
                pred_noise = self.model(noisy, ctx, t)
                loss = F.mse_loss(pred_noise, noise)

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                epoch_loss += loss.item()
            scheduler.step()
            final_loss = epoch_loss / max(len(loader), 1)

        logger.info("Diffusion trained: %d epochs, loss=%.6f", self.epochs, final_loss)
        return final_loss

    @torch.no_grad()
    def _sample(self, context: torch.Tensor) -> torch.Tensor:
        """
        Generate one sample path via reverse diffusion.
        Args:
            context: (1, 1, context_len)
        Returns:
            (1, 1, pred_len) — denoised future
        """
        x = torch.randn(1, 1, self.pred_len)

        for t_idx in reversed(range(self.n_steps)):
            t = torch.tensor([t_idx])
            pred_noise = self.model(x, context, t)

            # Reverse step
            beta = self._betas[t_idx]
            sqrt_recip = self._sqrt_recip_alphas[t_idx]
            sqrt_1mac = self._sqrt_one_minus_alphas_cumprod[t_idx]

            x = sqrt_recip * (x - beta / sqrt_1mac * pred_noise)

            if t_idx > 0:
                noise = torch.randn_like(x)
                x = x + torch.sqrt(self._posterior_variance[t_idx]) * noise

        return x

    def predict(self, test_df: pd.DataFrame) -> dict:
        """
        Generate probabilistic forecast from the last context_len prices.
        Returns dict with signal, probabilities, paths, VaR, etc.
        """
        if self.model is None:
            return {"error": "Model not trained", "signal": 0}

        self.model.eval()
        close = test_df["Close"].values if "Close" in test_df.columns else test_df.iloc[:, 3].values

        if len(close) < 10:
            return {"error": "Not enough data", "signal": 0}

        # Prepare context — pad with repeated first value if shorter than context_len
        if len(close) < self.context_len:
            pad_len = self.context_len - len(close)
            ctx_raw = np.concatenate([np.full(pad_len, close[0]), close])
        else:
            ctx_raw = close[-self.context_len:]
        ref_price = float(ctx_raw[-1])
        ctx_norm = np.log(ctx_raw / ref_price + 1e-8).astype(np.float32)
        ctx_tensor = torch.tensor(ctx_norm).unsqueeze(0).unsqueeze(0)  # (1, 1, ctx_len)

        # Generate N sample paths
        paths_norm = []
        for _ in range(self.n_samples):
            sample = self._sample(ctx_tensor)  # (1, 1, pred_len)
            paths_norm.append(sample.squeeze().numpy())

        paths_norm = np.array(paths_norm)  # (N, pred_len)
        # Denormalize: exp(log_return) * ref_price, clamp to realistic range
        paths_norm = np.clip(paths_norm, -0.3, 0.3)  # max ±30% over pred_len
        paths_price = np.exp(paths_norm) * ref_price

        # Final price distribution
        final_prices = paths_price[:, -1]
        returns = final_prices / ref_price - 1.0

        up_prob = float((returns > 0).mean())
        down_prob = float((returns < 0).mean())
        expected_return = float(returns.mean())
        median_return = float(np.median(returns))

        # VaR (5th percentile loss)
        var_5 = float(np.percentile(returns, 5))
        var_95 = float(np.percentile(returns, 95))

        # Confidence interval
        ci_low = float(np.percentile(final_prices, 10))
        ci_high = float(np.percentile(final_prices, 90))

        signal = 1 if up_prob > 0.55 else 0
        confidence = abs(up_prob - 0.5) * 200

        logger.info("Diffusion %s: up=%.1f%% exp_ret=%.2f%% VaR5=%.2f%% signal=%s",
                     "predict", up_prob * 100, expected_return * 100, var_5 * 100,
                     "BUY" if signal else "FLAT")

        return {
            "signal": signal,
            "signal_label": "BUY" if signal else "FLAT",
            "confidence": round(confidence, 1),
            "up_probability": round(up_prob, 3),
            "down_probability": round(down_prob, 3),
            "expected_return": round(expected_return, 4),
            "median_return": round(median_return, 4),
            "var_5pct": round(var_5, 4),
            "var_95pct": round(var_95, 4),
            "ci_low": round(ci_low, 2),
            "ci_high": round(ci_high, 2),
            "current_price": round(ref_price, 2),
            "n_paths": self.n_samples,
            "paths_final_prices": [round(float(p), 2) for p in final_prices[:10]],
        }

    def predict_signal_series(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> Optional[pd.Series]:
        """
        Generate binary signal series for backtesting.
        Rolling predict across test_df using train+test as context.
        """
        if self.model is None:
            return None

        self.model.eval()
        close_train = train_df["Close"].values if "Close" in train_df.columns else train_df.iloc[:, 3].values
        close_test = test_df["Close"].values if "Close" in test_df.columns else test_df.iloc[:, 3].values
        full_close = np.concatenate([close_train, close_test])

        train_len = len(close_train)
        signals = []

        for i in range(len(test_df)):
            global_idx = train_len + i
            if global_idx < self.context_len:
                signals.append(0)
                continue

            ctx_raw = full_close[global_idx - self.context_len:global_idx]
            ref = float(ctx_raw[-1])
            ctx_norm = np.log(ctx_raw / ref + 1e-8).astype(np.float32)
            ctx_tensor = torch.tensor(ctx_norm).unsqueeze(0).unsqueeze(0)

            # Quick sample (fewer paths for speed)
            returns_list = []
            for _ in range(20):
                sample = self._sample(ctx_tensor).squeeze().numpy()
                final_log_ret = float(np.clip(sample[-1], -0.3, 0.3))
                returns_list.append(np.exp(final_log_ret) - 1.0)

            up_prob = sum(1 for r in returns_list if r > 0) / len(returns_list)
            signals.append(1 if up_prob > 0.55 else 0)

        return pd.Series(signals, index=test_df.index)
