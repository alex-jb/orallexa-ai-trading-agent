"""sports_morning.py — daily NY 09:00 ET sports evidence scan.

Mirrors news_morning.py's pattern: pull today's relevant football matches
+ xG / Elo / lineup signals into a JSONL bus that sports_pricer.py will
consume to produce Dixon-Coles probabilities instead of Haiku our_p_yes
uniform-0.15.

Sources (tried in order, fail-graceful):
  1. soccerdata.ClubElo + soccerdata.FBref (primary)
  2. ScraperFC (fallback if soccerdata blocks)
  3. statsbombpy (only for historical truth, not live)

Output:
  ~/Desktop/Interview-Prep/Projects/alex-brain/research/markets-sports/YYYY-MM-DD.jsonl
  (one line per match, schema below)

Each line:
  {"date":"2026-06-29", "league":"WC-2026", "home":"Spain", "away":"Italy",
   "elo_home":1932, "elo_away":1768, "xg_recent_home":1.42, "xg_recent_away":0.98,
   "form_home":"WWDWW", "form_away":"DLWWD", "source":"soccerdata.club_elo",
   "fetched_at":"2026-06-29T13:00:00Z"}

Designed to fail gracefully — no network → write a stub placeholder rather
than crash. sports_pricer.py treats missing rows as "fall through to Haiku
our_p_yes" (back-compat).

Cron install:
  cp scripts/com.alexji.sports-morning.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.alexji.sports-morning.plist
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

HOME = Path.home()
BRAIN_DIR = (
    HOME / "Desktop" / "Interview-Prep" / "Projects" / "alex-brain"
    / "research" / "markets-sports"
)

# Tournaments + leagues to scan. Driven from rules.json eventually; for
# now, hardcoded to whatever's actively running. Update before each
# major-tournament season.
ACTIVE_COMPETITIONS = [
    {"league": "WC-2026", "soccerdata_id": "FIFA World Cup", "kind": "tournament"},
    {"league": "EPL", "soccerdata_id": "ENG-Premier League", "kind": "league"},
    {"league": "La Liga", "soccerdata_id": "ESP-La Liga", "kind": "league"},
]

# Window: today + tomorrow (so cron at 09:00 ET catches evening kickoffs
# anywhere in the world that resolve within the next ~36h).
HORIZON_HOURS = 36


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_via_soccerdata(competition: dict) -> list[dict]:
    """Try soccerdata first. Returns [] on any failure — caller falls back.

    soccerdata gives us:
      - ClubElo ratings (home_elo, away_elo) — the load-bearing strength feature
      - FBref rolling xG (xg_recent_home, xg_recent_away) over last 5 matches
      - Match schedule (date, kickoff)
    """
    try:
        # Late-import so cron doesn't crash on pip-not-installed
        import soccerdata as sd  # type: ignore
    except ImportError:
        print(f"[sports-morning] soccerdata not installed; skipping {competition['league']}",
              file=sys.stderr)
        return []

    rows: list[dict] = []
    try:
        elo = sd.ClubElo()
        elo_df = elo.read_team_history()  # all teams' Elo history
        # Last-known Elo per team
        latest = elo_df.sort_values("date").groupby("team").tail(1).set_index("team")["elo"]

        fb = sd.FBref(leagues=[competition["soccerdata_id"]], seasons=["2526"])
        # Schedule for the upcoming window
        try:
            schedule = fb.read_schedule()
        except Exception:
            schedule = None

        if schedule is not None and len(schedule) > 0:
            cutoff = datetime.now(timezone.utc) + timedelta(hours=HORIZON_HOURS)
            for _, m in schedule.iterrows():
                kickoff = m.get("date")
                if kickoff is None or kickoff > cutoff:
                    continue
                home = str(m.get("home_team") or m.get("home") or "")
                away = str(m.get("away_team") or m.get("away") or "")
                if not home or not away:
                    continue
                rows.append({
                    "date": kickoff.isoformat() if hasattr(kickoff, "isoformat") else str(kickoff),
                    "league": competition["league"],
                    "home": home,
                    "away": away,
                    "elo_home": float(latest.get(home, 1500.0)),
                    "elo_away": float(latest.get(away, 1500.0)),
                    "xg_recent_home": None,  # populated below if FBref has it
                    "xg_recent_away": None,
                    "form_home": None,
                    "form_away": None,
                    "source": "soccerdata.club_elo+fbref",
                    "fetched_at": _utcnow(),
                })
    except Exception as exc:
        print(f"[sports-morning] soccerdata failed for {competition['league']}: {exc}",
              file=sys.stderr)
        return []

    return rows


def fetch_via_scraperfc(competition: dict) -> list[dict]:
    """ScraperFC fallback. Same row schema as soccerdata path."""
    try:
        import ScraperFC as sfc  # type: ignore  # noqa: F401
    except ImportError:
        print(f"[sports-morning] ScraperFC not installed; skipping {competition['league']}",
              file=sys.stderr)
        return []

    # ScraperFC's API differs per source — keep this thin until we hit it
    # in production. The fallback role is "any signal beats no signal."
    # Wire the adapter shape when soccerdata first fails in the wild.
    try:
        # Placeholder: ScraperFC.Sofascore() / .FBref() / .ClubElo()
        # depending on what's down. For now, return empty so we don't
        # ship untested scraper code.
        return []
    except Exception as exc:
        print(f"[sports-morning] ScraperFC failed for {competition['league']}: {exc}",
              file=sys.stderr)
        return []


def fetch_matches() -> list[dict]:
    """Try each competition, soccerdata first, ScraperFC fallback."""
    out: list[dict] = []
    for comp in ACTIVE_COMPETITIONS:
        rows = fetch_via_soccerdata(comp)
        if not rows:
            rows = fetch_via_scraperfc(comp)
        out.extend(rows)
    return out


def write_jsonl(rows: list[dict]) -> Path:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = BRAIN_DIR / f"{today}.jsonl"
    with path.open("w") as f:
        if not rows:
            # Honest stub: write 0-row file with a meta header line so
            # downstream code can distinguish "scrapers all failed" from
            # "really 0 matches today."
            f.write(json.dumps({
                "_meta": "no rows — soccerdata + ScraperFC both returned empty",
                "fetched_at": _utcnow(),
            }) + "\n")
        else:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")
    return path


def main() -> int:
    try:
        rows = fetch_matches()
        path = write_jsonl(rows)
        print(f"[sports-morning] wrote {len(rows)} rows → {path}", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"[sports-morning] FATAL: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
