"""Resolve news mentions against a captured SEC ticker/CIK directory.

This is a research association, not event attribution or a trading signal.
The caller supplies capture times; matching hashes do not authenticate them.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from types import MappingProxyType
import unicodedata

from engine.news_context import anchor_char_span
from engine.news_research import _iso, _rejection, parse_timestamp


SEC_DIRECTORY_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_SYMBOL = r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*"
_SUFFIXES = frozenset({"inc", "corp", "co", "ltd", "plc", "llc", "lp", "llp", "ag", "sa", "nv", "se"})
_SUFFIX_SPELLINGS = {"incorporated": "inc", "corporation": "corp", "company": "co", "limited": "ltd"}


def _symbol_key(value: str) -> str | None:
    if not isinstance(value, str) or not value.isascii() or len(value) > 32:
        return None
    value = value.upper()
    return value.replace("-", ".") if re.fullmatch(_SYMBOL, value) else None


def _cik(value) -> str | None:
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value) or not int(value):
        return None
    return value.zfill(10)


def _name_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    # EDGAR conformed names can end in jurisdiction text such as /UK or /DE/.
    value = re.sub(r"\s+/[a-z]{2,6}/?$", "", value)
    words = re.sub(r"[.,]", " ", value).split()
    if words:
        words[-1] = _SUFFIX_SPELLINGS.get(words[-1], words[-1])
    return " ".join(words)


def _short_name(name: str) -> str:
    words = name.split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


def _venue(value: str) -> str:
    return " ".join(value.upper().split())


@dataclass(frozen=True)
class Listing:
    cik: str
    name: str
    ticker: str
    exchange: str | None


class IssuerDirectory:
    """An in-memory index of the exact bytes in one SEC directory capture."""

    def __init__(self, rows: tuple[Listing, ...], receipt: dict):
        self.rows = rows
        self.receipt = MappingProxyType(receipt.copy())
        self._symbols = defaultdict(list)
        self._names = defaultdict(list)
        self._short_names = defaultdict(list)
        self._issuers = defaultdict(list)
        for row in rows:
            self._symbols[_symbol_key(row.ticker)].append(row)
            name = _name_key(row.name)
            self._names[name].append(row)
            short = _short_name(name)
            if short != name:
                self._short_names[short].append(row)
            self._issuers[row.cik].append(row)
        venues = sorted({row.exchange for row in rows if row.exchange}, key=lambda venue: (-len(venue), venue))
        qualifiers = "|".join(re.escape(venue) for venue in venues)
        notation = r"CIK:[0-9]{1,10}|\$[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*"
        if qualifiers:
            notation += rf"|(?:{qualifiers}):{_SYMBOL}"
        self._explicit = re.compile(rf"(?<![A-Z0-9_:$])(?:{notation})", flags=re.IGNORECASE | re.ASCII)

    @classmethod
    def from_capture(cls, raw: bytes, receipt: dict) -> IssuerDirectory:
        if not isinstance(receipt, dict) or receipt.get("source_url") != SEC_DIRECTORY_URL:
            raise ValueError("Expected a receipt for the SEC exchange directory")
        captured = parse_timestamp(receipt.get("captured_at_utc"))
        if captured is None:
            raise ValueError("Directory capture needs an aware timestamp")
        digest = hashlib.sha256(raw).hexdigest()
        if receipt.get("sha256") != digest or type(receipt.get("bytes")) is not int or receipt["bytes"] != len(raw):
            raise ValueError("Directory bytes do not match the capture receipt")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Directory payload must be an object")
        fields, data = payload.get("fields"), payload.get("data")
        required = {"cik", "name", "ticker", "exchange"}
        if (not isinstance(fields, list) or not all(isinstance(f, str) for f in fields)
                or len(set(fields)) != len(fields) or not required.issubset(fields)
                or not isinstance(data, list) or not data):
            raise ValueError("Unexpected SEC directory schema")
        positions = {key: fields.index(key) for key in required}
        rows = set()
        for index, record in enumerate(data):
            if not isinstance(record, list) or len(record) != len(fields):
                raise ValueError(f"Malformed directory row {index}")
            cik, name, ticker, exchange = (record[positions[key]] for key in ("cik", "name", "ticker", "exchange"))
            cik = _cik(cik)
            if (cik is None or not isinstance(name, str) or not _name_key(name)
                    or _symbol_key(ticker) is None
                    or (exchange is not None and (not isinstance(exchange, str) or not exchange.strip()))):
                raise ValueError(f"Invalid directory values in row {index}")
            rows.add(Listing(cik, name.strip(), ticker.upper(), _venue(exchange) if exchange else None))
        ordered = tuple(sorted(rows, key=lambda row: (row.cik, row.ticker, row.exchange or "", row.name)))
        return cls(ordered, {"source_url": SEC_DIRECTORY_URL, "captured_at_utc": _iso(captured),
                             "sha256": digest, "bytes": len(raw), "input_rows": len(data),
                             "distinct_rows": len(ordered), "distinct_issuers": len({r.cik for r in ordered}),
                             "capture_time_basis": "caller_declared"})

    def _result(self, rows, basis: str, *, weak: bool = False, explicit: bool = False) -> dict:
        rows = tuple(dict.fromkeys(rows))
        issuers = {row.cik for row in rows}
        if not rows:
            status = "unresolved"
        elif len(issuers) > 1:
            status = "ambiguous"
        elif weak:
            status = "name_candidate"
        else:
            status = "symbol_match" if explicit and len({(r.ticker, r.exchange) for r in rows}) == 1 else "issuer_match"
        cik = rows[0].cik if status in {"issuer_match", "symbol_match"} else None
        symbol = {"ticker": rows[0].ticker, "exchange": rows[0].exchange} if status == "symbol_match" else None
        return {"status": status, "match_basis": basis, "issuer_cik": cik, "symbol": symbol,
                "matched_rows": [asdict(row) for row in rows],
                "issuer_listings": [asdict(row) for row in self._issuers.get(cik, ())]}

    def resolve_symbol(self, symbol: str, exchange: str | None = None) -> dict:
        """Resolve an explicitly supplied symbol, preserving class/venue ambiguity."""
        rows = self._symbols.get(_symbol_key(symbol), ())
        if exchange is not None:
            rows = [row for row in rows if row.exchange == _venue(exchange)]
        return self._result(rows, "explicit_symbol_and_venue" if exchange is not None else "explicit_symbol",
                            explicit=True)

    def resolve_mention(self, mention: str) -> dict:
        """Resolve mention text, assuming the caller already verified the source span."""
        query = mention.strip()
        if re.fullmatch(r"CIK:[0-9]{1,10}", query, flags=re.IGNORECASE | re.ASCII):
            return self._result(self._issuers.get(_cik(query.split(":", 1)[1]), ()), "explicit_cik")
        if query.startswith("$") and query[1:2].isascii() and query[1:2].isalpha():
            return self.resolve_symbol(query[1:])
        qualified = re.fullmatch(r"([A-Za-z][A-Za-z0-9 ]{0,31}):([A-Za-z0-9.-]{1,32})", query)
        if qualified:
            return self.resolve_symbol(qualified[2], qualified[1])
        key = _name_key(query)
        exact = self._names.get(key, ())
        if exact and _short_name(key) != key:
            return self._result(exact, "normalized_directory_name")
        candidates = [*exact, *self._short_names.get(key, ())]
        if candidates:
            return self._result(candidates, "unqualified_or_short_name", weak=True)
        return self._result((), "explicit_symbol_required" if _symbol_key(query) in self._symbols else "no_directory_match")

    def explicit_mentions(self, text: str) -> list[dict]:
        """Find complete cashtags, exchange-qualified tickers and CIK notations."""
        return [{"start": match.start(), "end": match.end(), "text": match.group()}
                for match in self._explicit.finditer(text) if _complete_span(text, match.start(), match.end())]


def _complete_span(text: str, start: int, end: int) -> bool:
    # Do not accept the A in AAPL or the BRK part of BRK.B as independent tokens.
    def word(char):
        return char.isascii() and (char.isalnum() or char == "_")

    if start and word(text[start - 1]) and (word(text[start]) or text[start] == "$"):
        return False
    if start and text[start] == "$" and text[start - 1] == ":":
        return False
    if end < len(text) and word(text[end]) and word(text[end - 1]):
        return False
    if start >= 2 and text[start - 1] in ".-" and word(text[start - 2]) and word(text[start]):
        return False
    return not (end + 1 < len(text) and text[end] in ".-" and word(text[end + 1]))


def audit_issuer_mentions(directory: IssuerDirectory, snapshot: dict, mentions: list,
                          *, as_of, focus_symbol: str | None = None, scan_explicit: bool = False) -> dict:
    """Build an offline identity report from one news snapshot and its extractor spans."""
    cutoff = parse_timestamp(as_of)
    if cutoff is None:
        raise ValueError("Issuer evidence needs an aware decision cutoff")
    if not isinstance(mentions, list):
        raise ValueError("Mentions must be a list")
    if focus_symbol is not None and _symbol_key(focus_symbol) is None:
        raise ValueError("Focus must be an explicit ticker argument")
    if parse_timestamp(directory.receipt["captured_at_utc"]) > cutoff:
        reason = "directory_after_cutoff"
    elif not isinstance(snapshot, dict):
        reason = "invalid_snapshot"
    else:
        try:
            reason = _rejection(snapshot, cutoff)
        except (TypeError, ValueError, UnicodeError):
            reason = "invalid_snapshot"
    focus = directory.resolve_symbol(focus_symbol) if focus_symbol and reason is None else None
    scanned = directory.explicit_mentions(snapshot["snapshot_text"]) if scan_explicit and not reason else []
    inputs = [("provided", mention) for mention in mentions] + [("explicit_scan", mention) for mention in scanned]
    linked, seen = [], set()
    for index, (origin, mention) in enumerate(inputs):
        row = {"mention_index": index, "origin": origin}
        if reason:
            linked.append({**row, "status": "blocked", "reason": reason})
            continue
        try:
            start, end, quote = mention["start"], mention["end"], mention["text"]
            text = snapshot["snapshot_text"]
            span = anchor_char_span(text, start, end, quote)
            if not quote or len(quote) > 512 or quote != quote.strip() or not _complete_span(text, start, end):
                raise ValueError("Expected a complete mention token")
        except (KeyError, TypeError, ValueError, UnicodeError):
            linked.append({**row, "status": "invalid_span"})
            continue
        row.update(start_char=start, end_char=end, quote=quote, **span)
        if (start, end) in seen:
            linked.append({**row, "status": "duplicate_span"})
            continue
        seen.add((start, end))
        link = directory.resolve_mention(quote)
        relation = "not_requested" if focus is None else "unresolved"
        symbol_relation = None
        if focus and focus["issuer_cik"] and link["issuer_cik"]:
            relation = "same_issuer" if focus["issuer_cik"] == link["issuer_cik"] else "different_issuer"
            if relation == "same_issuer" and focus["symbol"] and link["symbol"]:
                symbol_relation = "same_symbol" if focus["symbol"] == link["symbol"] else "other_symbol_same_issuer"
        linked.append({**row, **link, "focus_relation": relation, "focus_symbol_relation": symbol_relation})
    source = None
    if isinstance(snapshot, dict):
        source = {key: snapshot.get(key) for key in ("source_id", "source_sha256", "source_url",
                                                    "published_at_utc", "captured_at_utc")}
    return {"schema_version": 1, "status": "blocked" if reason else "evaluated", "reason": reason,
            "as_of_utc": _iso(cutoff), "directory": directory.receipt.copy(), "source": source,
            "focus_symbol": focus_symbol, "focus": focus, "mentions": linked,
            "provided_mentions": len(mentions), "explicit_scan_mentions": len(scanned),
            "mention_status_counts": dict(Counter(row["status"] for row in linked)),
            "scope": {"event_role_evaluated": False, "sentiment_evaluated": False,
                      "current_tradability_verified": False, "used_for_trading": False}}
