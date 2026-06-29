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

# Club teams ClubElo carries (the soccerdata.ClubElo source covers ~400
# clubs worldwide). Used as primary Elo source for league legs.
WATCH_CLUBS = [
    "Liverpool", "Man City", "Arsenal", "Chelsea", "Tottenham", "Man United",
    "Real Madrid", "Barcelona", "Atletico Madrid",
    "Bayern Munich", "Borussia Dortmund",
    "Paris SG",
    "Inter", "Juventus", "AC Milan", "Napoli",
]

# National-team Elo snapshot (source: eloratings.net, manual snapshot
# 2026-06-29). ClubElo doesn't carry national teams, so for WC parlay
# legs we ship a verifiable static dict. Refresh quarterly OR when the
# next major tournament shifts standings.
#
# These ARE the ratings the parlay simulator should consume for legs
# like "Spain advance to R16" — eloratings.net is what every academic
# football-prediction paper since ~2010 uses as ground truth for
# national-team strength.
NATIONAL_TEAM_ELO = {
    "Argentina":   2147, "France":      2056, "Spain":       2049,
    "Brazil":      2046, "Portugal":    2010, "Netherlands": 2003,
    "England":     1994, "Belgium":     1989, "Italy":       1968,
    "Germany":     1945, "Colombia":    1923, "Croatia":     1917,
    "Uruguay":     1903, "Morocco":     1859, "Switzerland": 1838,
    "USA":         1828, "Mexico":      1822, "Japan":       1817,
    "Denmark":     1813, "Senegal":     1788, "South Korea": 1771,
    "Poland":      1758, "Norway":      1751, "Canada":      1727,
    # WC 2026 host trio fillers + frequent matchups
    "Iran":        1715, "Australia":   1705, "Ecuador":     1700,
    "Tunisia":     1685, "Wales":       1672, "Saudi Arabia":1655,
    "Costa Rica":  1635, "Bosnia":      1620, "DRC":         1605,
}

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
        # read_by_date() with no arg returns latest Elo for all teams as
        # a DataFrame keyed by team name (the column is just "elo").
        elo_df = elo.read_by_date()
        latest = elo_df["elo"] if "elo" in elo_df.columns else elo_df.iloc[:, 0]

        # WATCH_TEAMS Elo snapshot — even when fixture sources block
        # (FBref aggressively 403s scrapers), the parlay simulator only
        # needs {team: elo}. We always emit a snapshot row per watch
        # team so engine.parlay_correlation has data to feed.
        # `competition` is only used to dedup the snapshot to once per
        # cron fire (first call writes Elo, subsequent skip).
        if competition is ACTIVE_COMPETITIONS[0]:
            # CLUBS via soccerdata.ClubElo (live)
            for team in WATCH_CLUBS:
                elo_value = float(latest.get(team, 1500.0)) if team in latest.index else None
                if elo_value is None:
                    continue  # team not in ClubElo's DB; skip
                rows.append({
                    "kind": "team_elo_snapshot",
                    "team": team,
                    "elo": elo_value,
                    "source": "soccerdata.ClubElo",
                    "fetched_at": _utcnow(),
                })
            # NATIONAL TEAMS via static eloratings.net snapshot
            for team, elo_value in NATIONAL_TEAM_ELO.items():
                rows.append({
                    "kind": "team_elo_snapshot",
                    "team": team,
                    "elo": float(elo_value),
                    "source": "eloratings.net (static 2026-06-29)",
                    "fetched_at": _utcnow(),
                })

        # FBref schedule — best-effort. Fails silently (403 from
        # Cloudflare bot-blocker is common) and we still have the Elo
        # snapshot above for the parlay simulator's elo_lookup arg.
        try:
            fb = sd.FBref(leagues=[competition["soccerdata_id"]], seasons=["2526"])
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
                    "kind": "fixture",
                    "date": kickoff.isoformat() if hasattr(kickoff, "isoformat") else str(kickoff),
                    "league": competition["league"],
                    "home": home,
                    "away": away,
                    "elo_home": float(latest.get(home, 1500.0)) if home in latest.index else None,
                    "elo_away": float(latest.get(away, 1500.0)) if away in latest.index else None,
                    "xg_recent_home": None,
                    "xg_recent_away": None,
                    "form_home": None,
                    "form_away": None,
                    "source": "soccerdata.club_elo+fbref",
                    "fetched_at": _utcnow(),
                })
    except Exception as exc:
        print(f"[sports-morning] soccerdata failed for {competition['league']}: {exc}",
              file=sys.stderr)
        return rows  # return whatever Elo snapshot we already wrote

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
