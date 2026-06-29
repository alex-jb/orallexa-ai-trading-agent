"""
engine/sports_pricer.py
──────────────────────────────────────────────────────────────────
Football match probability pricer using penaltyblog's Dixon-Coles
+ bivariate Poisson models.

Why this exists:
  - 2026-06-22 Polymarket cron audit found Haiku's our_p_yes was
    returning uniform ~0.15 for every market regardless of content.
    Root cause: Haiku has no actual football model — just a token
    probability fallback.
  - This module replaces our_p_yes for sports legs with a real
    statistical model trained on recent xG + Elo data.

Architecture mirror of engine/insider_signal.py:
  - Pure-function, deterministic
  - No LLM call inside the hot path
  - Pluggable: any caller producing a (home, away, league) tuple
    gets back a typed match-prob dict
  - Graceful fallback: missing data → return None → caller falls
    back to existing Haiku our_p_yes

Inputs come from markets/auto/sports_morning.py JSONL bus.

Output dict shape:
  {
    "p_home_win": 0.48,
    "p_draw":     0.27,
    "p_away_win": 0.25,
    "p_over_2_5": 0.51,
    "p_under_2_5":0.49,
    "p_btts":     0.55,
    "lambda_home":1.42,  # expected goals
    "lambda_away":1.18,
    "model":      "dixon_coles_v1",
    "trained_on": "FBref 2024-25 + 2025-26 (n=380)",
    "fetched_at": "2026-06-29T13:00:00Z"
  }

Then for tournament-stage markets (e.g. "Spain advance to R16"), use
engine.parlay_correlation.simulate_tournament_advance(team) instead —
single-match probability is the wrong granularity for those legs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


HOME = Path.home()
SPORTS_BUS = (
    HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain"
    / "research" / "markets-sports"
)

# Polymarket markets occasionally have "score exactly N" or "btts" props;
# this constant lets sizing.py treat the over/under threshold as
# explicitly parameterized rather than hardcoded.
DEFAULT_OU_LINE = 2.5


@dataclass
class MatchPrediction:
    p_home_win: float
    p_draw: float
    p_away_win: float
    p_over_n: float
    p_under_n: float
    p_btts: float
    lambda_home: float
    lambda_away: float
    ou_line: float
    model: str
    trained_on: str
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    def for_polymarket_leg(self, leg_type: str) -> Optional[float]:
        """Map a Polymarket leg label to the right probability.

        leg_type ∈ {
          "home_win", "draw", "away_win",
          "over", "under", "btts",
          "double_chance_home", "double_chance_away"
        }
        """
        m = {
            "home_win": self.p_home_win,
            "draw": self.p_draw,
            "away_win": self.p_away_win,
            "over": self.p_over_n,
            "under": self.p_under_n,
            "btts": self.p_btts,
            "double_chance_home": self.p_home_win + self.p_draw,
            "double_chance_away": self.p_away_win + self.p_draw,
        }
        return m.get(leg_type)


def _load_today_matches() -> list[dict]:
    """Read the latest sports_morning.py JSONL output."""
    if not SPORTS_BUS.exists():
        return []
    files = sorted(SPORTS_BUS.glob("*.jsonl"), reverse=True)
    if not files:
        return []
    matches: list[dict] = []
    with files[0].open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if "_meta" in row:
                    continue  # skip the empty-day stub
                matches.append(row)
            except json.JSONDecodeError:
                continue
    return matches


def _fit_dixon_coles(matches: list[dict]):
    """Wrap penaltyblog Dixon-Coles fit. Returns model or None."""
    try:
        import penaltyblog as pb  # type: ignore
    except ImportError:
        return None
    if not matches:
        return None
    # penaltyblog wants a DataFrame with cols: home_team, away_team,
    # home_goals, away_goals, date. We use FBref historical match results
    # via soccerdata for training, NOT the upcoming-fixture rows.
    # For now, this is a stub call site — the caller should pass a
    # training dataframe. Returns the fit model or None.
    return None


def predict_match(
    home: str,
    away: str,
    *,
    elo_home: Optional[float] = None,
    elo_away: Optional[float] = None,
    xg_recent_home: Optional[float] = None,
    xg_recent_away: Optional[float] = None,
    ou_line: float = DEFAULT_OU_LINE,
) -> Optional[MatchPrediction]:
    """Produce a Dixon-Coles match prediction for a single fixture.

    If penaltyblog isn't installed OR we don't have enough data,
    returns None — caller (typically markets/polymarket_daily.py)
    falls back to the existing Haiku our_p_yes path.

    For now, this implements a SIMPLIFIED Dixon-Coles using Elo as
    the team-strength proxy (no historical match training needed).
    The full penaltyblog version requires the model fit + season of
    historical scorelines — that lands in v0.2 of this module.
    """
    if elo_home is None or elo_away is None:
        return None

    # Simplified strength: Elo difference → expected-goals difference.
    # Calibration constants are eyeball estimates from FBref 2024-25
    # benchmark; v0.2 will fit these via penaltyblog on real data.
    elo_diff = (elo_home - elo_away) / 400.0  # standard Elo scale
    base_lambda = 1.35  # league-average goals per side per match
    home_advantage = 0.25  # home_team scores 0.25 more on average
    lam_home = max(0.05, base_lambda * (10 ** (elo_diff / 2)) + home_advantage)
    lam_away = max(0.05, base_lambda / (10 ** (elo_diff / 2)))

    # Override with recent xG if we have it — much better signal than Elo
    # alone, especially after a transfer window or a coaching change.
    if xg_recent_home is not None and xg_recent_home > 0:
        lam_home = 0.6 * lam_home + 0.4 * xg_recent_home
    if xg_recent_away is not None and xg_recent_away > 0:
        lam_away = 0.6 * lam_away + 0.4 * xg_recent_away

    # Dixon-Coles outcome probabilities via Poisson grid up to 6 goals
    # per side (covers >99.99% of football scorelines).
    try:
        import math
        max_goals = 7
        p_grid = [[0.0] * max_goals for _ in range(max_goals)]
        for h in range(max_goals):
            for a in range(max_goals):
                p_grid[h][a] = (
                    (math.exp(-lam_home) * lam_home ** h / math.factorial(h))
                    * (math.exp(-lam_away) * lam_away ** a / math.factorial(a))
                )
        # Apply Dixon-Coles low-score correlation correction (rho ≈ -0.1
        # is the canonical value from Dixon & Coles 1997 §3.2). Bumps
        # the 0-0, 1-0, 0-1 cells, dampens 1-1.
        rho = -0.10
        p_grid[0][0] *= (1 - lam_home * lam_away * rho)
        p_grid[0][1] *= (1 + lam_home * rho)
        p_grid[1][0] *= (1 + lam_away * rho)
        p_grid[1][1] *= (1 - rho)

        total = sum(sum(row) for row in p_grid)
        if total <= 0:
            return None
        # Renormalize
        p_grid = [[c / total for c in row] for row in p_grid]

        p_home_win = sum(p_grid[h][a] for h in range(max_goals) for a in range(max_goals) if h > a)
        p_draw     = sum(p_grid[h][a] for h in range(max_goals) for a in range(max_goals) if h == a)
        p_away_win = sum(p_grid[h][a] for h in range(max_goals) for a in range(max_goals) if h < a)
        p_over_n   = sum(p_grid[h][a] for h in range(max_goals) for a in range(max_goals) if (h + a) > ou_line)
        p_under_n  = 1.0 - p_over_n
        p_btts     = sum(p_grid[h][a] for h in range(1, max_goals) for a in range(1, max_goals))
    except Exception:
        return None

    return MatchPrediction(
        p_home_win=round(p_home_win, 4),
        p_draw=round(p_draw, 4),
        p_away_win=round(p_away_win, 4),
        p_over_n=round(p_over_n, 4),
        p_under_n=round(p_under_n, 4),
        p_btts=round(p_btts, 4),
        lambda_home=round(lam_home, 3),
        lambda_away=round(lam_away, 3),
        ou_line=ou_line,
        model="dixon_coles_simplified_v1",
        trained_on=(
            "Elo (ClubElo) + xG recent (FBref) — "
            "penaltyblog full-fit upgrade pending v0.2"
        ),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def get_prediction_for_fixture(
    home: str, away: str, *, ou_line: float = DEFAULT_OU_LINE
) -> Optional[MatchPrediction]:
    """Convenience wrapper that pulls today's row from the JSONL bus."""
    rows = _load_today_matches()
    home_l, away_l = home.lower(), away.lower()
    for r in rows:
        if r.get("home", "").lower() == home_l and r.get("away", "").lower() == away_l:
            return predict_match(
                home, away,
                elo_home=r.get("elo_home"),
                elo_away=r.get("elo_away"),
                xg_recent_home=r.get("xg_recent_home"),
                xg_recent_away=r.get("xg_recent_away"),
                ou_line=ou_line,
            )
    # Reverse match (in case the user passed teams in opposite order)
    for r in rows:
        if r.get("home", "").lower() == away_l and r.get("away", "").lower() == home_l:
            mirrored = predict_match(
                away, home,
                elo_home=r.get("elo_home"),
                elo_away=r.get("elo_away"),
                xg_recent_home=r.get("xg_recent_home"),
                xg_recent_away=r.get("xg_recent_away"),
                ou_line=ou_line,
            )
            if mirrored:
                # Swap home/away in the result
                return MatchPrediction(
                    p_home_win=mirrored.p_away_win,
                    p_draw=mirrored.p_draw,
                    p_away_win=mirrored.p_home_win,
                    p_over_n=mirrored.p_over_n,
                    p_under_n=mirrored.p_under_n,
                    p_btts=mirrored.p_btts,
                    lambda_home=mirrored.lambda_away,
                    lambda_away=mirrored.lambda_home,
                    ou_line=mirrored.ou_line,
                    model=mirrored.model,
                    trained_on=mirrored.trained_on,
                    fetched_at=mirrored.fetched_at,
                )
            return None
    return None
