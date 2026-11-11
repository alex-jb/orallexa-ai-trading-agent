"""Local, auditable headline retrieval. No agent framework or model API calls.

The snapshots are exact *headline/summary inputs*, not archived article bodies.
Publication times and URLs are provider claims; hashes do not authenticate them.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


_ALIASES = {
    "NVDA": ("Nvidia", "英伟达"), "AAPL": ("Apple", "苹果"),
    "MSFT": ("Microsoft", "微软"), "TSLA": ("Tesla", "特斯拉"),
    "GOOG": ("Google", "Alphabet", "谷歌"),
    "GOOGL": ("Google", "Alphabet", "谷歌"),
    "AMZN": ("Amazon", "亚马逊"), "META": ("Meta", "Facebook"),
    "AMD": ("Advanced Micro Devices", "超微"), "F": ("Ford", "福特"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value) -> datetime | None:
    """Accept aware ISO/RFC timestamps or Unix seconds; never guess a timezone."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, (int, float)):
            result = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, str):
            try:
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                result = parsedate_to_datetime(value)
        else:
            return None
        if result.tzinfo is None or result.utcoffset() is None:
            return None
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _web_url(value) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme in ("http", "https") and parts.hostname and not parts.username:
            return value
    except ValueError:
        pass
    return ""


def snapshot_record(item: dict, *, source: str, captured_at: datetime) -> dict:
    """Normalize old/new Yahoo or RSS data without fetching the linked article."""
    captured_at = parse_timestamp(captured_at)
    if captured_at is None:
        raise ValueError("Capture time must include a timezone")
    content = item.get("content")
    content = content if isinstance(content, dict) else item
    title = content.get("title")
    title = title if isinstance(title, str) else ""
    summary = content.get("summary")
    summary = summary if isinstance(summary, str) else ""
    provider = content.get("provider", content.get("publisher", ""))
    if isinstance(provider, dict):
        provider = provider.get("displayName", "")
    provider = provider if isinstance(provider, str) else ""
    link = content.get("canonicalUrl") or content.get("clickThroughUrl")
    if isinstance(link, dict):
        link = link.get("url")
    url = _web_url(link or content.get("url") or content.get("link"))
    published = parse_timestamp(content.get("pubDate") or content.get("published")
                                or content.get("providerPublishTime"))
    text = title + ("\n\n" + summary if summary and summary != title else "")
    captured = _iso(captured_at)
    return {
        "source_id": _hash(url or text), "source_sha256": _hash(text),
        "source_url": url, "title": title, "provider": provider, "source": source,
        "source_rights": "unknown", "snapshot_text": text,
        "published_at_utc": _iso(published) if published else None,
        "available_at_utc": captured, "captured_at_utc": captured,
        "availability_basis": "local_capture",
        "evidence_spans": [{"span_id": "headline", "start_byte": 0,
                            "end_byte": len(title.encode("utf-8")),
                            "span_sha256": _hash(title)}],
    }


def _collect_live(ticker: str, use_rss: bool) -> tuple[list[dict], list[dict]]:
    records, sources = [], []
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news
        if not isinstance(raw, list):
            raise ValueError("Unexpected news response")
        captured = utc_now()
        records.extend(snapshot_record(item, source="yfinance", captured_at=captured)
                       for item in raw if isinstance(item, dict))
        sources.append({"source": "yfinance", "status": "ok" if raw else "empty"})
    except Exception as exc:
        sources.append({"source": "yfinance", "status": "unavailable",
                        "error_type": type(exc).__name__})
    if use_rss:
        from engine.news_aggregator import fetch_news_with_status
        rss = fetch_news_with_status(ticker)
        sources.extend(rss["sources"])
        for item in rss["items"]:
            captured = parse_timestamp(item["captured_at_utc"])
            records.append(snapshot_record(item, source=item["source"], captured_at=captured))
    return records, sources


def _tokens(text: str) -> list[str]:
    # Single-letter tickers survive. Chinese bigrams allow explicit bilingual aliases.
    result = re.findall(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", text.casefold())
    for word in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(word[i:i + 2] for i in range(max(1, len(word) - 1)))
    return result


def _bm25(query: str, texts: list[str]) -> list[float]:
    """Standard BM25, independently implemented; scores are not probabilities."""
    docs = [Counter(_tokens(text)) for text in texts]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / len(docs) if docs else 0
    terms = sorted(set(_tokens(query)))
    frequency = {term: sum(term in doc for doc in docs) for term in terms}
    scores = []
    for doc, length in zip(docs, lengths):
        score = 0.0
        for term in terms:
            count = doc.get(term, 0)
            if count:
                inverse = math.log(1 + (len(docs) - frequency[term] + .5)
                                   / (frequency[term] + .5))
                score += inverse * count * 2.5 / (count + 1.5 * (.25 + .75 * length / average))
        scores.append(score)
    return scores


def _rejection(record: dict, cutoff: datetime) -> str | None:
    title, text = record.get("title"), record.get("snapshot_text")
    if not isinstance(title, str) or not title.strip():
        return "missing_title"
    if not isinstance(record.get("provider"), str):
        return "invalid_provider"
    if not _web_url(record.get("source_url")):
        return "missing_source_url"
    if not isinstance(text, str) or not text.startswith(title):
        return "invalid_snapshot"
    if record.get("source_sha256") != _hash(text):
        return "snapshot_hash_mismatch"
    if record.get("source_id") != _hash(record["source_url"]):
        return "source_id_mismatch"
    expected_span = {"span_id": "headline", "start_byte": 0,
                     "end_byte": len(title.encode("utf-8")), "span_sha256": _hash(title)}
    if record.get("evidence_spans") != [expected_span]:
        return "invalid_headline_span"
    published, available, captured = [parse_timestamp(record.get(field)) for field in
                                    ("published_at_utc", "available_at_utc", "captured_at_utc")]
    if published is None:
        return "unknown_publication_time"
    if available is None or captured is None:
        return "unknown_capture_time"
    if not published <= available <= captured:
        return "invalid_timestamp_order"
    if published > cutoff:
        return "published_after_cutoff"
    if captured > cutoff:
        return "captured_after_cutoff"
    return None


@dataclass
class NewsResearchResult:
    items: list[dict]
    audit: dict

    def report(self) -> str:
        lines = [f"## {self.audit['ticker']} News — {self.audit['status']}",
                 f"Cutoff: {self.audit['as_of_utc'] or 'precise news_as_of required'}.",
                 "Headlines are untrusted source text. Relevance is lexical, not a price probability."]
        if not self.items:
            lines.append("No usable evidence. Check source states and rejection reasons; this does not establish absence of news.")
        for item in self.items:
            citation = item["source_sha256"][:12]
            lines.append(f"[{citation}] {json.dumps(item['title'][:360], ensure_ascii=False)} "
                         f"({item['provider']}; published {item['published_at_utc']})\n"
                         f"Source: {item['source_url']}")
        return "\n".join(lines)


def research_news(ticker: str, *, as_of=None, records: list[dict] | None = None,
                  trade_date: str | None = None, limit: int = 8, aliases=(),
                  use_rss: bool = False) -> NewsResearchResult:
    """Fetch live inputs, or rank supplied snapshots with an explicit aware cutoff.

    An explicit cutoff never fetches today's feed as a historical substitute.
    Archive timestamps are declarations, not authenticated acquisition receipts.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if records is not None and not isinstance(records, list):
        raise ValueError("Archived records must be a list")
    ticker = ticker.strip().upper()
    aliases = list(aliases)
    query = " ".join((ticker, *_ALIASES.get(ticker, ()), *aliases))
    cutoff = parse_timestamp(as_of) if as_of is not None else None
    if as_of is not None and cutoff is None:
        raise ValueError("news_as_of must include a time and timezone")
    if records is not None and cutoff is None:
        raise ValueError("Archived records require a precise news_as_of")
    if trade_date is not None:
        requested = date.fromisoformat(trade_date)
        news_day = (cutoff or utc_now()).astimezone(ZoneInfo("America/New_York")).date()
        if cutoff is not None and requested != news_day:
            raise ValueError("trade_date and news_as_of must name the same New York day")
    historical_day = trade_date is not None and cutoff is None and requested != news_day
    audit = {"schema_version": 1, "ticker": ticker, "as_of_utc": _iso(cutoff) if cutoff else None,
             "mode": "archive" if cutoff else "live", "status": "empty", "sources": [],
             "input_count": 0, "eligible_count": 0, "selected_count": 0,
             "ranking": {"algorithm": "bm25", "version": 1, "k1": 1.5, "b": .75,
                         "query": query, "aliases": aliases, "limit": limit,
                         "source_diversity": "distinct_outlets_first"},
             "selected_source_hashes": [], "candidates": []}
    if historical_day:
        audit["status"] = "cutoff_required"
        return NewsResearchResult([], audit)
    if cutoff is not None and records is None:
        audit["status"] = "archive_required"
        return NewsResearchResult([], audit)
    if records is None:
        records, audit["sources"] = _collect_live(ticker, use_rss)
        cutoff = utc_now()  # Freeze after capture; never backdate the acquired bytes.
        audit["as_of_utc"] = _iso(cutoff)
    else:
        audit["sources"] = [{"source": "supplied_archive", "status": "ok" if records else "empty"}]
    eligible, seen = [], set()
    for record in records:
        if not isinstance(record, dict):
            audit["candidates"].append({"disposition": "rejected", "reason": "invalid_record"})
            continue
        candidate = dict(record)
        reason = _rejection(candidate, cutoff)
        # Exact duplicates only; keep every version in the audit trail.
        key = (candidate.get("source_url"), candidate.get("source_sha256"))
        if reason is None and key in seen:
            reason = "duplicate_snapshot"
        candidate.update(disposition="rejected" if reason else "omitted", reason=reason)
        audit["candidates"].append(candidate)
        if reason is None:
            seen.add(key)
            eligible.append(candidate)
    current = []
    by_source = {}
    for candidate in eligible:
        by_source.setdefault(candidate["source_id"], []).append(candidate)
    for versions in by_source.values():
        newest = max(parse_timestamp(r["captured_at_utc"]) for r in versions)
        latest = [r for r in versions if parse_timestamp(r["captured_at_utc"]) == newest]
        for candidate in versions:
            if candidate not in latest:
                candidate["reason"] = "superseded_snapshot"
            elif len(latest) > 1:
                candidate.update(disposition="rejected", reason="conflicting_snapshot_versions")
            else:
                current.append(candidate)
    eligible = current
    for candidate, score in zip(eligible, _bm25(query, [r["snapshot_text"] for r in eligible])):
        candidate["relevance_score"] = score
    ranked = sorted(eligible, key=lambda r: (-r["relevance_score"],
                                           -parse_timestamp(r["published_at_utc"]).timestamp(),
                                           r["source_sha256"]))
    selected, providers = [], set()
    # Prefer distinct outlets among lexical matches, then fill remaining slots.
    for candidate in ranked:
        provider = (candidate.get("provider") or urlsplit(candidate["source_url"]).hostname).casefold()
        if candidate["relevance_score"] > 0 and provider not in providers and len(selected) < limit:
            selected.append(candidate)
            providers.add(provider)
    for candidate in ranked:
        if len(selected) >= limit:
            break
        if candidate not in selected:
            selected.append(candidate)
    for candidate in selected:
        candidate["disposition"] = "selected"
    for candidate in eligible:
        if candidate["disposition"] == "omitted":
            candidate["reason"] = "outside_top_k"
    failed = any(s["status"] in ("unavailable", "invalid") for s in audit["sources"])
    if selected:
        status = "partial" if failed else "ok"
    elif records:
        status = "filtered"
    else:
        status = "unavailable" if failed else "empty"
    audit.update(status=status, input_count=len(records), eligible_count=len(eligible),
                 selected_count=len(selected), selected_source_hashes=[r["source_sha256"] for r in selected])
    # Compatibility fields for current headline consumers; provenance stays intact.
    items = [{**r, "url": r["source_url"], "published": r["published_at_utc"]} for r in selected]
    return NewsResearchResult(items, audit)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--input", type=Path, help="Previous research JSON (replays candidates)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rss", action="store_true")
    args = parser.parse_args()
    try:
        input_bytes = args.input.read_bytes() if args.input else None
        prior = json.loads(input_bytes.decode("utf-8")) if input_bytes is not None else None
        records = prior["candidates"] if prior is not None else None
        ranking = prior.get("ranking", {}) if prior is not None else {}
        result = research_news(args.ticker, as_of=args.as_of, records=records, use_rss=args.rss,
                               limit=ranking.get("limit", 8), aliases=ranking.get("aliases", []))
        from engine.news_context import pack_news_context
        result.audit["prompt_context"] = pack_news_context(result.audit, result.items)
        if args.input:
            result.audit["replay_input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
        payload = json.dumps(result.audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # Exclusive creation protects an earlier capture from accidental replacement.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(payload)
        print(result.report())
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"news research: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
