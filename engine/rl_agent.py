"""
engine/rl_agent.py
──────────────────────────────────────────────────────────────────
Reinforcement Learning trading agent using PPO (stable-baselines3).

Custom Gymnasium environment with Sharpe-based reward shaping,
drawdown penalty, and automatic stop-loss.

Usage:
    from engine.rl_agent import RLTrader
    trader = RLTrader(total_timesteps=20000)
    trader.train(train_df)
    signal = trader.predict(test_df)  # pd.Series of {0, 1}
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from core.logger import get_logger

logger = get_logger("rl_agent")

# Features the RL agent observes (subset of TechnicalAnalysisSkillV2 output)
RL_FEATURES = [
    "RSI", "MACD_Hist", "BB_Pct", "ADX", "Volume_Ratio",
    "Stoch_K", "ROC", "ATR_Pct", "HV20", "OBV",
]

# ── Risk parameters ──
STOP_LOSS_PCT = 0.05       # -5% hard stop
TAKE_PROFIT_PCT = 0.10     # +10% take profit
TRANSACTION_COST = 0.001   # 0.1% per trade


def _build_env(df: pd.DataFrame, features: list[str], initial_balance: float = 100000.0):
    """Create a TradingEnv with Sharpe-based reward shaping."""
    import gymnasium as gym

    available = [f for f in features if f in df.columns]
    if len(available) < 3:
        return None

    class TradingEnv(gym.Env):
        """
        Single-stock trading environment.
        Actions: 0=hold, 1=buy, 2=sell
        Reward: daily risk-adjusted return with drawdown penalty.
        """
        metadata = {"render_modes": []}

        def __init__(self):
            super().__init__()
            self.df = df.reset_index(drop=True)
            self.features = available
            self.initial_balance = initial_balance
            self.window = 10

            # Observation: window of (features + position + unrealized_pnl + drawdown)
            self.observation_space = gym.spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.window, len(self.features) + 3),
                dtype=np.float32,
            )
            self.action_space = gym.spaces.Discrete(3)
            self.reset()

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.step_idx = self.window
            self.balance = self.initial_balance
            self.position = 0
            self.entry_price = 0.0
            self.portfolio_values = [self.initial_balance]
            self.peak_value = self.initial_balance
            self.trade_returns = []
            return self._obs(), {}

        def _portfolio_value(self) -> float:
            price = float(self.df["Close"].iloc[min(self.step_idx, len(self.df) - 1)])
            return self.balance + self.position * price

        def _obs(self):
            # Use data up to previous day to avoid lookahead bias
            end = max(1, self.step_idx)
            start = max(0, end - self.window)
            feat_data = self.df[self.features].iloc[start:end].values.copy()

            # Replace NaN/Inf with 0 to prevent gradient explosion
            feat_data = np.nan_to_num(feat_data, nan=0.0, posinf=0.0, neginf=0.0)

            # Z-score normalization within window
            mean = feat_data.mean(axis=0, keepdims=True)
            std = feat_data.std(axis=0, keepdims=True) + 1e-8
            feat_norm = np.clip((feat_data - mean) / std, -5.0, 5.0)  # clip extreme z-scores

            n_rows = len(feat_norm)

            # Position state: 1 if holding, 0 if flat
            pos_col = np.full((n_rows, 1), 1.0 if self.position > 0 else 0.0)

            # Unrealized PnL (scaled)
            pnl_col = np.zeros((n_rows, 1))
            if self.position > 0:
                current = float(self.df["Close"].iloc[min(self.step_idx - 1, len(self.df) - 1)])
                pnl_col[-1, 0] = (current / self.entry_price - 1.0) * 10

            # Current drawdown from peak
            dd_col = np.zeros((n_rows, 1))
            pv = self._portfolio_value()
            dd_col[-1, 0] = (pv / self.peak_value - 1.0) * 10 if self.peak_value > 0 else 0.0

            obs = np.hstack([feat_norm, pos_col, pnl_col, dd_col]).astype(np.float32)

            # Pad if window not full
            if obs.shape[0] < self.window:
                pad = np.zeros((self.window - obs.shape[0], obs.shape[1]), dtype=np.float32)
                obs = np.vstack([pad, obs])

            return obs

        def _execute_sell(self, price: float) -> float:
            """Execute sell, return reward."""
            proceeds = self.position * price * (1 - TRANSACTION_COST)
            pnl_pct = (price / self.entry_price - 1.0)
            self.trade_returns.append(pnl_pct)
            self.balance += proceeds
            self.position = 0
            self.entry_price = 0.0
            return pnl_pct

        def step(self, action):
            if self.step_idx >= len(self.df) - 1:
                return self._obs(), 0.0, True, False, {}

            price = float(self.df["Close"].iloc[self.step_idx])
            reward = 0.0

            # ── Auto stop-loss / take-profit ──
            if self.position > 0:
                unrealized = price / self.entry_price - 1.0
                if unrealized <= -STOP_LOSS_PCT:
                    reward = self._execute_sell(price) - 0.01  # extra penalty for hitting stop
                    action = 0  # override action
                elif unrealized >= TAKE_PROFIT_PCT:
                    reward = self._execute_sell(price) + 0.005  # bonus for taking profit
                    action = 0

            # ── Execute action (if not overridden by stop) ──
            if action == 1 and self.position == 0:  # BUY
                shares = int(self.balance * 0.95 / (price * (1 + TRANSACTION_COST)))
                if shares > 0:
                    cost = shares * price * (1 + TRANSACTION_COST)
                    self.position = shares
                    self.entry_price = price
                    self.balance -= cost
                    reward = -TRANSACTION_COST  # cost penalty

            elif action == 2 and self.position > 0:  # SELL
                reward = self._execute_sell(price)

            elif action == 0:  # HOLD
                if self.position > 0:
                    # Daily return as reward (risk-adjusted)
                    if self.step_idx > self.window:
                        prev_price = float(self.df["Close"].iloc[self.step_idx - 1])
                        daily_ret = (price / prev_price - 1.0)
                        reward = daily_ret  # direct daily return
                # Holding flat: small negative to discourage sitting out forever
                elif self.step_idx > self.window + 20:
                    reward = -0.0001

            # ── Drawdown penalty ──
            pv = self._portfolio_value()
            self.peak_value = max(self.peak_value, pv)
            drawdown = (pv / self.peak_value - 1.0)
            if drawdown < -0.05:
                reward += drawdown * 0.1  # penalize large drawdowns

            self.portfolio_values.append(pv)
            self.step_idx += 1
            done = self.step_idx >= len(self.df) - 1

            # Force close at end
            if done and self.position > 0:
                reward += self._execute_sell(price)

            # ── Terminal Sharpe bonus ──
            if done and len(self.trade_returns) >= 3:
                returns = np.array(self.trade_returns)
                sharpe = float(returns.mean() / (returns.std() + 1e-8)) * np.sqrt(252)
                reward += max(sharpe * 0.01, 0)  # bonus for positive Sharpe

            return self._obs(), float(reward), done, False, {}

    return TradingEnv()


class RLTrader:
    """PPO-based RL trading agent with stability safeguards.

    Stability features:
        - Multi-seed training with best-of-N selection
        - Gradient norm clipping (max_grad_norm=0.5)
        - Training convergence check via reward trajectory
        - Inference latency guard (<100ms per step)
    """

    N_SEEDS = 3              # train N models, pick best
    MAX_INFERENCE_MS = 100   # warn if inference exceeds this

    def __init__(self, total_timesteps: int = 20000):
        self.total_timesteps = total_timesteps
        self.model = None
        self.features = RL_FEATURES
        self.train_reward: float = 0.0  # final reward from best seed

    def train(self, train_df: pd.DataFrame) -> bool:
        """Train PPO with multi-seed selection. Returns True if successful."""
        try:
            from stable_baselines3 import PPO
            from stable_baselines3.common.vec_env import DummyVecEnv
            from stable_baselines3.common.callbacks import BaseCallback
            import time as _time

            env = _build_env(train_df, self.features)
            if env is None:
                logger.warning("RL: Not enough features to build env")
                return False

            best_model = None
            best_reward = -np.inf

            class RewardTracker(BaseCallback):
                """Track episode rewards for convergence monitoring."""
                def __init__(self):
                    super().__init__()
                    self.episode_rewards: list[float] = []

                def _on_step(self) -> bool:
                    infos = self.locals.get("infos", [])
                    for info in infos:
                        if "episode" in info:
                            self.episode_rewards.append(info["episode"]["r"])
                    return True

            for seed in range(self.N_SEEDS):
                vec_env = DummyVecEnv([lambda: _build_env(train_df, self.features)])
                tracker = RewardTracker()
                model = PPO(
                    "MlpPolicy", vec_env,
                    n_steps=64,
                    batch_size=32,
                    n_epochs=10,
                    learning_rate=3e-4,
                    gamma=0.99,
                    gae_lambda=0.95,
                    clip_range=0.2,
                    ent_coef=0.01,
                    max_grad_norm=0.5,
                    verbose=0,
                    seed=42 + seed,
                    policy_kwargs={"net_arch": [128, 64]},
                )
                model.learn(
                    total_timesteps=self.total_timesteps,
                    callback=tracker,
                )

                # Evaluate: run one episode to get final reward
                eval_env = _build_env(train_df, self.features)
                if eval_env is None:
                    continue
                obs, _ = eval_env.reset()
                total_reward = 0.0
                for _ in range(len(train_df)):
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, done, _, _ = eval_env.step(action)
                    total_reward += reward
                    if done:
                        break

                # Convergence check: reward should trend upward
                if tracker.episode_rewards:
                    n = len(tracker.episode_rewards)
                    if n >= 4:
                        first_half = np.mean(tracker.episode_rewards[:n//2])
                        second_half = np.mean(tracker.episode_rewards[n//2:])
                        if second_half < first_half * 0.8:
                            logger.warning("RL seed %d: reward declined (%.2f -> %.2f), skipping",
                                           seed, first_half, second_half)
                            continue

                logger.info("RL seed %d: total_reward=%.4f", seed, total_reward)
                if total_reward > best_reward:
                    best_reward = total_reward
                    best_model = model

            if best_model is None:
                logger.warning("RL: all seeds failed convergence check")
                return False

            self.model = best_model
            self.train_reward = best_reward
            logger.info("RL PPO trained: %d timesteps x %d seeds, best_reward=%.4f",
                        self.total_timesteps, self.N_SEEDS, best_reward)
            return True
        except Exception as e:
            logger.warning("RL training failed: %s", e)
            return False

    def predict(self, test_df: pd.DataFrame) -> Optional[pd.Series]:
        """Generate trading signals with inference latency guard."""
        if self.model is None:
            return None

        import time as _time

        env = _build_env(test_df, self.features)
        if env is None:
            return None

        obs, _ = env.reset()
        signals = []
        slow_steps = 0
        for _ in range(len(test_df)):
            t0 = _time.perf_counter()
            action, _ = self.model.predict(obs, deterministic=True)
            dt_ms = (_time.perf_counter() - t0) * 1000
            if dt_ms > self.MAX_INFERENCE_MS:
                slow_steps += 1

            obs, _, done, _, _ = env.step(action)
            signals.append(1 if action == 1 or (action == 0 and env.position > 0) else 0)
            if done:
                break

        if slow_steps > 0:
            logger.warning("RL inference: %d/%d steps exceeded %dms",
                           slow_steps, len(signals), self.MAX_INFERENCE_MS)

        # Pad to match test_df length
        while len(signals) < len(test_df):
            signals.append(0)
        signals = signals[:len(test_df)]

        return pd.Series(signals, index=test_df.index)
