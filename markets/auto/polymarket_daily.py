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

import hashlib
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

# 72h news-lag skip window (2026-07-02 upgrade #3, per Prophet Arena
# 2026 finding, arxiv 2510.17638):
#   "markets incorporate breaking information and news updates more
#    rapidly than LLMs, quickly surpassing LLMs in short-term accuracy"
# Within 72h of resolution, LLM p_yes is systematically outperformed by
# market_p because LLMs can't ingest breaking news fast enough. We skip
# our estimate + fall back to market_p only — this removes a known
# structural loss window rather than pretending our estimate is useful.
NEWS_LAG_SKIP_HOURS = 72

# Political-market extremization (2026-07-02 upgrade #2, per
# "Decomposing Crowd Wisdom" arxiv 2602.19520, 292M trades / 327K
# contracts). Direct finding:
#   "The dominant pattern is persistent underconfidence in political
#    markets, where prices are chronically compressed toward 50%"
# When market_p sits in the compression zone and our estimate agrees
# directionally with market_p (both above or both below 0.5), we
# extremize our p_yes 30% away from market — correcting the structural
# compression bias without inventing signal we don't have.
POLITICAL_COMPRESSION_ZONE = (0.30, 0.70)
POLITICAL_EXTREMIZATION_FACTOR = 0.30

# Keywords that identify a market as political-adjacent. Conservative:
# false-positive (extremizing a non-political market) costs at most a
# 30% amplification of an already-correct directional edge; false-
# negative (missing extremization on a political market) is the baseline
# behavior. Bias toward FALSE for safety.
_POLITICAL_KEYWORDS = (
    "trump", "biden", "harris", "vance", "walz", "newsom",
    "election", "primary", "nominat", "impeach", "vote",
    "president", "senate", "congress", "supreme court", "scotus",
    "fed rate", "federal reserve", "powell", "fomc", "ecb", "boe",
    "china", "taiwan", "iran", "russia", "ukraine", "nato",
    "invade", "invasion", "war between", "cease-fire", "ceasefire",
    "recession", "gdp", "inflation", "cpi", "unemployment",
    "government shutdown", "debt ceiling",
)


def _is_political_market(event_title: str, question: str, event_slug: str = "") -> bool:
    """Detect political / political-adjacent markets. Conservative: a
    false positive costs a 30% amplification of an already-correct
    directional edge; a false negative leaves you at baseline behavior.
    Reasonable to err toward FALSE.
    """
    haystack = f"{event_title} {question} {event_slug}".lower()
    return any(kw in haystack for kw in _POLITICAL_KEYWORDS)


def _extremize_political_p(our_p: float, market_p: float | None) -> float:
    """Push our_p 30% further from market_p, but only when:
      1. market_p is in the compression zone [0.30, 0.70]
      2. our_p and market_p agree directionally (both < 0.5 or both > 0.5)

    Never crosses 0.5 (would flip the directional bet, which extremization
    is not supposed to do). Clamped to [0.01, 0.99] so we never emit
    literal certainty.
    """
    if market_p is None:
        return our_p
    if not (POLITICAL_COMPRESSION_ZONE[0] <= market_p <= POLITICAL_COMPRESSION_ZONE[1]):
        return our_p
    # Directional agreement check
    if (our_p >= 0.5) != (market_p >= 0.5):
        return our_p
    delta = our_p - market_p
    extremized = market_p + (1 + POLITICAL_EXTREMIZATION_FACTOR) * delta
    # Clamp; never cross 0.5 (would flip the directional bet)
    if market_p >= 0.5:
        extremized = max(0.5, min(0.99, extremized))
    else:
        extremized = min(0.5, max(0.01, extremized))
    return round(extremized, 4)

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


def _hours_until_resolution(end_date: str | None) -> float | None:
    """Return hours from now (UTC) until the market resolves, or None if
    the end_date field is missing or malformed.

    Polymarket serializes `endDate` as ISO 8601 with a trailing Z. We
    parse forgivingly — junk data means None + caller assumes "not
    near resolution" (safer than raising).
    """
    if not end_date:
        return None
    try:
        cleaned = end_date.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta_seconds = (dt - datetime.now(timezone.utc)).total_seconds()
        return delta_seconds / 3600.0
    except (ValueError, TypeError):
        return None


def _is_within_news_lag_window(end_date: str | None) -> bool:
    """True if we're within NEWS_LAG_SKIP_HOURS of the market's resolution.

    Returns False on malformed dates — we'd rather Haiku-estimate a
    long-horizon market than skip a valid one over a parse quirk.
    """
    hrs = _hours_until_resolution(end_date)
    if hrs is None:
        return False
    return 0 < hrs < NEWS_LAG_SKIP_HOURS


def estimate_p_yes(event_title: str, question: str, current_market_p: float | None,
                   event_slug: str = "", end_date: str | None = None) -> dict:
    """Return {'p_yes', 'conviction', 'rationale'} or None values if unavailable.

    Calls Claude Haiku once per event. Cost ~$0.0003 per call (200 input + 150
    output tokens). 4 events/day → $0.0012/day → $0.44/year. Negligible.

    Sports markets are routed to a `sports_skip` no-estimate response (see
    _is_sports_market) because Haiku defaults to ~0.5 on them, which created
    the fake +0.472 mean-edge bug surfaced 2026-06-30. Real bracket-MC for
    tournament-win markets is engine/sports_pricer.py + parlay_correlation
    v0.2 work.
    """
    # 2026-07-02 upgrade #3: 72h news-lag skip. Within NEWS_LAG_SKIP_HOURS
    # of resolution, LLM p_yes is systematically outperformed by market_p
    # (Prophet Arena 2026, arxiv 2510.17638). Check this BEFORE the sports
    # branch and BEFORE the Anthropic call — the shortest-path skip.
    if _is_within_news_lag_window(end_date):
        hrs = _hours_until_resolution(end_date)
        return {
            "p_yes": None,
            "conviction": "skip",
            "rationale": f"news_lag_skip_within_{NEWS_LAG_SKIP_HOURS}h_of_resolution ({hrs:.1f}h left)",
        }

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
    # 2026-07-02 upgrade #4: edge_thesis is now a required field. Kris
    # Longmore (Robot Wealth 2026) — "nice-looking backtests are cheap
    # now. AI has no theory of edge and doesn't know which edges have
    # real economic drivers behind them." A flag without an economic
    # driver is a false-positive factory. If the model refuses to
    # articulate ONE, we treat that as signal absence, not signal
    # presence.
    prompt = f"""Estimate the probability of this Polymarket event resolving YES.

Event: {event_title}
Question: {question}
{market_str}

Be an analyst, not a market follower. Don't anchor on the market price unless
you have no other signal. Cite 1-2 concrete factors driving your estimate.
Calibrated reasoning beats confident-sounding wrong calls.

CRITICAL: You must include an `edge_thesis` field — one sentence
explaining WHO on the other side of your view is systematically
mispricing this event and WHY. If you cannot articulate a specific
economic driver of edge, set edge_thesis to null and lower conviction
to "low". A view without an edge_thesis is a random walk.

Output strictly JSON:
{{
  "p_yes": 0.XX,
  "conviction": "high" | "medium" | "low",
  "rationale": "one-line summary of your reasoning",
  "edge_thesis": "specific economic driver of edge, or null"
}}
"""
    # 2026-07-02 upgrade #9: auditable-history port from Shadow's
    # buildReproducibilityArtifact (2026-07-02 sibling ship). Anthropic
    # Claude Science launch (2026-06-30) positioned "every output
    # carries an auditable history of how it was made" as the industry
    # trust primitive for AI in high-risk regulated domains. Same shape
    # here for banking-adjacent prediction-market decisions. Alex 6
    # months from now, or an examiner replaying this audit chain, can
    # verify "the model said X" not "Alex rewrote the log after".
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    call_started_utc = datetime.now(timezone.utc).isoformat()
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
        # edge_thesis extraction — treated as informational but persisted
        # so brier_audit can bucket signals by "has thesis" vs "no thesis"
        # and see empirically whether thesis-backed signals outperform.
        raw_thesis = data.get("edge_thesis")
        if raw_thesis is None or (isinstance(raw_thesis, str) and not raw_thesis.strip()):
            edge_thesis = None
            # A missing thesis is legitimate signal absence — downgrade
            # conviction so downstream mispricing_flag threshold catches it.
            conviction = "low"
        else:
            edge_thesis = str(raw_thesis)[:300]
            conviction = str(data.get("conviction", "low"))[:20]
        return {
            "p_yes": p_yes,
            "conviction": conviction,
            "rationale": str(data.get("rationale", ""))[:200],
            "edge_thesis": edge_thesis,
            # 2026-07-02 upgrade #9: auditable-history fields per Claude
            # Science 2026-06-30 pattern. Prompt hash pins determinism;
            # model_id pins Sonnet-4-6 vs Haiku-4-5 vs future Sonnet-5;
            # timestamps bound the response to a specific market snapshot
            # in time. Full prompt not returned (may contain client-
            # confidential market context in future); hash is enough to
            # prove the same prompt reran deterministically.
            "audit": {
                "model_id": CLAUDE_MODEL,
                "prompt_sha256": prompt_sha256,
                "call_started_utc": call_started_utc,
                "call_completed_utc": datetime.now(timezone.utc).isoformat(),
                "response_tokens_hint": len(text),
            },
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
            end_date=m.get("endDate"),
        )
        # 2026-07-02 upgrade #2: political-market extremization. Applied
        # to the RAW Haiku estimate before mispricing delta calc.
        # Recorded separately so brier_audit can compare pre- vs post-
        # extremization Brier and validate the correction is helping.
        raw_our_p = est["p_yes"]
        extremized_p = raw_our_p
        if raw_our_p is not None and _is_political_market(
            m.get("_event_title") or "", m.get("question") or "", slug or ""
        ):
            extremized_p = _extremize_political_p(raw_our_p, yes)
        mispricing_delta = None
        mispricing_flag = None
        if extremized_p is not None and yes is not None:
            mispricing_delta = round(extremized_p - yes, 3)
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
            # our_p_yes is the EXTREMIZED value we act on downstream.
            # our_p_yes_raw is the pre-extremization Haiku output — kept
            # so brier_audit can bucket by pre/post and validate that
            # extremization actually helps calibration (upgrade #8).
            "our_p_yes": extremized_p,
            "our_p_yes_raw": raw_our_p,
            "our_conviction": est["conviction"],
            "our_rationale": est["rationale"],
            # 2026-07-02 upgrade #4: economic-driver field. May be None
            # for skip paths (sports/news-lag) or when the model refuses
            # to articulate one. brier_audit can bucket by has-thesis.
            "our_edge_thesis": est.get("edge_thesis"),
            "extremized": extremized_p != raw_our_p,
            # 2026-07-02 upgrade #9: auditable-history block. None on
            # skip paths (sports / news-lag) — no LLM call, nothing to
            # audit. When present, `audit.model_id + prompt_sha256 +
            # call_completed_utc` uniquely identifies "the exact model
            # + prompt + moment" that produced this row. 6 months from
            # now an examiner can verify the log is authentic.
            "audit": est.get("audit"),
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
