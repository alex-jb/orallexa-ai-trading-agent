"""Offline, read-only signed snapshots of the fixed-rule PAPER pilot ledger.

This does not contact Alpaca, use an LLM, or establish that historic records are
complete or correct. Stop the pilot writer before exporting a snapshot.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "orallexa-paper-audit-snapshot-v1"
DOMAIN = b"Orallexa PAPER audit snapshot v1\n"
BOUND_SCHEMA = "orallexa-paper-audit-snapshot-v2"
BOUND_DOMAIN = b"Orallexa PAPER audit snapshot v2\n"
FILES = frozenset({"state.json", "ledger.jsonl", "manifest.json", "signature.ed25519"})
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_META_BYTES = 16 * 1024
EVENT_ID = re.compile(r"[0-9a-f]{32}\Z")
TICKER = re.compile(r"[A-Z]{1,5}\Z")
INPUT_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REPLAY_RULE = "sma20_50_long_flat_v1"
SOURCE_KINDS = frozenset({"alpaca_iex_daily_bars", "csv_date_close",
                          "caller_supplied_completed_closes"})


class AuditError(ValueError):
    """A snapshot or a trust input failed validation."""


def _path(path: Path, *, kind: str) -> Path:
    """Reject symlinks in every existing component, including the final path."""
    absolute = Path(os.path.abspath(path))  # resolve() would hide a symlink.
    for component in reversed((absolute, *absolute.parents)):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            if component != absolute:
                raise AuditError("A parent directory is missing") from None
            if kind == "new":
                return absolute
            raise AuditError("A required path is missing") from None
        if stat.S_ISLNK(mode):
            raise AuditError("Symlink paths are not accepted")
        if component != absolute and not stat.S_ISDIR(mode):
            raise AuditError("A path parent is not a directory")
        if component == absolute:
            if kind == "new":
                raise AuditError("The output bundle already exists")
            if kind == "file" and not stat.S_ISREG(mode):
                raise AuditError("Expected a regular file")
            if kind == "directory" and not stat.S_ISDIR(mode):
                raise AuditError("Expected a directory")
    return absolute


def _read(path: Path, *, limit: int) -> bytes:
    path = _path(path, kind="file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise AuditError("Expected a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise AuditError("File exceeds the snapshot size limit")
        return data
    finally:
        os.close(descriptor)


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError("Duplicate JSON key")
        result[key] = value
    return result


def _strict_json(data: bytes) -> object:
    def invalid_constant(value: str) -> None:
        raise AuditError("Non-finite JSON number")

    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs_unique,
                            parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, AuditError):
            raise
        raise AuditError("Invalid UTF-8 JSON") from exc

    def finite(value: object) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise AuditError("Non-finite JSON number")
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    try:
        finite(parsed)
    except RecursionError as exc:
        raise AuditError("JSON nesting is too deep") from exc
    return parsed


def _validate_state(data: bytes) -> tuple[set[str], str | None, int | None, str | None]:
    state = _strict_json(data)
    if not isinstance(state, dict) or not isinstance(state.get("tickers"), dict):
        raise AuditError("Invalid paper state schema")
    if any(not isinstance(ticker, str) or not TICKER.fullmatch(ticker)
           or not isinstance(item, dict) for ticker, item in state["tickers"].items()):
        raise AuditError("Invalid ticker checkpoint in paper state")
    config = state.get("config")
    qty = config.get("qty") if isinstance(config, dict) else None
    if type(qty) is not int or not 1 <= qty <= 100:
        raise AuditError("State has no valid fixed share quantity")
    pilot_id = config.get("pilot_id")
    if "pilot_id" in config and (not isinstance(pilot_id, str) or not EVENT_ID.fullmatch(pilot_id)):
        raise AuditError("State has an invalid pilot identity")
    count = state.get("ledger_event_count")
    digest = state.get("ledger_sha256")
    if pilot_id and (type(count) is not int or count < 0
                     or not isinstance(digest, str) or not INPUT_SHA256.fullmatch(digest)):
        raise AuditError("Bound state has no valid ledger checkpoint")
    if state.get("outbox") is not None:
        raise AuditError("Unrecovered audit outbox; run recovery before export")
    return set(state["tickers"]), pilot_id, count, digest


def _verify_decision_input(row: dict, number: int) -> None:
    """Replay derived closes; a valid hash alone cannot prove source truth."""
    if row.get("event_type") not in ("decision", "order_intent"):
        raise AuditError(f"Ledger row {number} puts decision inputs on a non-decision event")
    closes = row["input_closes"]
    if (not isinstance(closes, list) or len(closes) != 50
            or any(type(price) is not float or not math.isfinite(price) or price <= 0
                   for price in closes)):
        raise AuditError(f"Ledger row {number} has invalid transformed closes")
    if row.get("rule_version") != REPLAY_RULE:
        raise AuditError(f"Ledger row {number} has an unsupported replay rule")
    if not isinstance(row.get("source_kind"), str) or row["source_kind"] not in SOURCE_KINDS:
        raise AuditError(f"Ledger row {number} has an invalid source label")
    session = row.get("source_as_of_session")
    if session is not None:
        try:
            if not isinstance(session, str) or date.fromisoformat(session).isoformat() != session:
                raise ValueError("Noncanonical session date")
        except ValueError as exc:
            raise AuditError(f"Ledger row {number} has an invalid source session") from exc
    digest = hashlib.sha256(json.dumps(
        closes, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    recorded_digest = row.get("input_closes_sha256")
    if (not isinstance(recorded_digest, str) or not INPUT_SHA256.fullmatch(recorded_digest)
            or recorded_digest != digest):
        raise AuditError(f"Ledger row {number} has an invalid decision input hash")
    sma20, sma50 = sum(closes[-20:]) / 20, sum(closes) / 50
    if (any(type(row.get(field)) is not float
            for field in ("signal_price", "sma20", "sma50"))
            or row["signal_price"] != closes[-1] or row["sma20"] != sma20
            or row.get("sma50") != sma50
            or row.get("signal") != ("BUY" if sma20 > sma50 else "SELL")):
        raise AuditError(f"Ledger row {number} does not replay the fixed rule")


def _validate_ledger(data: bytes) -> tuple[int, str, set[str], dict, set[str], bool]:
    if not data or not data.endswith(b"\n") or b"\r" in data:
        raise AuditError("Ledger must contain JSONL rows with final LF")
    seen: set[str] = set()
    tickers: set[str] = set()
    pilot_ids: set[str] = set()
    unbound_row = False
    last = ""
    replay_eligible = replay_verified = 0
    for number, line in enumerate(data.split(b"\n")[:-1], 1):
        if not line:
            raise AuditError(f"Blank ledger row {number}")
        row = _strict_json(line)
        if not isinstance(row, dict):
            raise AuditError(f"Ledger row {number} is not an object")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
            raise AuditError(f"Ledger row {number} has an invalid event ID")
        if event_id in seen:
            raise AuditError("Duplicate ledger event ID")
        seen.add(event_id)
        last = event_id
        if "pilot_id" in row:
            pilot_id = row["pilot_id"]
            if not isinstance(pilot_id, str) or not EVENT_ID.fullmatch(pilot_id):
                raise AuditError(f"Ledger row {number} has an invalid pilot identity")
            pilot_ids.add(pilot_id)
        else:
            unbound_row = True
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, str):
            raise AuditError(f"Ledger row {number} has no timestamp")
        try:
            observed = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise AuditError(f"Ledger row {number} has an invalid timestamp") from exc
        if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
            raise AuditError(f"Ledger row {number} needs a UTC timestamp")
        if not isinstance(row.get("ticker"), str) or not TICKER.fullmatch(row["ticker"]):
            raise AuditError(f"Ledger row {number} has an invalid ticker")
        tickers.add(row["ticker"])
        if row.get("signal") not in ("BUY", "SELL", "HOLD"):
            raise AuditError(f"Ledger row {number} has an invalid signal")
        required = ("order_type", "qty", "order_status", "filled_qty", "fill_price",
                    "fees_usd", "realized_pnl_total_usd", "drawdown_pct")
        if any(field not in row for field in required):
            raise AuditError(f"Ledger row {number} is missing audit fields")
        if row["order_type"] not in (None, "market"):
            raise AuditError(f"Ledger row {number} has an invalid order type")
        if row["order_status"] is not None and not isinstance(row["order_status"], str):
            raise AuditError(f"Ledger row {number} has an invalid order status")
        for field in ("qty", "filled_qty", "fees_usd", "realized_pnl_total_usd"):
            value = row[field]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (value < 0 and field != "realized_pnl_total_usd")):
                raise AuditError(f"Ledger row {number} has an invalid {field}")
        for field in ("fill_price", "drawdown_pct"):
            value = row[field]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise AuditError(f"Ledger row {number} has an invalid {field}")
        # A pre-replay ledger may contain order intents with only a digest and
        # old decisions with no explicit event type. Count them as unverified.
        eligible = row.get("event_type") in ("decision", "order_intent") or (
            row.get("event_type") is None and row.get("signal_price") is not None
            and row.get("sma20") is not None and row.get("sma50") is not None)
        if "input_closes" in row:
            _verify_decision_input(row, number)
            replay_verified += 1
        if eligible:
            replay_eligible += 1
    return len(seen), last, tickers, {
        "eligible_rows": replay_eligible, "verified_rows": replay_verified,
        "unverified_rows": replay_eligible - replay_verified,
    }, pilot_ids, unbound_row


def _require_matching_tickers(state_tickers: set[str], ledger_tickers: set[str]) -> None:
    # A feed failure can log a ticker before the first valid-bar decision has
    # created its checkpoint. Every checkpointed ticker must still have a row.
    if not state_tickers.issubset(ledger_tickers):
        raise AuditError("State ticker is absent from the ledger")


def _require_matching_pilot(state_id: str | None, ledger_ids: set[str], unbound_row: bool) -> None:
    if state_id is None:
        if ledger_ids:
            raise AuditError("Unbound state cannot be paired with a bound ledger")
    elif unbound_row or ledger_ids != {state_id}:
        raise AuditError("State and every ledger row must share the same pilot identity")


def _canonical(manifest: dict) -> bytes:
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(encoding=serialization.Encoding.Raw,
                                  format=serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def _private_key(path: Path) -> Ed25519PrivateKey:
    path = _path(path, kind="file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise AuditError("Signing key must have owner-only permissions")
    try:
        key = serialization.load_pem_private_key(_read(path, limit=MAX_META_BYTES), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise AuditError("Invalid unencrypted Ed25519 private key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AuditError("Signing key is not Ed25519")
    return key


def _public_key(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(_read(path, limit=MAX_META_BYTES))
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise AuditError("Invalid trusted Ed25519 public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise AuditError("Trusted key is not Ed25519")
    return key


def _write(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def export_snapshot(state_path: Path, ledger_path: Path, bundle_path: Path,
                    signing_key_path: Path) -> dict:
    """Write a new private bundle. Does not mutate the input files."""
    state_path = _path(state_path, kind="file")
    ledger_path = _path(ledger_path, kind="file")
    bundle_path = _path(bundle_path, kind="new")
    key = _private_key(signing_key_path)
    if len({state_path, ledger_path, Path(os.path.abspath(signing_key_path))}) != 3:
        raise AuditError("Signing key and source files must be separate")
    state = _read(state_path, limit=MAX_SOURCE_BYTES)
    ledger = _read(ledger_path, limit=MAX_SOURCE_BYTES)
    state_tickers, pilot_id, checkpoint_count, checkpoint_hash = _validate_state(state)
    count, last, ledger_tickers, replay, ledger_ids, unbound_row = _validate_ledger(ledger)
    _require_matching_tickers(state_tickers, ledger_tickers)
    _require_matching_pilot(pilot_id, ledger_ids, unbound_row)
    if pilot_id and (checkpoint_count != count or checkpoint_hash != hashlib.sha256(ledger).hexdigest()):
        raise AuditError("Bound ledger differs from its saved checkpoint")
    # Detect ordinary concurrent writes. This is not a substitute for stopping
    # the writer: the state and ledger have no shared atomic snapshot primitive.
    if state != _read(state_path, limit=MAX_SOURCE_BYTES) or ledger != _read(ledger_path, limit=MAX_SOURCE_BYTES):
        raise AuditError("Paper data changed during export; stop the writer and retry")
    payload = {"state.json": state, "ledger.jsonl": ledger}
    manifest = {
        "schema": BOUND_SCHEMA if pilot_id else SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "signer_public_key_sha256": _fingerprint(key.public_key()),
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
                  for name, data in payload.items()},
        "ledger_event_count": count,
        "ledger_last_event_id": last,
        "evidence_scope": "local_paper_state_and_ledger_bytes_only",
    }
    if pilot_id:
        manifest["pilot_id"] = pilot_id
    encoded = _canonical(manifest)
    signature = base64.b64encode(key.sign((BOUND_DOMAIN if pilot_id else DOMAIN) + encoded)) + b"\n"
    bundle_path.mkdir(mode=0o700)
    for name, data in payload.items():
        _write(bundle_path / name, data)
    _write(bundle_path / "manifest.json", encoded)
    _write(bundle_path / "signature.ed25519", signature)
    _fsync_directory(bundle_path)
    _fsync_directory(bundle_path.parent)
    return {"bundle": str(bundle_path), "ledger_event_count": count,
            "signer_public_key_sha256": manifest["signer_public_key_sha256"],
            "decision_replay_coverage": replay, "pilot_id": pilot_id,
            "pilot_identity_status": "bound" if pilot_id else "identity_unverified"}


def verify_snapshot(bundle_path: Path, trusted_public_key_path: Path) -> dict:
    """Verify against a key supplied independently of the bundle."""
    bundle_path = _path(bundle_path, kind="directory")
    trusted_public_key_path = _path(trusted_public_key_path, kind="file")
    if bundle_path == trusted_public_key_path or bundle_path in trusted_public_key_path.parents:
        raise AuditError("Trusted public key must be outside the bundle")
    if {child.name for child in bundle_path.iterdir()} != FILES:
        raise AuditError("Bundle files are missing or unexpected")
    manifest_bytes = _read(bundle_path / "manifest.json", limit=MAX_META_BYTES)
    manifest = _strict_json(manifest_bytes)
    if not isinstance(manifest, dict) or manifest_bytes != _canonical(manifest):
        raise AuditError("Manifest is not canonical JSON")
    schema = manifest.get("schema")
    if schema not in (SCHEMA, BOUND_SCHEMA):
        raise AuditError("Unsupported manifest version or scope")
    expected_keys = {"schema", "created_at_utc", "signer_public_key_sha256", "files",
                     "ledger_event_count", "ledger_last_event_id", "evidence_scope"}
    if schema == BOUND_SCHEMA:
        expected_keys.add("pilot_id")
    if set(manifest) != expected_keys:
        raise AuditError("Unknown manifest schema")
    if manifest["evidence_scope"] != "local_paper_state_and_ledger_bytes_only":
        raise AuditError("Unsupported manifest version or scope")
    try:
        created = datetime.fromisoformat(manifest["created_at_utc"])
    except (ValueError, TypeError) as exc:
        raise AuditError("Invalid snapshot creation time") from exc
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        raise AuditError("Snapshot creation time must be UTC")
    key = _public_key(trusted_public_key_path)
    fingerprint = _fingerprint(key)
    if manifest["signer_public_key_sha256"] != fingerprint:
        raise AuditError("Trusted public key fingerprint does not match")
    signature_bytes = _read(bundle_path / "signature.ed25519", limit=MAX_META_BYTES)
    if not signature_bytes.endswith(b"\n") or signature_bytes.count(b"\n") != 1:
        raise AuditError("Invalid signature encoding")
    try:
        signature = base64.b64decode(signature_bytes[:-1], validate=True)
        if len(signature) != 64 or base64.b64encode(signature) + b"\n" != signature_bytes:
            raise AuditError("Invalid signature encoding")
        key.verify(signature, (BOUND_DOMAIN if schema == BOUND_SCHEMA else DOMAIN) + manifest_bytes)
    except (ValueError, AuditError) as exc:
        raise AuditError("Invalid signature encoding") from exc
    except InvalidSignature as exc:
        raise AuditError("Snapshot signature does not verify") from exc
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != {"state.json", "ledger.jsonl"}:
        raise AuditError("Manifest does not name the two required files")
    payload = {}
    for name in ("state.json", "ledger.jsonl"):
        metadata = files[name]
        if not isinstance(metadata, dict) or set(metadata) != {"sha256", "size_bytes"}:
            raise AuditError("Invalid file metadata")
        raw = _read(bundle_path / name, limit=MAX_SOURCE_BYTES)
        if metadata["size_bytes"] != len(raw) or metadata["sha256"] != hashlib.sha256(raw).hexdigest():
            raise AuditError("Snapshot bytes do not match the signed manifest")
        payload[name] = raw
    state_tickers, pilot_id, checkpoint_count, checkpoint_hash = _validate_state(payload["state.json"])
    count, last, ledger_tickers, replay, ledger_ids, unbound_row = _validate_ledger(payload["ledger.jsonl"])
    _require_matching_tickers(state_tickers, ledger_tickers)
    _require_matching_pilot(pilot_id, ledger_ids, unbound_row)
    if pilot_id and (checkpoint_count != count
                     or checkpoint_hash != hashlib.sha256(payload["ledger.jsonl"]).hexdigest()):
        raise AuditError("Bound ledger differs from its saved checkpoint")
    if schema == BOUND_SCHEMA:
        if not pilot_id or manifest["pilot_id"] != pilot_id:
            raise AuditError("Signed pilot identity does not match snapshot inputs")
    elif pilot_id:
        raise AuditError("Legacy manifest cannot claim a bound pilot")
    if manifest["ledger_event_count"] != count or manifest["ledger_last_event_id"] != last:
        raise AuditError("Ledger metadata does not match the signed manifest")
    # Catch an ordinary replacement after the first read. Verification still
    # cannot promise a hostile, concurrently writable directory stays fixed.
    if {child.name for child in bundle_path.iterdir()} != FILES:
        raise AuditError("Bundle changed during verification")
    for name, original in (("manifest.json", manifest_bytes),
                           ("signature.ed25519", signature_bytes),
                           *payload.items()):
        limit = MAX_META_BYTES if name in ("manifest.json", "signature.ed25519") else MAX_SOURCE_BYTES
        if _read(bundle_path / name, limit=limit) != original:
            raise AuditError("Bundle changed during verification")
    return {"bundle": str(bundle_path), "ledger_event_count": count,
            "signer_public_key_sha256": fingerprint, "verified": True,
            "evidence_scope": manifest["evidence_scope"],
            "created_at_utc": manifest["created_at_utc"],
            "ledger_sha256": manifest["files"]["ledger.jsonl"]["sha256"],
            "decision_replay_coverage": replay, "pilot_id": pilot_id,
            "pilot_identity_status": "bound" if pilot_id else "identity_unverified"}


def verify_continuity(previous_bundle_path: Path, bundle_path: Path,
                      trusted_public_key_path: Path) -> dict:
    """Check that a newer signed ledger strictly extends a separately retained one.

    Both bundles must verify with the same independently supplied public key.
    This can detect history loss after the earlier snapshot, but cannot prove
    anything about rows missing before that first trusted snapshot.
    """
    previous_bundle_path = _path(previous_bundle_path, kind="directory")
    bundle_path = _path(bundle_path, kind="directory")
    if previous_bundle_path == bundle_path:
        raise AuditError("Previous and current bundles must be different")
    previous = verify_snapshot(previous_bundle_path, trusted_public_key_path)
    current = verify_snapshot(bundle_path, trusted_public_key_path)
    if previous["pilot_id"] != current["pilot_id"]:
        raise AuditError("Snapshots have different pilot identities")
    if datetime.fromisoformat(current["created_at_utc"]) <= datetime.fromisoformat(previous["created_at_utc"]):
        raise AuditError("Current snapshot is not later than the previous snapshot")
    if current["ledger_event_count"] <= previous["ledger_event_count"]:
        raise AuditError("Current ledger has no new events")
    prior_bytes = _read(previous_bundle_path / "ledger.jsonl", limit=MAX_SOURCE_BYTES)
    current_bytes = _read(bundle_path / "ledger.jsonl", limit=MAX_SOURCE_BYTES)
    if (hashlib.sha256(prior_bytes).hexdigest() != previous["ledger_sha256"]
            or hashlib.sha256(current_bytes).hexdigest() != current["ledger_sha256"]):
        raise AuditError("Snapshot ledger changed after verification")
    if not current_bytes.startswith(prior_bytes):
        raise AuditError("Current ledger does not preserve the previous signed history")
    return {"verified": True, "new_events": current["ledger_event_count"] - previous["ledger_event_count"],
            "previous_ledger_sha256": previous["ledger_sha256"],
            "current_ledger_sha256": current["ledger_sha256"],
            "evidence_scope": "signed_local_ledger_append_only_continuity",
            "pilot_id": current["pilot_id"],
            "pilot_identity_status": current["pilot_identity_status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export = subparsers.add_parser("export", help="Sign a stopped pilot's local state and ledger")
    export.add_argument("--state", type=Path, default=ROOT / "logs/paper_harness_state.json")
    export.add_argument("--ledger", type=Path, default=ROOT / "logs/paper_harness.jsonl")
    export.add_argument("--signing-key", type=Path, required=True, help="Existing private Ed25519 PEM")
    export.add_argument("--out", type=Path, help="New bundle directory, defaults to logs/")
    verify = subparsers.add_parser("verify", help="Verify a bundle with an independent trusted key")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--trusted-public-key", type=Path, required=True)
    continuity = subparsers.add_parser("verify-continuity", help="Check a later bundle extends a retained trusted bundle")
    continuity.add_argument("--previous-bundle", type=Path, required=True)
    continuity.add_argument("--bundle", type=Path, required=True)
    continuity.add_argument("--trusted-public-key", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            out = args.out or ROOT / "logs" / f"paper-audit-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
            if args.out is None:
                _path(out.parent.parent, kind="directory")
                out.parent.mkdir(mode=0o700, exist_ok=True)
            result = export_snapshot(args.state, args.ledger, out, args.signing_key)
        elif args.command == "verify":
            result = verify_snapshot(args.bundle, args.trusted_public_key)
        else:
            result = verify_continuity(args.previous_bundle, args.bundle, args.trusted_public_key)
    except (AuditError, OSError) as exc:
        parser.exit(2, f"Audit {args.command} refused ({type(exc).__name__}); inspect local inputs.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
