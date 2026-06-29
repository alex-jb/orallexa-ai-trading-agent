"""
eval/backtest_sports.py
──────────────────────────────────────────────────────────────────
Brier-score backtest of engine.sports_pricer.predict_match against
StatsBomb open-data historical matches.

Why this exists:
  Sports edge claims are easy to fake on small samples. Before any
  paper-trade $ goes through Orallexa's sports leg, this harness
  computes the Brier score of predict_match() across hundreds of
  past matches with known outcomes — the same OOS-Sharpe-gate
  discipline as engine/walkforward.py imposed on the markets stack
  (which caught -3.08 mean Sharpe = SKIP signal 2026-06-09).

Pattern mirror:
  - eval/harness.py (general loader)
  - eval/decision_eval.py (Brier on decisions)
  - markets/brier_audit.py (live Brier on Polymarket calls)

Usage:
  python -m eval.backtest_sports --competition "FIFA World Cup" --year 2022
  python -m eval.backtest_sports --all

Output:
  eval/history/sports-backtest-YYYY-MM-DD-HHMMSS.json
  + appended summary in eval/history/sports-SUMMARY.md

Decision gate (mirroring markets walkforward):
  - Brier < 0.20 → GO (model beats baseline of always-50/50)
  - Brier 0.20-0.25 → WAIT (marginal edge, need more data)
  - Brier > 0.25 → SKIP (model worse than baseline, do NOT bet)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from engine.sports_pricer import predict_match
except ImportError:
    # Allow running standalone for sanity checks
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engine.sports_pricer import predict_match


HISTORY_DIR = Path(__file__).resolve().parent / "history"


def load_statsbomb_matches(competition: str, year: int) -> list[dict]:
    """Pull historical matches with known final scores from StatsBomb."""
    try:
        from statsbombpy import sb  # type: ignore
    except ImportError:
        print("[backtest-sports] statsbombpy not installed.", file=sys.stderr)
        return []
    try:
        comps = sb.competitions()
        match = comps[
            (comps["competition_name"] == competition)
            & (comps["season_name"].astype(str).str.contains(str(year)))
        ]
        if match.empty:
            print(f"[backtest-sports] no StatsBomb season for {competition} {year}",
                  file=sys.stderr)
            return []
        comp_id = int(match.iloc[0]["competition_id"])
        season_id = int(match.iloc[0]["season_id"])
        ms = sb.matches(competition_id=comp_id, season_id=season_id)
        rows = []
        for _, m in ms.iterrows():
            home = str(m.get("home_team", ""))
            away = str(m.get("away_team", ""))
            hg = int(m.get("home_score", 0))
            ag = int(m.get("away_score", 0))
            if not home or not away:
                continue
            rows.append({
                "competition": competition,
                "year": year,
                "home": home,
                "away": away,
                "home_goals": hg,
                "away_goals": ag,
            })
        return rows
    except Exception as exc:
        print(f"[backtest-sports] StatsBomb fetch failed: {exc}", file=sys.stderr)
        return []


def _team_elo_lookup_stub(matches: list[dict]) -> dict[str, float]:
    """Compute a quick Elo lookup from the match list itself (poor proxy
    but works without external data). For a real backtest, replace with
    a soccerdata.ClubElo() pull keyed on the match dates."""
    elo: dict[str, float] = {}
    for m in matches:
        elo.setdefault(m["home"], 1500.0)
        elo.setdefault(m["away"], 1500.0)
    # One pass of K=20 Elo updates over the match list
    K = 20.0
    for m in matches:
        e_h = elo[m["home"]]
        e_a = elo[m["away"]]
        # Expected score with 0.25 home advantage
        exp_h = 1.0 / (1.0 + 10 ** ((e_a - e_h - 100) / 400))
        if m["home_goals"] > m["away_goals"]:
            actual_h = 1.0
        elif m["home_goals"] < m["away_goals"]:
            actual_h = 0.0
        else:
            actual_h = 0.5
        elo[m["home"]] = e_h + K * (actual_h - exp_h)
        elo[m["away"]] = e_a + K * ((1 - actual_h) - (1 - exp_h))
    return elo


def brier_3way(p_h: float, p_d: float, p_a: float, outcome: str) -> float:
    """Multi-class Brier: sum of squared errors across the 3 outcomes.
    outcome ∈ {'H', 'D', 'A'}. Range: 0 (perfect) to 2 (worst).
    Divide by 2 for the 0-1 normalized variant used in much of the
    sports-betting literature."""
    truth = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[outcome]
    pred = (p_h, p_d, p_a)
    return sum((pred[i] - truth[i]) ** 2 for i in range(3)) / 2.0


def run_backtest(matches: list[dict]) -> dict:
    """Score every match with predict_match() and compute mean Brier."""
    if not matches:
        return {
            "n": 0, "mean_brier": None, "verdict": "no-data",
            "matches_scored": 0,
        }

    elo = _team_elo_lookup_stub(matches)
    n_scored = 0
    brier_sum = 0.0
    per_match: list[dict] = []

    for m in matches:
        pred = predict_match(
            m["home"], m["away"],
            elo_home=elo[m["home"]],
            elo_away=elo[m["away"]],
        )
        if pred is None:
            continue
        if m["home_goals"] > m["away_goals"]:
            outcome = "H"
        elif m["home_goals"] < m["away_goals"]:
            outcome = "A"
        else:
            outcome = "D"
        b = brier_3way(pred.p_home_win, pred.p_draw, pred.p_away_win, outcome)
        brier_sum += b
        n_scored += 1
        per_match.append({
            "home": m["home"],
            "away": m["away"],
            "score": f"{m['home_goals']}-{m['away_goals']}",
            "outcome": outcome,
            "p_h": pred.p_home_win,
            "p_d": pred.p_draw,
            "p_a": pred.p_away_win,
            "brier": round(b, 4),
        })

    mean_brier = brier_sum / n_scored if n_scored else None

    # Decision gate
    if mean_brier is None:
        verdict = "no-data"
    elif mean_brier < 0.20:
        verdict = "GO"
    elif mean_brier < 0.25:
        verdict = "WAIT"
    else:
        verdict = "SKIP"

    return {
        "n": len(matches),
        "matches_scored": n_scored,
        "mean_brier": round(mean_brier, 4) if mean_brier is not None else None,
        "verdict": verdict,
        "per_match": per_match,
    }


def write_report(competition: str, year: int, report: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    path = HISTORY_DIR / f"sports-backtest-{competition.replace(' ', '_')}-{year}-{ts}.json"
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "competition": competition,
        "year": year,
        **report,
    }
    path.write_text(json.dumps(out, indent=2))
    # Append-only summary
    summary = HISTORY_DIR / "sports-SUMMARY.md"
    if not summary.exists():
        summary.write_text(
            "# Sports backtest — running log\n\n"
            "> engine.sports_pricer.predict_match Brier against StatsBomb open-data.\n"
            "> Verdict gates: < 0.20 GO, 0.20-0.25 WAIT, > 0.25 SKIP.\n\n"
            "| Competition | Year | n | mean Brier | verdict | when |\n"
            "|---|---|---|---|---|---|\n"
        )
    with summary.open("a") as f:
        f.write(
            f"| {competition} | {year} | {report['matches_scored']} | "
            f"{report['mean_brier']} | {report['verdict']} | {ts} |\n"
        )
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--competition", default="FIFA World Cup")
    ap.add_argument("--year", type=int, default=2022)
    ap.add_argument("--all", action="store_true",
                    help="run a preset list of WC + UEFA + UCL backtests")
    args = ap.parse_args()

    targets: list[tuple[str, int]]
    if args.all:
        targets = [
            ("FIFA World Cup", 2022),
            ("FIFA World Cup", 2018),
            ("UEFA Euro", 2024),
            ("UEFA Euro", 2020),
            ("Champions League", 2024),
        ]
    else:
        targets = [(args.competition, args.year)]

    n_go = n_wait = n_skip = 0
    for comp, year in targets:
        print(f"\n[backtest-sports] {comp} {year}", file=sys.stderr)
        matches = load_statsbomb_matches(comp, year)
        report = run_backtest(matches)
        path = write_report(comp, year, report)
        v = report["verdict"]
        print(f"  → mean Brier {report['mean_brier']} on n={report['matches_scored']}: {v}",
              file=sys.stderr)
        print(f"  → {path}", file=sys.stderr)
        if v == "GO": n_go += 1
        elif v == "WAIT": n_wait += 1
        elif v == "SKIP": n_skip += 1

    print(f"\n[backtest-sports] summary: GO={n_go} WAIT={n_wait} SKIP={n_skip}",
          file=sys.stderr)
    # Exit non-zero if any verdict is SKIP — let CI / pre-paper-trade
    # gates catch model regressions before real money.
    return 0 if n_skip == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
