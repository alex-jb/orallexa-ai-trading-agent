#!/usr/bin/env python3
"""Polymarket daily yes-price tracker for 3 named binary events.

Cron: com.orallexa.polymarket-daily, NY 09:35 ET (right after market open).
Re-enabled 2026-05-14 after Cloudflare IP block lifted (verified
in .polymarket_status.json).

Output: appends one JSONL line per event per day to
~/.orallexa/markets/polymarket_history.jsonl. Brier audit cron at
NY 22:00 reads this for calibration scoring.

The 3 events we care about are listed in EVENTS below. To add a new one:
just append a {slug_query, friendly_name} tuple. The script will search
gamma-api by keywords and pick the highest-volume active match.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HISTORY = HOME / ".orallexa" / "markets" / "polymarket_history.jsonl"
HISTORY.parent.mkdir(parents=True, exist_ok=True)

# PolyAlert (project #2 2026-05-31): rules.json declarative config.
# Borrowed pattern from TradingView MCP (greenpeas007/tradingview-mcp-jackson).
# When rules.json exists, it overrides hardcoded EVENTS below. Allows scaling
# from 4 → 100+ events without editing code.
RULES_PATH = HOME / ".orallexa" / "markets" / "rules.json"

# 2026-05-27 (Phase A #1): per-event own probability estimation via Claude.
# Without our own estimate we can't Brier-score Polymarket predictions; without
# Brier scores we can't satisfy the Phase 1 ($300 real money) entry gate.
# Haiku is enough — these are 1-shot reasoned estimates, not deep research.
CLAUDE_MODEL = "claude-haiku-4-5"
MISPRICING_THRESHOLD = 0.05  # |our_p - market_p| > 5% → flag

# Load ANTHROPIC_API_KEY: prefer env, fall back to grepping ~/.zshrc
# (daily-brief.sh established this pattern — launchd doesn't source zshrc).
def _load_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    zshrc = HOME / ".zshrc"
    if not zshrc.exists():
        return ""
    try:
        for line in zshrc.read_text().splitlines():
            m = re.match(r'^export\s+ANTHROPIC_API_KEY\s*=\s*"?([^"\s]+)"?', line.strip())
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


# Sports-market routing (2026-06-30 fix):
#   queue_consumer.py first fire surfaced 173 historical Polymarket decisions,
#   126 (73%) of them were sports markets ("Will X win the 2026 FIFA World Cup")
#   where Haiku had been returning a default-ish ~0.5 p_yes for every row —
#   producing a fake mean edge of +0.472 across the entire sports tape. If we
#   had been real-money trading, that's 126 sized positions all on noise.
#
#   The proper fix is a Monte Carlo bracket simulator over Elo
#   (engine.parlay_correlation.simulate_tournament_advance), but that needs the
#   2026 World Cup bracket structure as data + a full Elo lookup, which is its
#   own ship. Until then: DETECT sports markets and refuse to estimate. Better
#   to write our_p_yes=None than to write a wrong number that looks edged.
_SPORTS_TOKENS = (
    "world-cup", "champions-league", "premier-league", "la-liga",
    "serie-a", "bundesliga", "ligue-1", "mls", "nba", "nfl", "nhl",
    "mlb", "tennis", "atp", "wta", "f1-", "formula-1", "nascar",
    "olympics", "euro-202", "copa-america", "fifa", "uefa",
    "wimbledon", "us-open", "french-open", "australian-open",
    "super-bowl", "world-series", "stanley-cup",
)
_SPORTS_PHRASES = (
    # Sport-specific titles only. "win the 2028" was tried initially but
    # false-positived on "Bernie Sanders win the 2028 Democratic
    # Presidential nomination" — that pattern belongs to politics, Haiku
    # is fine with it.
    "wins the world cup", "win the world cup",
    "wins the world series", "win the world series",
    "wins the super bowl", "win the super bowl",
    "advance to ", "reach the final", "win the championship",
    "win the cup", "win the title", "win the league",
)


def _is_sports_market(slug: str, question: str) -> bool:
    """True if this Polymarket event is a sports market that our Haiku
    pricer cannot reliably estimate. Conservative detection: false-positive
    (skipping a non-sports market) costs us 1 estimate; false-negative
    (Haiku rates a sports market) re-introduces the +0.5 default bug.
    """
    s = (slug or "").lower()
    q = (question or "").lower()
    if any(tok in s for tok in _SPORTS_TOKENS):
        return True
    if any(tok in q for tok in _SPORTS_TOKENS):
        return True
    if any(phrase in q for phrase in _SPORTS_PHRASES):
        return True
    return False


# Tournament-winner market routing (2026-06-30 wire-in):
# 126/173 historical sports markets are "Will <country> win the 2026 FIFA
# World Cup". Extract the country, look it up in NATIONAL_TEAM_ELO,
# delegate to engine.sports_pricer.predict_tournament_winner_elo_only.
# If extraction fails or team not in Elo dict (small federations not in
# top-32 snapshot), fall through to the existing `sports_skip` path.

# Lazy import so this module is still testable without engine/ being on
# the Python path (tests for the LLM call shouldn't transitively pull in
# sports_pricer's stack).
def _tournament_winner_p_yes(slug: str, question: str) -> dict | None:
    """Returns {'p_yes', 'rationale', 'team'} or None if not extractable."""
    s = (slug or "").lower()
    # Pattern: "will-<TEAM>-win-the-2026-fifa-world-cup" + trailing-id
    m = re.match(r"^will-([a-z][a-z-]+?)-win-the-2026-fifa-world-cup(?:-\d+)?$", s)
    if not m:
        return None
    raw_team = m.group(1)  # e.g. "new-zealand"
    # Normalize "new-zealand" → "New Zealand", "south-korea" → "South Korea"
    team = " ".join(w.capitalize() for w in raw_team.split("-"))

    try:
        from engine.sports_pricer import predict_tournament_winner_elo_only
        from markets.auto.sports_morning import NATIONAL_TEAM_ELO
    except ImportError as exc:
        # If engine layer isn't importable, log + bail (caller skips).
        print(f"[polymarket-daily] sports_pricer import failed: {exc}",
              file=sys.stderr)
        return None

    p_yes = predict_tournament_winner_elo_only(
        team, NATIONAL_TEAM_ELO,
        n_rounds=4,          # WC R16→QF→SF→F path
        n_sims=3000,
        seed=42,             # deterministic for daily reproducibility
    )
    if p_yes is None:
        return None  # team not in Elo dict
    return {
        "p_yes": round(p_yes, 4),
        "rationale": (
            f"tournament_winner_elo_only(team={team}, n_rounds=4, "
            f"n_sims=3000, seed=42) — Elo-based MC, no bracket structure"
        ),
        "team": team,
    }


def estimate_p_yes(event_title: str, question: str, current_market_p: float | None,
                   event_slug: str = "") -> dict:
    """Return {'p_yes', 'conviction', 'rationale'} or None values if unavailable.

    Calls Claude Haiku once per event. Cost ~$0.0003 per call (200 input + 150
    output tokens). 4 events/day → $0.0012/day → $0.44/year. Negligible.

    Sports markets are routed to a `sports_skip` no-estimate response (see
    _is_sports_market) because Haiku defaults to ~0.5 on them, which created
    the fake +0.472 mean-edge bug surfaced 2026-06-30. Real bracket-MC for
    tournament-win markets is engine/sports_pricer.py + parlay_correlation
    v0.2 work.
    """
    if _is_sports_market(event_slug, f"{event_title} {question}"):
        # 2026-06-30 wire-in: try tournament-winner Elo MC first; if the
        # team is extractable + in NATIONAL_TEAM_ELO, return a real prob.
        # Only fall through to skip if extraction or Elo lookup fails.
        tw = _tournament_winner_p_yes(event_slug, question)
        if tw is not None:
            return {
                "p_yes": tw["p_yes"],
                "conviction": "medium",
                "rationale": tw["rationale"],
            }
        return {
            "p_yes": None,
            "conviction": "skip",
            "rationale": "sports_market_skip_v1_no_bracket_mc_yet",
        }
    api_key = _load_anthropic_key()
    if not api_key:
        return {"p_yes": None, "conviction": "n/a", "rationale": "no-api-key"}
    try:
        from anthropic import Anthropic
    except ImportError:
        return {"p_yes": None, "conviction": "n/a", "rationale": "no-sdk"}

    market_str = (f"Current market consensus: {current_market_p:.3f} "
                  f"(~{current_market_p*100:.0f}% yes)") if current_market_p else "(market price unavailable)"
    prompt = f"""Estimate the probability of this Polymarket event resolving YES.

Event: {event_title}
Question: {question}
{market_str}

Be an analyst, not a market follower. Don't anchor on the market price unless
you have no other signal. Cite 1-2 concrete factors driving your estimate.
Calibrated reasoning beats confident-sounding wrong calls.

Output strictly JSON: {{"p_yes": 0.XX, "conviction": "high"|"medium"|"low", "rationale": "..."}}
"""
    try:
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        m = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if not m:
            return {"p_yes": None, "conviction": "err", "rationale": "parse_fail"}
        data = json.loads(m.group())
        p_raw = data.get("p_yes")
        try:
            p_yes = float(p_raw) if p_raw is not None else None
        except (TypeError, ValueError):
            return {"p_yes": None, "conviction": "err", "rationale": "non_numeric_p"}
        if p_yes is not None and (p_yes < 0 or p_yes > 1):
            return {"p_yes": None, "conviction": "err",
                    "rationale": f"out_of_range:{p_yes}"}
        return {
            "p_yes": p_yes,
            "conviction": str(data.get("conviction", "low"))[:20],
            "rationale": str(data.get("rationale", ""))[:200],
        }
    except Exception as exc:
        return {"p_yes": None, "conviction": "err", "rationale": f"api:{exc!r}"[:120]}

# Hardcoded event slugs we care about. 2026-05-19 refresh after powell_out
# resolved + ai_model_google_may liquidity collapsed (May market closes
# May 31). New set tilts toward macro events that move the 14-ticker
# watchlist on a longer horizon:
#
#   - China invade Taiwan 2026 — defense (LMT/KTOS/AVAV/RDW) + China semis
#   - Best AI model end-of-JUNE — fresher iteration of the May market
#   - Fed rate cuts 2026 (count) — macro discount-rate; we track the
#     "exactly 2 cuts" sub-market as a proxy for consensus path
#   - OpenAI valuation hit $X by Dec 31 — AI-cycle thermometer (proxy
#     for NVDA/AVGO premium expansion)
EVENTS_HARDCODED = [
    ("will-china-invade-taiwan-before-2027",        "china_taiwan_2026", None),
    ("which-company-has-best-ai-model-end-of-june", "ai_model_google_jun",
                                                    "Will Google have the best AI model"),
    ("how-many-fed-rate-cuts-in-2026",              "fed_cuts_2_in_2026",
                                                    "2 fed rate cuts"),
    ("will-openais-valuation-hit-by-december-31",   "openai_500b_eoy",
                                                    "500"),
]


def load_events() -> list[tuple[str, str, str | None]]:
    """Read events from rules.json if present, else fall back to EVENTS_HARDCODED.
    PolyAlert (project #2): lets user grow event list to 100+ without editing code."""
    if not RULES_PATH.exists():
        return EVENTS_HARDCODED
    try:
        rules = json.loads(RULES_PATH.read_text())
        watchlist = rules.get("watchlist", [])
        if not watchlist:
            return EVENTS_HARDCODED
        return [
            (e["slug"], e["friendly"], e.get("sub_question_filter"))
            for e in watchlist
            if "slug" in e and "friendly" in e
        ]
    except Exception as exc:
        print(f"[polymarket-daily] rules.json parse failed: {exc!r}, using hardcoded",
              file=sys.stderr)
        return EVENTS_HARDCODED


EVENTS = load_events()


_HTTP = None


def _get(url: str):
    global _HTTP
    if _HTTP is None:
        try:
            from curl_cffi import requests as cf
            _HTTP = ("cf", cf)
        except ImportError:
            import urllib.request
            _HTTP = ("urllib", urllib.request)
    kind, mod = _HTTP
    if kind == "cf":
        return mod.get(url, impersonate="chrome", timeout=20)
    req = mod.Request(url, headers={"User-Agent": "polymarket-daily/1.0"})
    r = mod.urlopen(req, timeout=20)
    payload = r.read().decode()
    class _R:
        status_code = r.status
        @staticmethod
        def json():
            return json.loads(payload)
    return _R()


def fetch_event(slug: str, sub_question_filter: str | None = None) -> dict | None:
    """Fetch an event by slug → return its primary binary sub-market.
    If `sub_question_filter` is provided, picks the first market whose
    question starts with it (case-insensitive). Else returns the first
    market in the event."""
    url = f"https://gamma-api.polymarket.com/events/slug/{slug}"
    try:
        r = _get(url)
        if r.status_code != 200:
            return None
        evt = r.json()
    except Exception as exc:
        print(f"[polymarket-daily] {slug} fetch failed: {exc!r}", file=sys.stderr)
        return None
    markets = evt.get("markets") or []
    if not markets:
        return None
    if sub_question_filter:
        needle = sub_question_filter.lower()
        for m in markets:
            if (m.get("question") or "").lower().startswith(needle):
                # Stamp event title for clarity.
                m["_event_title"] = evt.get("title")
                return m
        return None
    m = markets[0]
    m["_event_title"] = evt.get("title")
    return m


def extract_yes_price(market: dict) -> float | None:
    """gamma-api returns outcomePrices as stringified list 'no,yes' or
    'yes,no' depending on market. The yes-side is whichever outcome label
    matches 'yes' (case-insensitive). Returns 0..1 or None."""
    outcomes = market.get("outcomes")
    prices = market.get("outcomePrices")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            return None
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except Exception:
            return None
    if not (isinstance(outcomes, list) and isinstance(prices, list)):
        return None
    for label, price in zip(outcomes, prices):
        if str(label).lower().strip() == "yes":
            try:
                return float(price)
            except Exception:
                return None
    # fallback: first entry
    try:
        return float(prices[0])
    except Exception:
        return None


def main() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    written = 0
    for slug, friendly, sub_filter in EVENTS:
        m = fetch_event(slug, sub_filter)
        if not m:
            print(f"[polymarket-daily] {friendly} ({slug!r}) — no match", file=sys.stderr)
            continue
        yes = extract_yes_price(m)
        try:
            vol = float(m.get("volume24hr") or 0)
        except Exception:
            vol = 0.0
        # Phase A #1 (2026-05-27): our own probability estimate via Haiku.
        # 2026-06-30: sports markets short-circuit to skip — see estimate_p_yes
        # docstring for the 73%-of-tape-was-noise bug we just stopped.
        est = estimate_p_yes(
            event_title=m.get("_event_title") or "",
            question=m.get("question") or "",
            current_market_p=yes,
            event_slug=slug or m.get("slug") or "",
        )
        mispricing_delta = None
        mispricing_flag = None
        if est["p_yes"] is not None and yes is not None:
            mispricing_delta = round(est["p_yes"] - yes, 3)
            mispricing_flag = "YES" if abs(mispricing_delta) > MISPRICING_THRESHOLD else "NO"

        line = {
            "date": today,
            "friendly": friendly,
            "event_slug": slug,
            "event_title": m.get("_event_title"),
            "slug": m.get("slug"),
            "question": m.get("question"),
            "yes_price": yes,
            "volume24hr": vol,
            "end_date": m.get("endDate"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            # Phase A #1 — our own estimate for Brier scoring + mispricing detection
            "our_p_yes": est["p_yes"],
            "our_conviction": est["conviction"],
            "our_rationale": est["rationale"],
            "mispricing_delta": mispricing_delta,
            "mispricing_flag": mispricing_flag,
        }
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        flag_emoji = "🚨" if mispricing_flag == "YES" else "  "
        our_str = f"{est['p_yes']:.3f}" if est["p_yes"] is not None else "n/a"
        print(f"[polymarket-daily] {flag_emoji} {friendly}: market_yes={yes} our_yes={our_str} "
              f"Δ={mispricing_delta} conviction={est['conviction']}")
        written += 1
    print(f"[polymarket-daily] wrote {written}/{len(EVENTS)} entries to {HISTORY}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
