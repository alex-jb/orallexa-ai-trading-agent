"""
engine/news_aggregator.py
──────────────────────────────────────────────────────────────────
Multi-platform news aggregator — Google News RSS + Yahoo Finance RSS,
with fuzzy title dedup.

Inspired by sansan0/TrendRadar — one ticker often generates 5-15
articles across outlets that are slight rewordings of the same story.
We aggregate, dedupe by title prefix/containment, and prefer premium
providers when duplicates collide.

Usage:
    from engine.news_aggregator import fetch_aggregated_news
    items = fetch_aggregated_news("NVDA", limit=10)
    for it in items:
        print(it["title"], it["provider"], it["url"])

Only stdlib + requests (no feedparser dep). RSS XML parsed via
xml.etree. Failures in any one source fall back silently.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

_UA = "oralexxa/1.0 news aggregator"
_HTTP_TIMEOUT = 5.0
_GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?q={q}+stock&hl=en-US&gl=US&ceid=US:en"
)
_YAHOO_RSS_URL = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"
)

# Premium providers get a small ranking boost on dedup collisions
_PROVIDER_RANK = {
    "reuters": 3,
    "bloomberg": 3,
    "wsj": 3,
    "wall street journal": 3,
    "financial times": 3,
    "ft": 3,
    "cnbc": 2,
    "marketwatch": 2,
    "barron's": 2,
    "barrons": 2,
    "yahoo": 1,
    "yahoo finance": 1,
    "seeking alpha": 1,
    "benzinga": 1,
}


def fetch_aggregated_news(ticker: str, limit: int = 15) -> list[dict]:
    """
    Fetch news for `ticker` from multiple RSS sources, dedupe, and return
    the top `limit` items ordered by recency.

    Each item: {title, url, provider, published, source}.
    """
    items = _fetch_google_news(ticker) + _fetch_yahoo_rss(ticker)
    return _dedupe_and_rank(items, limit=limit)


def _fetch_google_news(ticker: str) -> list[dict]:
    url = _GOOGLE_NEWS_URL.format(q=quote_plus(ticker))
    xml = _get_xml(url)
    if xml is None:
        return []
    return _parse_rss(xml, source="google_news")


def _fetch_yahoo_rss(ticker: str) -> list[dict]:
    url = _YAHOO_RSS_URL.format(t=quote_plus(ticker))
    xml = _get_xml(url)
    if xml is None:
        return []
    return _parse_rss(xml, source="yahoo_finance")


def _get_xml(url: str) -> Optional[bytes]:
    try:
        import requests
        resp = requests.get(
            url,
            headers={"User-Agent": _UA, "Accept": "application/rss+xml,application/xml"},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.content
    except Exception as e:
        logger.debug("RSS fetch failed %s: %s", url, e)
        return None


def _parse_rss(xml_bytes: bytes, source: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.debug("RSS parse failed for %s: %s", source, e)
        return []

    out: list[dict] = []
    # RSS 2.0 channel/item structure
    for item in root.iter("item"):
        title = _text(item, "title")
        link = _text(item, "link")
        pub = _text(item, "pubDate") or _text(item, "{http://purl.org/dc/elements/1.1/}date")
        provider = _extract_provider(item, title, link, default_source=source)
        if not title or not link:
            continue
        out.append({
            "title": title.strip(),
            "url": link.strip(),
            "provider": provider,
            "published": pub or "",
            "source": source,
        })
    return out


def _text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _extract_provider(item: ET.Element, title: str, link: str, default_source: str) -> str:
    """Best-effort provider extraction from RSS item."""
    # Google News puts source in <source> child or in the title suffix (" - Publisher")
    src = item.find("source")
    if src is not None and src.text:
        return src.text.strip()
    # Title ends with " - Publisher"
    m = re.search(r"\s-\s([^-]+)$", title)
    if m:
        return m.group(1).strip()
    # Extract domain from URL
    m2 = re.search(r"https?://(?:www\.)?([^/]+)", link)
    if m2:
        return m2.group(1).split(".")[0]
    return default_source


def _normalize_title(title: str) -> str:
    """Lowercase, strip publisher tail, strip punctuation, collapse whitespace."""
    t = title.lower()
    # Strip publisher tails FIRST (before punctuation): " - Reuters", " | Bloomberg"
    t = re.sub(r"\s+[-|]\s+\w[\w\s&.']{0,40}$", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_pub_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _provider_rank(provider: str) -> int:
    p = provider.lower()
    for key, rank in _PROVIDER_RANK.items():
        if key in p:
            return rank
    return 0


def _dedupe_and_rank(items: list[dict], limit: int) -> list[dict]:
    """
    Dedupe by normalized-title prefix/containment. On collision, keep the
    item from the higher-ranked provider. Return newest-first up to `limit`.
    """
    buckets: list[dict] = []
    seen_norm: list[str] = []

    for it in items:
        norm = _normalize_title(it["title"])
        if len(norm) < 10:
            continue

        # Dedup: first 60 chars containment in either direction
        key = norm[:60]
        collision_idx: Optional[int] = None
        for i, prev in enumerate(seen_norm):
            prev_key = prev[:60]
            if key == prev_key or key in prev or prev in key:
                collision_idx = i
                break

        dt = _parse_pub_date(it.get("published", ""))

        enriched = {**it, "normalized_title": norm, "_published_dt": dt}

        if collision_idx is None:
            buckets.append(enriched)
            seen_norm.append(norm)
            continue

        # Collision — keep the higher-ranked provider. Tiebreak: newer date.
        existing = buckets[collision_idx]
        new_rank = _provider_rank(enriched["provider"])
        old_rank = _provider_rank(existing["provider"])
        if new_rank > old_rank:
            buckets[collision_idx] = enriched
        elif new_rank == old_rank:
            old_dt = existing.get("_published_dt")
            if dt and (old_dt is None or dt > old_dt):
                buckets[collision_idx] = enriched

    # Sort newest-first (missing dates sink)
    buckets.sort(key=lambda x: x.get("_published_dt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Drop internal fields
    out = []
    for b in buckets[:limit]:
        out.append({
            "title": b["title"],
            "url": b["url"],
            "provider": b["provider"],
            "published": b["published"],
            "source": b["source"],
        })
    return out
