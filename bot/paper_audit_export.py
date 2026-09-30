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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "orallexa-paper-audit-snapshot-v1"
DOMAIN = b"Orallexa PAPER audit snapshot v1\n"
FILES = frozenset({"state.json", "ledger.jsonl", "manifest.json", "signature.ed25519"})
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_META_BYTES = 16 * 1024
EVENT_ID = re.compile(r"[0-9a-f]{32}\Z")
TICKER = re.compile(r"[A-Z]{1,5}\Z")


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


def _validate_state(data: bytes) -> None:
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
    if state.get("outbox") is not None:
        raise AuditError("Unrecovered audit outbox; run recovery before export")


def _validate_ledger(data: bytes) -> tuple[int, str]:
    if not data or not data.endswith(b"\n") or b"\r" in data:
        raise AuditError("Ledger must contain JSONL rows with final LF")
    seen: set[str] = set()
    last = ""
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
    return len(seen), last


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
    _validate_state(state)
    count, last = _validate_ledger(ledger)
    # Detect ordinary concurrent writes. This is not a substitute for stopping
    # the writer: the state and ledger have no shared atomic snapshot primitive.
    if state != _read(state_path, limit=MAX_SOURCE_BYTES) or ledger != _read(ledger_path, limit=MAX_SOURCE_BYTES):
        raise AuditError("Paper data changed during export; stop the writer and retry")
    payload = {"state.json": state, "ledger.jsonl": ledger}
    manifest = {
        "schema": SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "signer_public_key_sha256": _fingerprint(key.public_key()),
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
                  for name, data in payload.items()},
        "ledger_event_count": count,
        "ledger_last_event_id": last,
        "evidence_scope": "local_paper_state_and_ledger_bytes_only",
    }
    encoded = _canonical(manifest)
    signature = base64.b64encode(key.sign(DOMAIN + encoded)) + b"\n"
    bundle_path.mkdir(mode=0o700)
    for name, data in payload.items():
        _write(bundle_path / name, data)
    _write(bundle_path / "manifest.json", encoded)
    _write(bundle_path / "signature.ed25519", signature)
    return {"bundle": str(bundle_path), "ledger_event_count": count,
            "signer_public_key_sha256": manifest["signer_public_key_sha256"]}


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
    if set(manifest) != {"schema", "created_at_utc", "signer_public_key_sha256", "files",
                         "ledger_event_count", "ledger_last_event_id", "evidence_scope"}:
        raise AuditError("Unknown manifest schema")
    if manifest["schema"] != SCHEMA or manifest["evidence_scope"] != "local_paper_state_and_ledger_bytes_only":
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
        key.verify(signature, DOMAIN + manifest_bytes)
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
    _validate_state(payload["state.json"])
    count, last = _validate_ledger(payload["ledger.jsonl"])
    if manifest["ledger_event_count"] != count or manifest["ledger_last_event_id"] != last:
        raise AuditError("Ledger metadata does not match the signed manifest")
    # A late file replacement/extra member is still refused before returning.
    if {child.name for child in bundle_path.iterdir()} != FILES:
        raise AuditError("Bundle changed during verification")
    return {"bundle": str(bundle_path), "ledger_event_count": count,
            "signer_public_key_sha256": fingerprint, "verified": True,
            "evidence_scope": manifest["evidence_scope"]}


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
    args = parser.parse_args()
    try:
        if args.command == "export":
            out = args.out or ROOT / "logs" / f"paper-audit-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
            if args.out is None:
                _path(out.parent.parent, kind="directory")
                out.parent.mkdir(mode=0o700, exist_ok=True)
            result = export_snapshot(args.state, args.ledger, out, args.signing_key)
        else:
            result = verify_snapshot(args.bundle, args.trusted_public_key)
    except (AuditError, OSError) as exc:
        parser.exit(2, f"Audit {args.command} refused ({type(exc).__name__}); inspect local inputs.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
