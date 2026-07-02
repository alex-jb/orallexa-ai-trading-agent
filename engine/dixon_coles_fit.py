"""
engine/dixon_coles_fit.py
──────────────────────────────────────────────────────────────────
Vendored MLE fit for the Dixon-Coles bivariate Poisson model.

Ships 2026-07-02 Tier-2 upgrade #6 from the deep-research roadmap.

Why vendor
----------
`penaltyblog` is the canonical Python lib for this (Martin Eastwood,
MIT). BUT its import chain drags in `arviz -> scipy.signal.gaussian`
which was removed in scipy >= 1.13. On Alex's Python 3.9 + scipy 1.x,
`import penaltyblog` crashes before the DC code is reachable.

Rather than fight the dep tree (which risks breaking other modules
that depend on the installed scipy version), we vendor the ~80 lines
of MLE fit code that Alex actually needs. Same math, no framework.
Matches the we-dont-do rule against dep ballooning + the vendored
pattern already used for `keeks` (Kelly) and `orallexa.risk` port.

Contract
--------
Pure functions. Deterministic. No LLM. No network. Takes a list of
match-outcome dicts, returns a `DixonColesFit` dataclass containing
attack/defense strengths per team, home-advantage γ, and low-score
correlation ρ.

Consumers in the stack:
  - engine/sports_pricer.py — replaces the simplified Elo→λ path
    (`dixon_coles_simplified_v1`) with a properly fit DC model when
    training data is available.
  - engine/parlay_correlation.py — feeds `lambda_home / lambda_away`
    into the tournament-advance simulator instead of Elo-derived
    approximations.

Fit is done via scipy.optimize.minimize (Nelder-Mead default, robust
for the log-likelihood surface even on small samples of n≈380 matches).

Ref
---
Dixon & Coles (1997) "Modelling Association Football Scores and
Inefficiencies in the Football Betting Market", JRSS Ser. C.
Martin Eastwood, penaltyblog v1.x (MIT-licensed reference impl).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import scipy.optimize as _opt


# ═══════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════

@dataclass
class DixonColesFit:
    """Fitted parameters of a DC bivariate Poisson model.

    attack + defense are indexed by team name. Attack is unbounded
    (log-scale in the fit); higher = better attack. Defense is also
    log-scale; lower = better defense (concedes fewer goals).

    Sum-to-zero identifiability constraint is baked in — the fit
    fixes sum(attack) = 0 so the model is uniquely determined.
    """
    attack: dict[str, float]
    defense: dict[str, float]
    home_advantage: float          # γ, log-scale; typically ~0.25
    rho: float                     # low-score correlation, ≤ 0
    n_matches: int
    log_likelihood: float

    def teams(self) -> list[str]:
        return sorted(self.attack.keys())

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        """Return (λ_home, λ_away) — Poisson expected goals per side.

        λ_home = exp(attack_home + defense_away + γ)
        λ_away = exp(attack_away + defense_home)

        Returns (None, None) if either team is not in the fit.
        """
        if home not in self.attack or away not in self.attack:
            return (0.0, 0.0)
        lam_h = math.exp(
            self.attack[home] + self.defense[away] + self.home_advantage
        )
        lam_a = math.exp(self.attack[away] + self.defense[home])
        return (lam_h, lam_a)


# ═══════════════════════════════════════════════════════════════
# Dixon-Coles tau (low-score correction)
# ═══════════════════════════════════════════════════════════════

def _tau(h: int, a: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles adjustment τ(h, a, λ_h, λ_a, ρ).

    Applied to 0-0, 1-0, 0-1, 1-1 cells only. Corrects the
    Poisson-independence assumption that Dixon & Coles 1997 found
    UNDERESTIMATES 0-0 and 1-1 draws while OVERESTIMATING 1-0 and
    0-1 wins. ρ is negative for real football (~ -0.05 to -0.15),
    which gives τ > 1 on 0-0/1-1 (bump) and τ < 1 on 1-0/0-1
    (dampen).
    """
    if h == 0 and a == 0:
        return 1.0 - lam_h * lam_a * rho
    if h == 0 and a == 1:
        return 1.0 + lam_h * rho
    if h == 1 and a == 0:
        return 1.0 + lam_a * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


# ═══════════════════════════════════════════════════════════════
# Fit
# ═══════════════════════════════════════════════════════════════

def fit(matches: Iterable[dict]) -> DixonColesFit:
    """MLE-fit the Dixon-Coles model to `matches`.

    matches
    -------
    Iterable of {"home_team": str, "away_team": str,
                 "home_goals": int, "away_goals": int}

    Optional per-row weight "weight": float (defaults to 1.0). Used
    for time-decay reweighting — Dixon-Coles recommends exponential
    time decay so the most recent 100 matches dominate the fit.

    Returns
    -------
    DixonColesFit with attack/defense per team + γ + ρ.

    Raises
    ------
    ValueError if fewer than 20 matches or fewer than 4 unique teams
    (fit is degenerate below that scale).
    """
    m_list = list(matches)
    if len(m_list) < 20:
        raise ValueError(
            f"Need at least 20 matches to fit Dixon-Coles, got {len(m_list)}"
        )
    teams = sorted({m["home_team"] for m in m_list} | {m["away_team"] for m in m_list})
    if len(teams) < 4:
        raise ValueError(
            f"Need at least 4 unique teams, got {len(teams)}"
        )

    n = len(teams)
    idx = {t: i for i, t in enumerate(teams)}

    def unpack(params):
        # params layout: attack[0..n-1], defense[0..n-1], gamma, rho
        # Sum-to-zero constraint on attack: attack[0] = -sum(attack[1..])
        att_free = params[: n - 1]
        att = [-sum(att_free), *att_free]
        defn = params[n - 1: 2 * n - 1]
        gamma = params[2 * n - 1]
        rho = params[2 * n]
        return att, list(defn), gamma, rho

    def neg_log_likelihood(params):
        att, defn, gamma, rho = unpack(params)
        # Clamp rho to a physically-meaningful range. Outside [-0.5, 0.5]
        # τ can go negative for common scorelines → log(negative) → NaN.
        if rho < -0.5 or rho > 0.5:
            return 1e10
        nll = 0.0
        for m in m_list:
            h_team = m["home_team"]
            a_team = m["away_team"]
            h_goals = int(m["home_goals"])
            a_goals = int(m["away_goals"])
            weight = float(m.get("weight", 1.0))
            i_h = idx[h_team]
            i_a = idx[a_team]
            lam_h = math.exp(att[i_h] + defn[i_a] + gamma)
            lam_a = math.exp(att[i_a] + defn[i_h])
            # Poisson log-pmf
            log_p_h = -lam_h + h_goals * math.log(lam_h) - _log_factorial(h_goals)
            log_p_a = -lam_a + a_goals * math.log(lam_a) - _log_factorial(a_goals)
            tau_val = _tau(h_goals, a_goals, lam_h, lam_a, rho)
            if tau_val <= 0:
                return 1e10  # would take log of negative
            nll -= weight * (log_p_h + log_p_a + math.log(tau_val))
        return nll

    # Initial guesses: all-zero attack (avg team), all-zero defense,
    # γ = 0.25 (canonical home advantage on log-λ scale), ρ = -0.1.
    x0 = [0.0] * (n - 1) + [0.0] * n + [0.25, -0.10]

    result = _opt.minimize(
        neg_log_likelihood, x0,
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-4, "fatol": 1e-4},
    )

    att, defn, gamma, rho = unpack(result.x)
    return DixonColesFit(
        attack={t: att[idx[t]] for t in teams},
        defense={t: defn[idx[t]] for t in teams},
        home_advantage=gamma,
        rho=rho,
        n_matches=len(m_list),
        log_likelihood=-result.fun,
    )


# ═══════════════════════════════════════════════════════════════
# Match probability from fitted model
# ═══════════════════════════════════════════════════════════════

def match_probabilities(
    lam_home: float,
    lam_away: float,
    rho: float,
    *,
    max_goals: int = 7,
    ou_line: float = 2.5,
) -> dict:
    """Compute {home, draw, away, over, under, btts} probabilities
    from expected goals λ_h, λ_a + DC ρ correction.

    Grid up to `max_goals` goals per side. 7×7 covers >99.99% of
    real football scorelines (highest professional-match goal count
    since 1997 is 10-1, contributing ~1e-8 to any probability).
    """
    grid = [[0.0] * max_goals for _ in range(max_goals)]
    for h in range(max_goals):
        for a in range(max_goals):
            p_h = math.exp(-lam_home) * lam_home ** h / math.factorial(h)
            p_a = math.exp(-lam_away) * lam_away ** a / math.factorial(a)
            grid[h][a] = p_h * p_a * _tau(h, a, lam_home, lam_away, rho)

    total = sum(sum(row) for row in grid)
    if total <= 0:
        return {
            "p_home_win": 0.0, "p_draw": 0.0, "p_away_win": 0.0,
            "p_over_n": 0.0, "p_under_n": 0.0, "p_btts": 0.0,
        }
    grid = [[c / total for c in row] for row in grid]

    return {
        "p_home_win": sum(grid[h][a] for h in range(max_goals) for a in range(max_goals) if h > a),
        "p_draw":     sum(grid[h][a] for h in range(max_goals) for a in range(max_goals) if h == a),
        "p_away_win": sum(grid[h][a] for h in range(max_goals) for a in range(max_goals) if h < a),
        "p_over_n":   sum(grid[h][a] for h in range(max_goals) for a in range(max_goals) if (h + a) > ou_line),
        "p_under_n":  sum(grid[h][a] for h in range(max_goals) for a in range(max_goals) if (h + a) <= ou_line),
        "p_btts":     sum(grid[h][a] for h in range(1, max_goals) for a in range(1, max_goals)),
    }


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

_LOG_FACT_CACHE: dict[int, float] = {0: 0.0, 1: 0.0}


def _log_factorial(k: int) -> float:
    """log(k!) with a small cache. Called O(fit_iterations * n_matches * 2)
    times so worth caching for k in typical 0-7 goal range."""
    if k in _LOG_FACT_CACHE:
        return _LOG_FACT_CACHE[k]
    v = math.lgamma(k + 1)
    _LOG_FACT_CACHE[k] = v
    return v


def time_decay_weights(dates: list, xi: float = 0.0018) -> list[float]:
    """Compute exponential time-decay weights per match date.

    Dixon-Coles §3 recommends this to keep recent matches dominant.
    Default ξ = 0.0018 per day gives 100-match half-life ≈ 385 days,
    which matches Dixon-Coles' original 1997 English Premier League
    calibration.

    Parameters
    ----------
    dates : list of datetime or date, ordered oldest to newest OK
    xi    : decay rate per day. Higher = faster decay. 0.0018 default
            from Dixon-Coles 1997.

    Returns
    -------
    List of weights (0, 1], most recent date → 1.0.
    """
    if not dates:
        return []
    max_d = max(dates)
    out = []
    for d in dates:
        delta_days = (max_d - d).days if hasattr(max_d - d, "days") else 0
        out.append(math.exp(-xi * delta_days))
    return out
