"""Produce an offline issuer evidence report from captured news and SEC bytes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from engine.issuer_identity import IssuerDirectory, audit_issuer_mentions
from engine.news_research import _iso, parse_timestamp


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON records with snapshots and extractor spans")
    parser.add_argument("--directory", required=True, type=Path, help="Captured company_tickers_exchange.json bytes")
    parser.add_argument("--receipt", required=True, type=Path, help="Directory source URL, capture time, size and SHA-256")
    parser.add_argument("--as-of", required=True, help="Aware decision cutoff, e.g. 2026-11-11T22:50:00Z")
    parser.add_argument("--focus-symbol", help="Optional default ticker; individual records may specify a focus")
    parser.add_argument("--scan-explicit", action="store_true", help="Also detect explicit cashtags, venue-qualified symbols and CIKs")
    parser.add_argument("--output", required=True, type=Path, help="New JSON output path")
    args = parser.parse_args(argv)
    try:
        cutoff = parse_timestamp(args.as_of)
        if cutoff is None:
            raise ValueError("Expected an aware decision cutoff")
        directory = IssuerDirectory.from_capture(args.directory.read_bytes(), json.loads(args.receipt.read_bytes()))
        raw_input = args.input.read_bytes()
        payload = json.loads(raw_input)
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise ValueError("Input must contain a records list")
        reports, seen, counts = [], set(), Counter()
        for row in records:
            identifier = row.get("id") if isinstance(row, dict) else None
            if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
                raise ValueError("Input records need unique non-empty IDs")
            seen.add(identifier)
            report = audit_issuer_mentions(directory, row.get("snapshot"), row.get("mentions", []),
                                          as_of=cutoff, focus_symbol=row.get("focus_symbol", args.focus_symbol),
                                          scan_explicit=args.scan_explicit)
            counts.update(report["mention_status_counts"])
            reports.append({"id": identifier, **report})
        result = {"schema_version": 1, "as_of_utc": _iso(cutoff),
                  "input_sha256": hashlib.sha256(raw_input).hexdigest(),
                  "directory": directory.receipt.copy(), "input_records": len(records),
                  "record_status_counts": dict(Counter(row["status"] for row in reports)),
                  "mention_status_counts": dict(counts), "records": reports}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        print(json.dumps({key: result[key] for key in ("input_records", "record_status_counts", "mention_status_counts")}))
        return 0
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
