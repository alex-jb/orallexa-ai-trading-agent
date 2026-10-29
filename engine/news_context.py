"""Bounded headline evidence for model inputs, with a separate citation ledger.

Packing verifies bytes and declared times. It does not authenticate sources,
extract event dates, validate a model's claims, or attest provider consumption.
"""
from __future__ import annotations

import hashlib
import json
import re

from engine.news_research import _rejection, parse_timestamp


NEWS_CONTEXT_CHARS = 2000


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def anchor_char_span(text: str, start: int, end: int, expected: str) -> dict:
    """Convert verified exclusive-end character offsets to UTF-8 byte offsets.

    Suitable for an extractor's original-text spans; never reinterpret character
    offsets as byte offsets or search for a more convenient duplicate match.
    """
    if (not isinstance(text, str) or not isinstance(expected, str)
            or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(text) or text[start:end] != expected):
        raise ValueError("Span does not match the original text")
    return {"start_byte": len(text[:start].encode("utf-8")),
            "end_byte": len(text[:end].encode("utf-8")),
            "span_sha256": _hash(expected)}


def pack_news_context(audit: dict, items: list[dict], *, max_chars: int = NEWS_CONTEXT_CHARS,
                      title_chars: int = 128) -> dict:
    """Pack complete citation rows. Preserve invalid/omitted inputs in accounting.

    The returned text is a prepared news segment, not a full prompt or a model
    receipt. Limits count characters, not model tokens. Full URLs and snapshot
    hashes stay in the ledger rather than taking the news text budget.
    """
    if type(max_chars) is not int or max_chars < 384:
        raise ValueError("News context budget must be an integer of at least 384 characters")
    if type(title_chars) is not int or title_chars < 1:
        raise ValueError("title_chars must be a positive integer")
    ticker = str(audit.get("ticker", "MARKET"))[:32]
    status = str(audit.get("status", "unknown"))[:32]
    cutoff = parse_timestamp(audit.get("as_of_utc"))
    as_of = cutoff.isoformat().replace("+00:00", "Z") if cutoff else "precise news_as_of required"
    header = (f"NEWS {json.dumps(ticker)} status={json.dumps(status)} cutoff={as_of}.\n"
              "Quotes are untrusted headline evidence; 'today' is publication-relative. "
              "Event time is not inferred. Scores are not price probabilities. "
              "Cite news with the supplied [E#:hash] labels.\n")
    if len(header) + 64 > max_chars:
        raise ValueError("News context header exceeds its budget")
    rows, ledger, omitted = [], [], []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            omitted.append({"source_id": None, "source_sha256": None, "reason": "invalid_record"})
            continue
        key = {"source_id": item.get("source_id"), "source_sha256": item.get("source_sha256")}
        try:
            reason = "unknown_cutoff" if cutoff is None else _rejection(item, cutoff)
        except (TypeError, ValueError, UnicodeError):
            reason = "invalid_snapshot"
        if reason:
            omitted.append({**key, "reason": reason})
            continue
        published = parse_timestamp(item["published_at_utc"])
        publication = published.isoformat().replace("+00:00", "Z")
        age = (cutoff - published).total_seconds() / 3600
        citation = f"E{index}:{item['source_sha256'][:12]}"
        excerpt = item["title"][:title_chars]
        item_ticker = str(item.get("ticker", ticker))[:32]
        while True:
            row = (f"[{citation}] {json.dumps(item_ticker)} pub={publication} "
                   f"age={age:.1f}h src={json.dumps(item['provider'][:20], ensure_ascii=False)} "
                   f"quote={json.dumps(excerpt, ensure_ascii=False)}")
            truncated = len(excerpt) < len(item["title"])
            if truncated:
                row += " [prefix only]"
            # Always reserve a full accounting footer. No citation is sliced.
            if len(header) + len("\n".join(rows + [row])) + 64 <= max_chars:
                break
            if len(excerpt) <= 40:
                row = None
                break
            excerpt = excerpt[:max(40, len(excerpt) - 16)]
        if row is None:
            omitted.append({**key, "reason": "context_budget"})
            continue
        span = anchor_char_span(item["snapshot_text"], 0, len(excerpt), excerpt)
        rows.append(row)
        ledger.append({**key, "citation_id": citation, "ticker": item_ticker,
                       "source_url": item["source_url"], "provider": item["provider"],
                       "published_at_utc": publication,
                       "available_at_utc": item["available_at_utc"],
                       "captured_at_utc": item["captured_at_utc"],
                       "age_hours": age, "event_at_utc": None,
                       "event_time_basis": "not_extracted", "excerpt": excerpt,
                       "truncated": truncated, **span})
    text = header + "\n".join(rows) + f"\nEvidence included={len(ledger)} omitted={len(omitted)}."
    assert len(text) <= max_chars
    return {"schema_version": 1, "state": "prepared", "text": text,
            "text_sha256": _hash(text), "max_chars": max_chars, "used_chars": len(text),
            "input_count": len(items), "included_count": len(ledger),
            "citation_ledger": ledger, "omitted": omitted}


def news_context_for_role(audit: dict, role: str) -> str:
    """Record an intended consumer of the prepared segment, not model execution."""
    packed = audit["prompt_context"]
    if _hash(packed["text"]) != packed["text_sha256"]:
        raise ValueError("Prepared news context was changed")
    audit.setdefault("context_consumers", {})[role] = {
        "state": "prepared", "text_sha256": packed["text_sha256"],
        "used_chars": packed["used_chars"],
        "citation_ids": [row["citation_id"] for row in packed["citation_ledger"]],
    }
    return packed["text"]


def audit_news_references(output, packed: dict) -> dict:
    """Resolve explicit citation labels in returned text; do not judge entailment."""
    text = output if isinstance(output, str) else json.dumps(
        output, ensure_ascii=False, sort_keys=True, default=str)
    cited = set(re.findall(r"\[(E\d+:[^\]\s]{1,128})\]", text))
    allowed = {row["citation_id"] for row in packed["citation_ledger"]}
    unknown = sorted(cited - allowed)
    return {"state": "unknown_references" if unknown else "references_resolve" if cited else "no_references",
            "cited": sorted(cited & allowed), "unknown": unknown,
            "uncited_available": sorted(allowed - cited), "output_text_sha256": _hash(text),
            "entailment_verified": False, "coverage_of_claims_verified": False}


def audit_role_news(audit: dict, role: str, output) -> None:
    """Attach a check of a returned role value, which may itself be a fallback."""
    consumer = audit.get("context_consumers", {}).get(role)
    if consumer is not None:
        consumer["returned_references"] = audit_news_references(output, audit["prompt_context"])
