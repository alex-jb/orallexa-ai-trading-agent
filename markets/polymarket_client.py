"""Polymarket Gamma + CLOB API client — read-only, no wallet.

Public endpoints exposed by Polymarket:

  Gamma API (gamma-api.polymarket.com)
    GET /markets               — list markets with rich metadata
    GET /markets/{id_or_slug}  — single market

  CLOB API (clob.polymarket.com)
    GET /prices-history?market=<condition_id>&interval=1h&fidelity=720
        — YES price time series

These do NOT require an EIP-712 signature or HMAC; they're plain JSON
over HTTPS. We use them strictly for:

1. Historical backtest data on resolved markets (Brier-score validation
   of our LLM debate against past Polymarket prices and outcomes).
2. Live read-only context for the daily HITL queue once we've validated
   on Kalshi and Polymarket US opens non-sports markets.

Wallet integration (`py-clob-client`, EIP-712 sigs, USDC transfers) is
deliberately not imported. We are not trading on Polymarket from this
module in v0.1. The Polymarket main wallet is geoblocked for NY IPs;
Polymarket US (QCEX) is on the iOS App Store but currently waitlist +
sports-only.

Reference: https://docs.polymarket.com/api-reference/
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from markets.market import BinaryMarket, PriceTick


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


@dataclass
class PolymarketConfig:
    gamma_base: str = GAMMA_BASE
    clob_base: str = CLOB_BASE
    # Cloudflare on Polymarket Gamma rejects bot-like User-Agents at the
    # TLS-handshake layer (verified 2026-05-12 — curl with default UA also
    # gets reset). Mimic a real Chrome on macOS so the read-only API call
    # passes through. We are not violating any ToS — Gamma is documented
    # public API; this is the price of being on Cloudflare-fronted infra.
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
    timeout_sec: int = 20


def _normalize_status(raw: dict) -> str:
    """Gamma exposes `closed` (bool) + `archived` (bool) + `active` (bool).
    Map them into BinaryMarket's status vocabulary.
    """
    if raw.get("archived"):
        return "finalized"
    if raw.get("closed"):
        return "settled"
    if raw.get("active"):
        return "open"
    return "closed"


def _normalize_outcome(raw: dict) -> Optional[int]:
    """Pull resolution from `outcomePrices` once closed.

    Gamma stores `outcomePrices` as a JSON-string like '["1", "0"]' where
    index 0 = YES, index 1 = NO. After settlement the winning outcome is
    1.0 and the loser is 0.0.
    """
    if not raw.get("closed"):
        return None
    op = raw.get("outcomePrices")
    if op is None:
        return None
    # outcomePrices is sometimes a JSON string, sometimes a list.
    if isinstance(op, str):
        import json
        try:
            op = json.loads(op)
        except json.JSONDecodeError:
            return None
    if not isinstance(op, list) or len(op) < 2:
        return None
    try:
        yes = float(op[0])
        no = float(op[1])
    except (TypeError, ValueError):
        return None
    if yes >= 0.99 and no <= 0.01:
        return 1
    if no >= 0.99 and yes <= 0.01:
        return 0
    return None  # ambiguous / not yet resolved


def _category_from_tags(raw: dict) -> str:
    """Gamma markets nominally carry `category` + `tags`, but in practice
    both fields are usually None or empty on real records. Falls back to
    slug + event-ticker keyword heuristics in that case.
    """
    raw_cat = (raw.get("category") or "").lower()
    bucket_map = {
        "politics": "politics",
        "us politics": "politics",
        "geopolitics": "geopolitics",
        "world events": "geopolitics",
        "international affairs": "geopolitics",
        "economics": "economics",
        "macroeconomics": "economics",
        "fed": "economics",
        "science": "science",
        "technology": "science",
        "ai": "science",
        "sports": "sports",
        "crypto": "crypto",
        "cryptocurrency": "crypto",
        "weather": "weather",
        "climate": "weather",
    }
    if raw_cat in bucket_map:
        return bucket_map[raw_cat]
    tags = raw.get("tags") or []
    if isinstance(tags, list):
        for t in tags:
            t = str(t).lower()
            if t in bucket_map:
                return bucket_map[t]

    # Heuristic from slug + event ticker (Polymarket 2026: category field
    # is almost always None on the wire, so we infer from text).
    haystack_parts = [raw.get("slug") or "", raw.get("question") or ""]
    for ev in (raw.get("events") or []):
        haystack_parts.append(ev.get("slug") or "")
        haystack_parts.append(ev.get("ticker") or "")
    h = " ".join(haystack_parts).lower()

    # Order matters: more-specific buckets before more-general
    crypto_kw = ("bitcoin", "btc", "ethereum", "eth", "solana", "doge", "crypto")
    sports_kw = (
        "nba", "nfl", "mlb", "nhl", "ufc", "f1", "fifa", "world-cup",
        "premier", "champions-league", "tennis", "golf", "pga",
        "soccer", "football",
    )
    economics_kw = ("fed", "fomc", "cpi", "gdp", "rate-hike", "rate-cut",
                    "powell", "yellen", "bowman", "treasury")
    geopolitics_kw = (
        "china", "russia", "iran", "ukraine", "israel", "gaza", "putin",
        "xi-jinping", "taiwan", "korea", "nato", "un-", "peace-deal",
        "summit", "war", "invasion",
    )
    politics_kw = (
        "election", "president", "senate", "house", "congress", "gop",
        "democrat", "republican", "trump", "harris", "biden", "vance",
        "primary", "scotus", "bill-pass", "epstein", "impeachment",
    )
    science_kw = ("nasa", "spacex", "ai-", "agi", "openai", "anthropic",
                  "fda-approval", "vaccine", "pandemic", "outbreak",
                  "hantavirus", "covid")
    weather_kw = ("hurricane", "storm", "snow", "temperature", "weather",
                  "atmospheric", "el-nino")

    def hit(kws) -> bool:
        return any(k in h for k in kws)

    if hit(crypto_kw):
        return "crypto"
    if hit(sports_kw):
        return "sports"
    if hit(economics_kw):
        return "economics"
    if hit(geopolitics_kw):
        return "geopolitics"
    if hit(politics_kw):
        return "politics"
    if hit(science_kw):
        return "science"
    if hit(weather_kw):
        return "weather"
    return "other"


# Events that aggregate many low-signal meme markets — filtered out by
# default in the CLI queue subcommand. Each market here is a sub-market
# of an umbrella event like "what-will-happen-before-gta-vi".
DEFAULT_EVENT_BLACKLIST = (
    "what-will-happen-before-",
    "will-it-happen-",
    "before-the-",
    "in-the-next-",
)


def is_meme_event(raw: dict) -> bool:
    """True if this market belongs to a meme umbrella event."""
    events = raw.get("events") or []
    if not events:
        return False
    for ev in events:
        slug = (ev.get("slug") or "").lower()
        if any(slug.startswith(p) for p in DEFAULT_EVENT_BLACKLIST):
            return True
    return False


def market_volume_24hr(raw: dict) -> float:
    """All-time volume is a stale signal — recent 24h volume is what tells
    us a market is currently being traded. Markets with $0 24h volume are
    effectively dead for our purposes regardless of historical $.
    """
    v = raw.get("volume24hr")
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_market(raw: dict) -> BinaryMarket:
    """Pure function: Gamma JSON record → BinaryMarket. Fixture-tested.

    Field map (Gamma → BinaryMarket):
      conditionId            → market_id
      slug                   → ticker
      question               → question
      category, tags         → category (bucketed)
      active/closed/archived → status (normalized)
      startDate, endDate     → open_time, close_time
      umaResolutionDate      → expiration_time
      resolvedDate           → settled_at
      lastTradePrice         → yes_price
      bestBid, bestAsk       → yes_bid, yes_ask
      volume, volumeNum      → volume
      liquidity              → open_interest (proxy)
      outcomePrices          → outcome (YES=1 / NO=0 / None)
    """
    condition_id = raw.get("conditionId") or raw.get("id") or ""
    slug = raw.get("slug") or condition_id

    def to_float(x) -> Optional[float]:
        if x is None:
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    return BinaryMarket(
        platform="polymarket",
        market_id=condition_id,
        ticker=slug,
        question=raw.get("question") or raw.get("title") or slug,
        category=_category_from_tags(raw),
        status=_normalize_status(raw),  # type: ignore[arg-type]
        open_time=raw.get("startDate"),
        close_time=raw.get("endDate"),
        expiration_time=raw.get("umaResolutionDate"),
        settled_at=raw.get("resolvedDate") or raw.get("closedTime"),
        yes_price=to_float(raw.get("lastTradePrice")),
        yes_bid=to_float(raw.get("bestBid")),
        yes_ask=to_float(raw.get("bestAsk")),
        volume=to_float(raw.get("volumeNum") or raw.get("volume")) or 0.0,
        open_interest=to_float(raw.get("liquidity") or raw.get("liquidityNum")) or 0.0,
        outcome=_normalize_outcome(raw),
        description=raw.get("description") or "",
        raw=raw,
    )


def parse_history(raw: dict) -> list[PriceTick]:
    """Polymarket /prices-history → list[PriceTick].

    Shape: {history: [{t: <unix>, p: <yes_price 0..1>}, ...]}
    """
    ticks: list[PriceTick] = []
    for row in raw.get("history") or []:
        t = row.get("t")
        p = row.get("p")
        if t is None or p is None:
            continue
        try:
            ticks.append(PriceTick(t=int(t), yes=float(p)))
        except (TypeError, ValueError):
            continue
    return ticks


class PolymarketClient:
    """Read-only Polymarket client. Gamma + CLOB endpoints, no wallet."""

    def __init__(self, config: Optional[PolymarketConfig] = None):
        self.config = config or PolymarketConfig()

    def _get(self, base: str, path: str, params: Optional[dict] = None) -> dict:
        """HTTP GET via curl_cffi (impersonates Chrome TLS fingerprint).

        Polymarket Gamma + CLOB are Cloudflare-fronted with Bot Fight Mode
        enabled. Plain `requests` and even default `curl` get rejected at the
        TLS-handshake layer (verified 2026-05-12). `curl_cffi` impersonates
        a real Chrome TLS fingerprint via libcurl-impersonate, which slips
        through Cloudflare's TLS-fingerprint detection.

        Falls back to plain `requests` only for non-Cloudflare-fronted
        endpoints (none currently — both Gamma and CLOB are protected).
        """
        import time as _t
        try:
            from curl_cffi import requests as cffi_requests
            use_impersonate = True
        except ImportError:
            import requests as cffi_requests  # type: ignore
            use_impersonate = False

        url = f"{base}{path}"
        kwargs = dict(
            params=params or {},
            headers={"User-Agent": self.config.user_agent, "Accept": "application/json"},
            timeout=self.config.timeout_sec,
        )
        if use_impersonate:
            kwargs["impersonate"] = "chrome"

        # DNS retry: markets.queue 09:00 ET fires before WiFi/networkd
        # finishes resolving. Same root cause as polymarket_daily 09:35
        # `Could not resolve host: gamma-api.polymarket.com` pattern.
        # 5 attempts, 30→45→67→100→120s backoff (~6 min total).
        delay = 30.0
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                resp = cffi_requests.get(url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                transient = (
                    "could not resolve" in msg
                    or "could not connect" in msg
                    or "name resolution" in msg
                    or "no address" in msg
                    or "timed out" in msg
                    or "connection refused" in msg
                    or "failed to connect" in msg
                )
                if not transient or attempt == 4:
                    raise
                import sys as _sys
                print(
                    f"[polymarket-client] transient fetch error "
                    f"(attempt {attempt + 1}/5): {exc!r} — "
                    f"waiting {delay:.0f}s",
                    file=_sys.stderr,
                )
                _t.sleep(delay)
                delay = min(delay * 1.5, 120)
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    def list_markets(
        self,
        *,
        active: Optional[bool] = True,
        closed: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume24hr",
        ascending: bool = False,
        min_volume_24hr: float = 0.0,
        min_liquidity: float = 0.0,
        exclude_meme_events: bool = True,
    ) -> list[BinaryMarket]:
        """One page of markets sorted server-side by `order`, then locally
        filtered by volume / liquidity / meme-event blacklist.

        Gamma's default sort is internal id (effectively random for our
        purposes). We default to `volume24hr` so the morning queue front-
        loads "what's actually being traded right now" rather than dead
        markets that happen to be `active=true`.
        """
        params: dict = {
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": "true" if ascending else "false",
        }
        if active is not None:
            params["active"] = "true" if active else "false"
        if closed is not None:
            params["closed"] = "true" if closed else "false"
        body = self._get(self.config.gamma_base, "/markets", params=params)
        records = body if isinstance(body, list) else (
            body.get("markets") or body.get("data") or []
        )

        out: list[BinaryMarket] = []
        for m in records:
            if exclude_meme_events and is_meme_event(m):
                continue
            v24 = market_volume_24hr(m)
            if v24 < min_volume_24hr:
                continue
            try:
                liq = float(m.get("liquidity") or 0)
            except (TypeError, ValueError):
                liq = 0.0
            if liq < min_liquidity:
                continue
            out.append(parse_market(m))
        return out

    def iter_markets(
        self,
        *,
        active: Optional[bool] = True,
        closed: Optional[bool] = None,
        max_pages: int = 5,
        page_size: int = 100,
        order: str = "volume24hr",
        ascending: bool = False,
        min_volume_24hr: float = 0.0,
        min_liquidity: float = 0.0,
        exclude_meme_events: bool = True,
    ) -> Iterator[BinaryMarket]:
        for page_idx in range(max_pages):
            page = self.list_markets(
                active=active,
                closed=closed,
                limit=page_size,
                offset=page_idx * page_size,
                order=order,
                ascending=ascending,
                min_volume_24hr=min_volume_24hr,
                min_liquidity=min_liquidity,
                exclude_meme_events=exclude_meme_events,
            )
            if not page:
                return
            yield from page

    def get_market(self, condition_id_or_slug: str) -> BinaryMarket:
        body = self._get(
            self.config.gamma_base, f"/markets/{condition_id_or_slug}"
        )
        return parse_market(body if isinstance(body, dict) else body[0])

    def get_history(
        self,
        condition_id: str,
        *,
        interval: str = "1h",
        fidelity: int = 720,
    ) -> list[PriceTick]:
        params = {"market": condition_id, "interval": interval, "fidelity": fidelity}
        body = self._get(self.config.clob_base, "/prices-history", params=params)
        return parse_history(body)
