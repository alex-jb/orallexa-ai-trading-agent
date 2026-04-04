"""
engine/micro_swarm.py
──────────────────────────────────────────────────────────────────
Lightweight Agent Swarm for scenario convergence testing.

Simulates 20 rule-based market agents with different behavioral
profiles reacting to a price shock or news event. No LLM needed —
pure rule-based agents with simple behavioral models.

Inspired by MiroFish's OASIS simulation, simplified to a fast
local Monte Carlo that runs in <1 second.

Agent types:
  - Momentum traders (5): buy breakouts, sell breakdowns
  - Mean reversion (5): fade extremes
  - News reactors (3): amplify or fade news sentiment
  - Institutional (3): slow, large, trend-following
  - Retail herd (4): FOMO/panic, follow momentum with delay

Usage:
    from engine.micro_swarm import run_swarm_simulation
    result = run_swarm_simulation(
        shock_pct=-5.0,
        sentiment=-0.6,
        rsi=72,
        adx=30,
    )
    print(result["convergence"])     # "SELL" / "BUY" / "MIXED"
    print(result["convergence_speed"])  # how fast agents agreed
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

STEPS = 50
N_SIMULATIONS = 100  # Monte Carlo runs


@dataclass
class SwarmAgent:
    """A single rule-based market agent."""
    name: str
    agent_type: str
    risk_appetite: float     # 0-1 (0 = conservative, 1 = aggressive)
    reaction_speed: int      # steps before reacting (0 = instant)
    contrarian: bool         # True = fades moves, False = follows
    position: float = 0.0   # -1 (full short) to +1 (full long)
    noise: float = 0.1      # random noise level

    def react(self, price_change: float, sentiment: float, step: int, crowd_position: float) -> float:
        """Update position based on market state. Returns new position [-1, +1]."""
        if step < self.reaction_speed:
            return self.position

        signal = 0.0

        if self.agent_type == "momentum":
            # Follow price direction, stronger with trend
            signal = np.sign(price_change) * min(abs(price_change) * 20, 1.0)
            signal *= self.risk_appetite

        elif self.agent_type == "mean_reversion":
            # Fade extreme moves
            if abs(price_change) > 0.01:
                signal = -np.sign(price_change) * min(abs(price_change) * 15, 1.0)
            signal *= self.risk_appetite

        elif self.agent_type == "news_reactor":
            # React to sentiment
            signal = sentiment * self.risk_appetite * 1.2
            if self.contrarian:
                signal *= -0.7

        elif self.agent_type == "institutional":
            # Slow, trend-following, large moves
            signal = np.sign(price_change) * 0.5 * self.risk_appetite
            # Mean revert if crowd is too extreme
            if abs(crowd_position) > 0.7:
                signal -= crowd_position * 0.2

        elif self.agent_type == "retail":
            # FOMO / panic: follow crowd with delay and amplification
            signal = crowd_position * 1.0 * self.risk_appetite
            # Panic amplification on big moves
            if abs(price_change) > 0.02:
                signal += np.sign(price_change) * 0.5

        # Add noise
        signal += np.random.normal(0, self.noise)

        # Smooth transition (agents don't flip instantly)
        new_pos = self.position * 0.4 + signal * 0.6
        self.position = max(-1.0, min(1.0, new_pos))
        return self.position


def _create_agents() -> list[SwarmAgent]:
    """Create the 20-agent swarm."""
    agents = []

    # 5 Momentum traders
    for i in range(5):
        agents.append(SwarmAgent(
            name=f"Momentum_{i+1}", agent_type="momentum",
            risk_appetite=0.5 + i * 0.1, reaction_speed=0,
            contrarian=False, noise=0.08 + i * 0.02,
        ))

    # 5 Mean reversion
    for i in range(5):
        agents.append(SwarmAgent(
            name=f"MeanRev_{i+1}", agent_type="mean_reversion",
            risk_appetite=0.4 + i * 0.1, reaction_speed=1 + i,
            contrarian=True, noise=0.1,
        ))

    # 3 News reactors
    for i in range(3):
        agents.append(SwarmAgent(
            name=f"News_{i+1}", agent_type="news_reactor",
            risk_appetite=0.6 + i * 0.1, reaction_speed=0,
            contrarian=(i == 2), noise=0.12,
        ))

    # 3 Institutional
    for i in range(3):
        agents.append(SwarmAgent(
            name=f"Inst_{i+1}", agent_type="institutional",
            risk_appetite=0.3 + i * 0.1, reaction_speed=3 + i * 2,
            contrarian=False, noise=0.05,
        ))

    # 4 Retail herd
    for i in range(4):
        agents.append(SwarmAgent(
            name=f"Retail_{i+1}", agent_type="retail",
            risk_appetite=0.7 + i * 0.05, reaction_speed=2 + i,
            contrarian=False, noise=0.15,
        ))

    return agents


def _run_single_simulation(
    shock_pct: float,
    sentiment: float,
    rsi: float,
    adx: float,
    steps: int = STEPS,
) -> dict:
    """Run one simulation of the swarm reacting to a shock."""
    agents = _create_agents()

    # Normalize inputs
    price_change = shock_pct / 100.0
    sent_norm = max(-1, min(1, sentiment))

    # Adjust agent behavior based on market state
    if rsi > 70:
        # Overbought: mean reversion agents get more aggressive
        for a in agents:
            if a.agent_type == "mean_reversion":
                a.risk_appetite *= 1.3
    elif rsi < 30:
        # Oversold: momentum agents cautious, mean reversion aggressive
        for a in agents:
            if a.agent_type == "mean_reversion":
                a.risk_appetite *= 1.3
            elif a.agent_type == "momentum":
                a.risk_appetite *= 0.7

    if adx > 25:
        # Strong trend: momentum agents more confident
        for a in agents:
            if a.agent_type == "momentum":
                a.risk_appetite *= 1.2

    # Run simulation
    position_history = []
    convergence_step = None

    for step in range(steps):
        # Dampen the shock over time
        current_shock = price_change * (0.9 ** step)

        # Crowd position (average of all agents)
        crowd_pos = sum(a.position for a in agents) / len(agents)

        # Each agent reacts
        for agent in agents:
            agent.react(current_shock, sent_norm, step, crowd_pos)

        # Record crowd state
        positions = [a.position for a in agents]
        avg_pos = sum(positions) / len(positions)
        bullish = sum(1 for p in positions if p > 0.1)
        bearish = sum(1 for p in positions if p < -0.1)
        neutral = len(positions) - bullish - bearish

        position_history.append({
            "step": step,
            "avg_position": round(avg_pos, 3),
            "bullish_pct": round(bullish / len(agents) * 100),
            "bearish_pct": round(bearish / len(agents) * 100),
            "neutral_pct": round(neutral / len(agents) * 100),
        })

        # Check convergence (>70% agree)
        if convergence_step is None:
            max_agree = max(bullish, bearish)
            if max_agree / len(agents) >= 0.7:
                convergence_step = step

    # Final state
    final = position_history[-1]
    return {
        "final_position": final["avg_position"],
        "bullish_pct": final["bullish_pct"],
        "bearish_pct": final["bearish_pct"],
        "neutral_pct": final["neutral_pct"],
        "convergence_step": convergence_step,
        "position_history": position_history,
    }


def run_swarm_simulation(
    shock_pct: float = 0.0,
    sentiment: float = 0.0,
    rsi: float = 50.0,
    adx: float = 20.0,
    n_simulations: int = N_SIMULATIONS,
    ticker: str = "",
) -> dict:
    """
    Run Monte Carlo swarm simulation.

    Parameters
    ----------
    shock_pct    : initial price shock (-10 to +10)
    sentiment    : news sentiment (-1 to +1)
    rsi          : current RSI (0-100)
    adx          : current ADX (0-100)
    n_simulations: number of Monte Carlo runs

    Returns
    -------
    dict with keys:
        convergence       : "SELL" / "BUY" / "MIXED"
        conviction        : 0-100
        convergence_speed : "fast" / "medium" / "slow" / "none"
        avg_steps         : average steps to convergence
        sell_pct          : % of simulations converging to sell
        buy_pct           : % of simulations converging to buy
        agent_breakdown   : per-type final position summary
        sample_path       : one representative simulation path
    """
    results = []
    for _ in range(n_simulations):
        results.append(_run_single_simulation(shock_pct, sentiment, rsi, adx))

    # Aggregate
    final_positions = [r["final_position"] for r in results]
    avg_final = sum(final_positions) / len(final_positions)
    convergence_steps = [r["convergence_step"] for r in results if r["convergence_step"] is not None]

    # Use agent distribution from each simulation (not just avg position)
    buy_converge = sum(1 for r in results if r["bullish_pct"] > r["bearish_pct"] + 15)
    sell_converge = sum(1 for r in results if r["bearish_pct"] > r["bullish_pct"] + 15)
    mixed = n_simulations - buy_converge - sell_converge

    buy_pct = round(buy_converge / n_simulations * 100)
    sell_pct = round(sell_converge / n_simulations * 100)

    if buy_pct > 60:
        convergence = "BUY"
    elif sell_pct > 60:
        convergence = "SELL"
    else:
        convergence = "MIXED"

    conviction = max(buy_pct, sell_pct)

    # Speed
    if convergence_steps:
        avg_steps = sum(convergence_steps) / len(convergence_steps)
        if avg_steps < 10:
            speed = "fast"
        elif avg_steps < 25:
            speed = "medium"
        else:
            speed = "slow"
    else:
        avg_steps = STEPS
        speed = "none"

    # Agent type breakdown from the last simulation
    last_sim = results[-1]
    agents = _create_agents()
    # Re-run last to get per-agent data
    last_run = _run_single_simulation(shock_pct, sentiment, rsi, adx)

    # Sample path (downsample to 10 points for frontend)
    sample = results[0]["position_history"]
    step_size = max(1, len(sample) // 10)
    sample_path = [sample[i] for i in range(0, len(sample), step_size)][:10]

    return {
        "ticker": ticker,
        "convergence": convergence,
        "conviction": conviction,
        "convergence_speed": speed,
        "avg_steps_to_converge": round(avg_steps, 1),
        "buy_pct": buy_pct,
        "sell_pct": sell_pct,
        "mixed_pct": round(mixed / n_simulations * 100),
        "n_simulations": n_simulations,
        "avg_final_position": round(avg_final, 3),
        "inputs": {
            "shock_pct": shock_pct,
            "sentiment": sentiment,
            "rsi": rsi,
            "adx": adx,
        },
        "sample_path": sample_path,
    }
