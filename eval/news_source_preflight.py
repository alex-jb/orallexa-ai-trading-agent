"""Check frozen local news inputs before human labels or provider outputs exist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.news_shadow_score import InvalidCohort, preflight_sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-bundle", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Write only after every source passes validation")
    args = parser.parse_args(argv)
    try:
        report = preflight_sources(args.manifest, args.source_bundle)
    except InvalidCohort as exc:
        parser.exit(2, f"invalid source bundle: {exc}\n")
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
