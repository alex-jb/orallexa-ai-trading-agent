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


def estimate_p_yes(event_title: str, question: str, current_market_p: float | None) -> dict:
    """Return {'p_yes', 'conviction', 'rationale'} or None values if unavailable.

    Calls Claude Haiku once per event. Cost ~$0.0003 per call (200 input + 150
    output tokens). 4 events/day → $0.0012/day → $0.44/year. Negligible.
    """
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
EVENTS = [
    ("will-china-invade-taiwan-before-2027",        "china_taiwan_2026", None),
    ("which-company-has-best-ai-model-end-of-june", "ai_model_google_jun",
                                                    "Will Google have the best AI model"),
    ("how-many-fed-rate-cuts-in-2026",              "fed_cuts_2_in_2026",
                                                    "2 fed rate cuts"),
    ("will-openais-valuation-hit-by-december-31",   "openai_500b_eoy",
                                                    "500"),
]


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
        est = estimate_p_yes(
            event_title=m.get("_event_title") or "",
            question=m.get("question") or "",
            current_market_p=yes,
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
