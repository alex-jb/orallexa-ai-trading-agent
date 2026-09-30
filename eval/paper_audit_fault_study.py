"""Reproducible, offline fault injection for signed PAPER audit snapshots.

Only generated synthetic files and disposable Ed25519 keys are used. This
study does not import the paper broker, contact Alpaca, call an LLM, trade, or
estimate returns. Run with ``python -m eval.paper_audit_fault_study``.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import random
import shutil
import tempfile
from pathlib import Path
from time import perf_counter_ns

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot.paper_audit_export as audit

SCRIPT_VERSION = "1.0"
DEFAULT_SEED = 20260930
FIXTURES = Path(__file__).with_name("fixtures")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def synthetic_inputs(seed: int) -> tuple[bytes, bytes]:
    """Create deterministic fictional data; no broker observations are used."""
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer between 0 and 2**32-1")
    rng = random.Random(seed)
    state = _json_bytes({"config": {"qty": 1}, "synthetic_fixture": True,
                         "tickers": {}})
    rows = []
    for number, signal in enumerate(("HOLD", "BUY", "HOLD", "SELL")):
        rows.append({
            "event_id": hashlib.sha256(f"orallexa-fault-study-v1:{seed}:{number}".encode()).hexdigest()[:32],
            "timestamp": f"2026-09-{20 + number:02d}T14:00:00+00:00",
            "ticker": "TEST", "signal": signal, "order_type": "market" if signal != "HOLD" else None,
            "qty": 1 if signal != "HOLD" else 0,
            "order_status": "filled" if signal != "HOLD" else None,
            "filled_qty": 1 if signal != "HOLD" else 0,
            "fill_price": round(100 + rng.uniform(-2, 2), 4) if signal != "HOLD" else None,
            "fees_usd": 0.0, "realized_pnl_total_usd": 0.0,
            "drawdown_pct": 0.0, "synthetic_fixture": True,
        })
    ledger = b"".join(_json_bytes(row) for row in rows)
    return state, ledger


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _keypair(directory: Path, label: str) -> tuple[Path, Path]:
    # Fresh and never retained: no test private key is included in Git or JSON.
    key = Ed25519PrivateKey.generate()
    private_path = directory / f"{label}-private.pem"
    public_path = directory / f"{label}-public.pem"
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8,
                         serialization.NoEncryption()))
    private_path.chmod(0o600)
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return private_path, public_path


def _mutate(case: str, bundle: Path) -> None:
    ledger = bundle / "ledger.jsonl"
    if case == "ledger_complete_row_truncation":
        ledger.write_bytes(b"".join(ledger.read_bytes().splitlines(keepends=True)[:-1]))
    elif case == "ledger_row_reorder":
        rows = ledger.read_bytes().splitlines(keepends=True)
        rows[1], rows[2] = rows[2], rows[1]
        ledger.write_bytes(b"".join(rows))
    elif case == "ledger_valid_row_modify":
        rows = ledger.read_bytes().splitlines(keepends=True)
        row = json.loads(rows[1])
        row["signal"] = "SELL"  # Still valid JSON and a valid signal.
        rows[1] = _json_bytes(row)
        ledger.write_bytes(b"".join(rows))
    elif case == "state_valid_json_modify":
        state = bundle / "state.json"
        value = json.loads(state.read_bytes())
        value["config"]["qty"] = 2
        state.write_bytes(_json_bytes(value))
    elif case == "manifest_canonical_modify":
        path = bundle / "manifest.json"
        value = json.loads(path.read_bytes())
        value["ledger_event_count"] += 1
        path.write_bytes(_json_bytes(value))
    elif case == "signature_valid_base64_modify":
        path = bundle / "signature.ed25519"
        value = path.read_bytes()
        path.write_bytes((b"A" if value[:1] != b"A" else b"B") + value[1:])
    elif case == "missing_bundle_member":
        (bundle / "state.json").unlink()
    elif case == "extra_bundle_member":
        (bundle / "unexpected.txt").write_bytes(b"synthetic-extra\n")
    elif case == "malformed_tail_after_signing":
        ledger.write_bytes(ledger.read_bytes() + b'{"event_id":')
    else:
        raise ValueError(f"Unrecognized injection case: {case}")


# Fixed before observing outcomes; each case starts from a fresh baseline copy.
VERIFY_CASES = (
    "intact_signed_bundle",
    "ledger_complete_row_truncation",
    "ledger_row_reorder",
    "ledger_valid_row_modify",
    "state_valid_json_modify",
    "manifest_canonical_modify",
    "signature_valid_base64_modify",
    "missing_bundle_member",
    "extra_bundle_member",
    "malformed_tail_after_signing",
    "wrong_independent_trusted_key",
)


def _observe(case: str, phase: str, expected_rejected: bool, action) -> dict:
    start = perf_counter_ns()
    rejected = False
    unexpected_error = None
    try:
        action()
    except audit.AuditError:
        rejected = True
    except Exception as exc:  # An arbitrary crash does not count as detection.
        unexpected_error = type(exc).__name__
    elapsed_ms = round((perf_counter_ns() - start) / 1_000_000, 3)
    return {"case": case, "phase": phase, "expected_rejected": expected_rejected,
            "rejected": rejected, "matched_expected": unexpected_error is None and rejected == expected_rejected,
            "unexpected_error_type": unexpected_error, "elapsed_ms": elapsed_ms}


def run_study(seed: int = DEFAULT_SEED) -> dict:
    state_bytes, ledger_bytes = synthetic_inputs(seed)
    if seed == DEFAULT_SEED:
        # Default fixture data is versioned in Git; catch generator drift.
        for name, data in (("paper_audit_fault_state_v1.json", state_bytes),
                           ("paper_audit_fault_ledger_v1.jsonl", ledger_bytes)):
            if (FIXTURES / name).read_bytes() != data:
                raise ValueError(f"The committed synthetic fixture has drifted: {name}")
    with tempfile.TemporaryDirectory(prefix="orallexa-paper-audit-fault-") as raw_temp:
        temp = Path(raw_temp)
        state, ledger = temp / "source-state.json", temp / "source-ledger.jsonl"
        state.write_bytes(state_bytes)
        ledger.write_bytes(ledger_bytes)
        private, public = _keypair(temp, "fixture")
        _, wrong_public = _keypair(temp, "untrusted")
        baseline = temp / "baseline"
        audit.export_snapshot(state, ledger, baseline, private)
        results = []
        for case in VERIFY_CASES:
            bundle = temp / case
            shutil.copytree(baseline, bundle)
            if case not in ("intact_signed_bundle", "wrong_independent_trusted_key"):
                _mutate(case, bundle)
            key = wrong_public if case == "wrong_independent_trusted_key" else public
            results.append(_observe(case, "verify", case != "intact_signed_bundle",
                                    lambda b=bundle, k=key: audit.verify_snapshot(b, k)))

        # Separate input-stage control: export must refuse a torn JSONL tail.
        malformed_source = temp / "malformed-source.jsonl"
        malformed_source.write_bytes(ledger_bytes + b'{"event_id":')
        results.append(_observe("malformed_tail_before_signing", "export", True,
                                lambda: audit.export_snapshot(state, malformed_source,
                                                              temp / "bad-tail-export", private)))

        # Known boundary: a valid whole-row deletion *before the first signature*
        # cannot be recognized without an independently trusted earlier anchor.
        shortened = temp / "shortened-before-signing.jsonl"
        shortened_bytes = b"".join(ledger_bytes.splitlines(keepends=True)[:-1])
        shortened.write_bytes(shortened_bytes)
        def sign_and_verify_shortened() -> None:
            signed = temp / "shortened-signed"
            audit.export_snapshot(state, shortened, signed, private)
            result = audit.verify_snapshot(signed, public)
            if result["ledger_event_count"] != 3:
                raise ValueError("shortened input did not have three rows")
        results.append(_observe("valid_history_loss_before_first_signature", "export_then_verify",
                                False, sign_and_verify_shortened))

    return {
        "study": "orallexa-offline-paper-audit-fault-injection",
        "script_version": SCRIPT_VERSION,
        "audit_schema": audit.SCHEMA,
        "audit_module_sha256": _sha(Path(audit.__file__).read_bytes()),
        "cryptography_version": importlib.metadata.version("cryptography"),
        "fixture": {"synthetic": True, "seed": seed, "row_count": 4,
                    "state_sha256": _sha(state_bytes), "ledger_sha256": _sha(ledger_bytes),
                    "pre_signature_shortened_ledger_sha256": _sha(shortened_bytes)},
        "cost_assumptions": {"broker_calls": 0, "llm_calls": 0, "broker_api_cost_usd": 0.0,
                             "llm_api_cost_usd": 0.0, "assumed_paper_commission_usd": 0.0,
                             "slippage_modeled": False},
        "timing_note": "Local perf_counter case durations in ms; descriptive, not a speed benchmark",
        "results": results,
        "passed": all(result["matched_expected"] for result in results),
        "interpretation": "The pre-signature history-loss control is expected to verify; no preexisting completeness proof",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, help="Optional JSON report; no keys or bundle bytes are retained")
    args = parser.parse_args()
    report = run_study(args.seed)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if not report["passed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
