"""Kalshi REST API client — read-only, demo + prod symmetric.

Kalshi is a CFTC-registered Designated Contract Market (DCM). Open to
NY residents. Demo environment at https://demo-api.kalshi.co serves the
exact same JSON shapes as production, so the parser is identical.

Endpoints exercised by this client (all GET, all public except portfolio):
  GET /trade-api/v2/markets           — list markets, paginated
  GET /trade-api/v2/markets/{ticker}  — single market
  GET /trade-api/v2/markets/{ticker}/history  — price history (1h fidelity)

We deliberately do NOT wire authenticated endpoints (portfolio, orders,
positions) in v0.1. That keeps the loop physically incapable of placing
a trade — the executor.py file only emits CSV, and you place every trade
by hand on kalshi.com. v0.2 may add auth; for now read-only.

Reference: https://trading-api.readme.io/reference/getmarkets
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from markets.market import BinaryMarket, PriceTick


DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"
PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"


@dataclass
class KalshiConfig:
    """Pick demo or prod base URL. No auth fields — read-only client."""
    base_url: str = DEMO_BASE
    user_agent: str = "Orallexa-Markets/0.1 (read-only)"
    timeout_sec: int = 20

    @classmethod
    def demo(cls) -> "KalshiConfig":
        return cls(base_url=DEMO_BASE)

    @classmethod
    def prod(cls) -> "KalshiConfig":
        return cls(base_url=PROD_BASE)


def _category_from_event_ticker(event_ticker: str) -> str:
    """Best-effort category bucket from Kalshi's event-ticker prefix.

    Kalshi prefixes with `KX` for most markets in their post-2024 schema
    (e.g. KXNBAGAME, KXMLBRFI, KXFED, KXNFL). Older series use bare prefixes
    (POTUS, SENATE). We use substring match on the first dash-segment to
    catch both forms.
    """
    pref = event_ticker.upper().split("-")[0]
    politics = ("POTUS", "SENATE", "HOUSE", "PRES", "ELECT", "GOV", "MAYOR")
    geopolitics = ("WAR", "NATO", "UN", "RUS", "CHINA", "IRAN", "ISRAEL")
    economics = ("FED", "CPI", "GDP", "NFP", "UNRATE", "PCE", "FOMC")
    science = ("NASA", "WHO", "AI", "OPENAI", "ANTHRO")
    weather = ("HIGH", "LOW", "RAIN", "SNOW", "HURRICANE", "TEMP")
    sports = ("NBA", "NFL", "MLB", "NHL", "TENNIS", "GOLF", "UFC", "F1",
              "GAME", "MLBGAME", "MLBRFI", "NBAGAME", "NFLGAME")
    crypto = ("BTC", "ETH", "SOL", "DOGE")

    def hit(kws) -> bool:
        return any(kw in pref for kw in kws)

    if hit(politics):
        return "politics"
    if hit(geopolitics):
        return "geopolitics"
    if hit(economics):
        return "economics"
    if hit(science):
        return "science"
    if hit(weather):
        return "weather"
    if hit(sports):
        return "sports"
    if hit(crypto):
        return "crypto"
    return "other"


def _normalize_status(raw_status: str) -> str:
    """Kalshi status → BinaryMarket status. Returns one of:
    open / closed / settled / finalized.
    """
    s = (raw_status or "").lower()
    if s in ("active", "initialized"):
        return "open"
    if s in ("closed",):
        return "closed"
    if s in ("settled",):
        return "settled"
    if s in ("finalized", "determined"):
        return "finalized"
    return "open"


def _normalize_outcome(raw: dict) -> Optional[int]:
    """Pull the YES/NO outcome out of a settled market record.

    Kalshi exposes `result` ∈ {"yes", "no", ""}. Anything else (or empty)
    means unresolved and we return None.
    """
    result = (raw.get("result") or "").lower()
    if result == "yes":
        return 1
    if result == "no":
        return 0
    return None


def parse_market(raw: dict) -> BinaryMarket:
    """Pure function: Kalshi JSON record → BinaryMarket. Fixture-tested.

    Field map (Kalshi 2024+ schema → BinaryMarket):
      ticker                → market_id, ticker
      event_ticker          → category (heuristic)
      title                 → question
      status                → status (normalized)
      last_price_dollars    → yes_price (already in 0..1 USD, no division)
      yes_bid_dollars       → yes_bid
      yes_ask_dollars       → yes_ask
      notional_value_dollars→ volume    (Kalshi reports notional, not contracts)
      open_interest_fp      → open_interest
      result                → outcome (YES=1, NO=0, unresolved=None)

    The pre-2024 schema used `last_price` in cents; we still accept those
    via a fallback so fixtures and older recordings continue parsing.
    """
    ticker = raw["ticker"]
    event_ticker = raw.get("event_ticker", "")
    status = _normalize_status(raw.get("status", ""))

    def dollars(x) -> Optional[float]:
        """Field already in dollars (0..1 range), pass through."""
        if x is None:
            return None
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def cents_to_unit(x) -> Optional[float]:
        """Legacy: field in cents (0..100), divide by 100."""
        if x is None:
            return None
        try:
            return float(x) / 100.0
        except (TypeError, ValueError):
            return None

    yes_price = dollars(raw.get("last_price_dollars"))
    if yes_price is None:
        yes_price = cents_to_unit(raw.get("last_price"))
    yes_bid = dollars(raw.get("yes_bid_dollars"))
    if yes_bid is None:
        yes_bid = cents_to_unit(raw.get("yes_bid"))
    yes_ask = dollars(raw.get("yes_ask_dollars"))
    if yes_ask is None:
        yes_ask = cents_to_unit(raw.get("yes_ask"))

    volume = (
        raw.get("notional_value_dollars")
        or raw.get("volume_24h_dollars")
        or raw.get("volume")
        or 0
    )
    open_interest = (
        raw.get("open_interest_fp") or raw.get("open_interest") or 0
    )

    return BinaryMarket(
        platform="kalshi",
        market_id=ticker,
        ticker=ticker,
        question=raw.get("title") or raw.get("subtitle") or ticker,
        category=_category_from_event_ticker(event_ticker),
        status=status,  # type: ignore[arg-type]
        open_time=raw.get("open_time"),
        close_time=raw.get("close_time"),
        expiration_time=raw.get("expiration_time"),
        settled_at=raw.get("settle_time") or raw.get("settled_time"),
        yes_price=yes_price,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        volume=float(volume) if volume else 0.0,
        open_interest=float(open_interest) if open_interest else 0.0,
        outcome=_normalize_outcome(raw),
        description=raw.get("rules_primary") or raw.get("subtitle") or "",
        raw=raw,
    )


def parse_history(raw: dict) -> list[PriceTick]:
    """Kalshi /history response → list[PriceTick].

    Kalshi history records: {history: [{ts: <unix>, yes_price: <cents>}, ...]}
    """
    ticks: list[PriceTick] = []
    for row in raw.get("history") or []:
        ts = row.get("ts")
        yes_cents = row.get("yes_price")
        if ts is None or yes_cents is None:
            continue
        try:
            ticks.append(PriceTick(t=int(ts), yes=float(yes_cents) / 100.0))
        except (TypeError, ValueError):
            continue
    return ticks


class KalshiClient:
    """Read-only Kalshi REST client.

    Lazy-imports requests so the module can be imported without the dep
    in test contexts that only exercise `parse_market` / `parse_history`.
    """

    def __init__(self, config: Optional[KalshiConfig] = None):
        self.config = config or KalshiConfig.demo()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        import requests  # lazy
        url = f"{self.config.base_url}{path}"
        resp = requests.get(
            url,
            params=params or {},
            headers={"User-Agent": self.config.user_agent, "Accept": "application/json"},
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()

    def list_markets(
        self,
        *,
        status: Optional[str] = "open",
        limit: int = 100,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
    ) -> tuple[list[BinaryMarket], Optional[str]]:
        """One page of markets + next cursor (None if no more pages)."""
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        body = self._get("/markets", params=params)
        markets = [parse_market(m) for m in body.get("markets") or []]
        next_cursor = body.get("cursor") or None
        return markets, next_cursor

    def iter_markets(
        self,
        *,
        status: Optional[str] = "open",
        max_pages: int = 5,
        event_ticker: Optional[str] = None,
    ) -> Iterator[BinaryMarket]:
        """Paginate up to max_pages."""
        cursor: Optional[str] = None
        for _ in range(max_pages):
            page, cursor = self.list_markets(
                status=status, cursor=cursor, event_ticker=event_ticker
            )
            yield from page
            if not cursor:
                return

    def get_market(self, ticker: str) -> BinaryMarket:
        body = self._get(f"/markets/{ticker}")
        return parse_market(body["market"])

    def get_history(
        self,
        ticker: str,
        *,
        period_interval_min: int = 60,
    ) -> list[PriceTick]:
        params = {"period_interval": period_interval_min}
        body = self._get(f"/markets/{ticker}/history", params=params)
        return parse_history(body)
