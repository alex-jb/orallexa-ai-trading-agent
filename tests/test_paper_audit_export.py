"""Local-only snapshot validation: generated keys and synthetic rows only."""
import base64
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import bot.paper_audit_export as paper_audit_export
from bot.paper_audit_export import (AuditError, BOUND_DOMAIN, export_snapshot, main,
                                    verify_continuity, verify_snapshot)


def _keypair(directory: Path, label: str = "signer") -> tuple[Path, Path]:
    private = Ed25519PrivateKey.generate()
    private_path = directory / f"{label}.private.pem"
    public_path = directory / f"{label}.public.pem"
    private_path.write_bytes(private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()))
    private_path.chmod(0o600)
    public_path.write_bytes(private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo))
    return private_path, public_path


def _row(event_id: str = "a" * 32) -> dict:
    return {
        "event_id": event_id, "timestamp": "2026-09-30T14:00:00+00:00",
        "ticker": "NVDA", "signal": "BUY", "order_type": "market", "qty": 1,
        "order_status": "prepared", "filled_qty": 0.0, "fill_price": None,
        "fees_usd": 0.0, "realized_pnl_total_usd": 0.0, "drawdown_pct": None,
        "event_type": "order_intent", "source_as_of_session": "2026-09-29",
    }


def _inputs(directory: Path) -> tuple[Path, Path]:
    state = directory / "pilot_state.json"
    ledger = directory / "pilot_ledger.jsonl"
    state.write_bytes(b'{\n  "tickers": {"NVDA": {}}, "config": {"qty": 1}\n}\n')
    ledger.write_bytes((json.dumps(_row()) + "\n").encode())
    return state, ledger


def _export(directory: Path) -> tuple[Path, Path, Path, Path, Path]:
    private, public = _keypair(directory)
    state, ledger = _inputs(directory)
    bundle = directory / "signed"
    export_snapshot(state, ledger, bundle, private)
    return state, ledger, bundle, private, public


def test_snapshot_preserves_exact_bytes_and_uses_external_trust(tmp_path):
    state, ledger, bundle, private, public = _export(tmp_path)
    assert (bundle / "state.json").read_bytes() == state.read_bytes()
    assert (bundle / "ledger.jsonl").read_bytes() == ledger.read_bytes()
    result = verify_snapshot(bundle, public)
    assert result["verified"] is True and result["ledger_event_count"] == 1
    assert result["evidence_scope"] == "local_paper_state_and_ledger_bytes_only"
    assert result["pilot_identity_status"] == "identity_unverified" and result["pilot_id"] is None
    assert result["decision_replay_coverage"] == {
        "eligible_rows": 1, "verified_rows": 0, "unverified_rows": 1,
    }  # Older intent rows containing only a digest cannot be replayed.
    assert not any(path.name.endswith("private.pem") for path in bundle.iterdir())
    assert bundle.stat().st_mode & 0o077 == 0
    assert all(path.stat().st_mode & 0o077 == 0 for path in bundle.iterdir())
    with pytest.raises(AuditError, match="already exists"):
        export_snapshot(state, ledger, bundle, private)


@pytest.mark.parametrize("filename", ["state.json", "ledger.jsonl", "manifest.json", "signature.ed25519"])
def test_any_signed_byte_tampering_fails(tmp_path, filename):
    _, _, bundle, _, public = _export(tmp_path)
    path = bundle / filename
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + (b"X" if raw[-1:] != b"X" else b"Y"))
    with pytest.raises(AuditError):
        verify_snapshot(bundle, public)


def test_wrong_public_key_or_self_supplied_key_rejected(tmp_path):
    _, _, bundle, _, public = _export(tmp_path)
    _, other = _keypair(tmp_path, "other")
    with pytest.raises(AuditError, match="fingerprint"):
        verify_snapshot(bundle, other)
    (bundle / "embedded.pem").write_bytes(public.read_bytes())
    with pytest.raises(AuditError, match="outside"):
        verify_snapshot(bundle, bundle / "embedded.pem")


def test_extra_missing_and_symlink_members_rejected(tmp_path):
    _, _, bundle, _, public = _export(tmp_path)
    (bundle / "hidden").write_text("extra")
    with pytest.raises(AuditError, match="missing or unexpected"):
        verify_snapshot(bundle, public)
    (bundle / "hidden").unlink()
    (bundle / "state.json").unlink()
    (bundle / "state.json").symlink_to(tmp_path / "pilot_state.json")
    with pytest.raises(AuditError, match="Symlink"):
        verify_snapshot(bundle, public)
    (bundle / "state.json").unlink()
    with pytest.raises(AuditError, match="missing or unexpected"):
        verify_snapshot(bundle, public)


@pytest.mark.parametrize("bad_ledger", [
    b'{"event_id":"a"}',  # no final LF
    b'\n',  # blank line
    b'{"event_id":"a","event_id":"b"}\n',
    b'{"event_id":"a","x":NaN}\n',
    b'{"event_id":"a","x":1e999}\n',
    b'{"event_id":"a"}\n\n',
])
def test_export_rejects_malformed_or_nonfinite_jsonl(tmp_path, bad_ledger):
    private, _ = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    ledger.write_bytes(bad_ledger)
    with pytest.raises(AuditError):
        export_snapshot(state, ledger, tmp_path / "signed", private)
    assert not (tmp_path / "signed").exists()


def test_export_rejects_duplicate_event_ids_and_wrong_timestamp(tmp_path):
    private, _ = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    raw = ledger.read_bytes()
    ledger.write_bytes(raw + raw)
    with pytest.raises(AuditError, match="Duplicate"):
        export_snapshot(state, ledger, tmp_path / "signed", private)
    row = _row()
    row["timestamp"] = "2026-09-30T14:00:00"
    ledger.write_text(json.dumps(row) + "\n")
    with pytest.raises(AuditError, match="UTC"):
        export_snapshot(state, ledger, tmp_path / "signed", private)


def test_export_rejects_disjoint_state_and_ledger_tickers(tmp_path):
    private, _ = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    state.write_text(json.dumps({"tickers": {"AAPL": {}}, "config": {"qty": 1}}))
    with pytest.raises(AuditError, match="State ticker is absent"):
        export_snapshot(state, ledger, tmp_path / "signed", private)
    assert not (tmp_path / "signed").exists()


def test_blocked_new_ticker_can_be_logged_without_checkpoint(tmp_path):
    from bot.paper_harness import PaperLoop

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    harness = PaperLoop(state, ledger)
    harness.run_ticker("AAPL", [], now=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
    harness.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                       now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
    assert set(json.loads(state.read_text())["tickers"]) == {"NVDA"}
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    assert verify_snapshot(bundle, public)["ledger_event_count"] == 2


@pytest.mark.parametrize("outbox", [{"event_id": "a" * 32}, {}, []])
def test_export_blocks_unrecovered_outbox(tmp_path, outbox):
    private, _ = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    state.write_text(json.dumps({"tickers": {}, "config": {"qty": 1}, "outbox": outbox}))
    with pytest.raises(AuditError, match="outbox"):
        export_snapshot(state, ledger, tmp_path / "signed", private)


def test_rejects_source_key_and_bundle_symlinks(tmp_path):
    private, public = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    alias = tmp_path / "alias-state"
    alias.symlink_to(state)
    with pytest.raises(AuditError, match="Symlink"):
        export_snapshot(alias, ledger, tmp_path / "signed", private)
    alias.unlink()
    alias.symlink_to(private)
    with pytest.raises(AuditError, match="Symlink"):
        export_snapshot(state, ledger, tmp_path / "signed", alias)
    export_snapshot(state, ledger, tmp_path / "signed", private)
    alias.unlink()
    alias.symlink_to(tmp_path / "signed", target_is_directory=True)
    with pytest.raises(AuditError, match="Symlink"):
        verify_snapshot(alias, public)


def test_private_key_custody_and_independent_public_key(tmp_path):
    private, public = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    private.chmod(0o644)
    with pytest.raises(AuditError, match="owner-only"):
        export_snapshot(state, ledger, tmp_path / "signed", private)
    private.chmod(0o600)
    export_snapshot(state, ledger, tmp_path / "signed", private)
    with pytest.raises(AuditError, match="outside"):
        verify_snapshot(tmp_path / "signed", tmp_path / "signed" / "state.json")


def test_signed_truncation_or_reordering_cannot_verify(tmp_path):
    private, public = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    ledger.write_bytes(ledger.read_bytes() + (json.dumps(_row("b" * 32)) + "\n").encode())
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    assert verify_snapshot(bundle, public)["ledger_event_count"] == 2
    original = (bundle / "ledger.jsonl").read_bytes()
    (bundle / "ledger.jsonl").write_bytes(original.splitlines(keepends=True)[-1])
    with pytest.raises(AuditError, match="bytes"):
        verify_snapshot(bundle, public)
    (bundle / "ledger.jsonl").write_bytes(b"".join(reversed(original.splitlines(keepends=True))))
    with pytest.raises(AuditError, match="bytes"):
        verify_snapshot(bundle, public)


def test_verification_rejects_bundle_replaced_after_first_read(tmp_path, monkeypatch):
    _, _, bundle, _, public = _export(tmp_path)
    original_read = paper_audit_export._read
    replaced = False

    def replace_ledger_after_read(path, *, limit):
        nonlocal replaced
        data = original_read(path, limit=limit)
        if path == bundle / "ledger.jsonl" and not replaced:
            (bundle / "ledger.jsonl").write_bytes(b"different contents\n")
            replaced = True
        return data

    monkeypatch.setattr(paper_audit_export, "_read", replace_ledger_after_read)
    with pytest.raises(AuditError, match="Bundle changed during verification"):
        verify_snapshot(bundle, public)
    assert replaced


def test_export_refuses_success_when_directory_sync_fails(tmp_path, monkeypatch):
    private, _ = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory sync failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(paper_audit_export.os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="directory sync failure"):
        export_snapshot(state, ledger, tmp_path / "incomplete-bundle", private)


def test_real_fixed_rule_dry_run_files_export_without_network(tmp_path):
    from bot.paper_harness import PaperLoop

    state = tmp_path / "state.json"
    ledger = tmp_path / "ledger.jsonl"
    harness = PaperLoop(state, ledger)  # No broker or model, default dry-run.
    harness.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                       now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    verified = verify_snapshot(bundle, public)
    assert verified["ledger_event_count"] == 1
    assert verified["decision_replay_coverage"] == {
        "eligible_rows": 1, "verified_rows": 1, "unverified_rows": 0,
    }


def test_real_fixed_rule_paper_fill_rows_export_without_network(tmp_path):
    from bot.paper_harness import PaperLoop

    class FakePaperGateway:
        position = 0.0

        def market_open(self):
            return True

        def last_completed_session(self, now):
            return date(2026, 9, 28)

        def position_qty(self, ticker):
            return self.position

        def by_client_id(self, client_id):
            return None

        def submit_market(self, ticker, side, qty, client_id):
            self.position = float(qty)
            self.order_record = {"id": "paper-1", "client_order_id": client_id,
                                 "symbol": ticker, "side": side, "qty": qty,
                                 "status": "filled", "filled_qty": qty,
                                 "filled_avg_price": 110.11}
            return self.order_record

        def order(self, order_id):
            return self.order_record

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    harness = PaperLoop(state, ledger, broker=FakePaperGateway(), submit_paper=True)
    row = harness.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                             now=datetime(2026, 9, 29, 14, tzinfo=timezone.utc),
                             mark_date=date(2026, 9, 28))
    assert row["order_status"] == "filled"
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    assert verify_snapshot(bundle, public)["ledger_event_count"] == 2


def test_offline_cli_export_and_verify(tmp_path, monkeypatch, capsys):
    private, public = _keypair(tmp_path)
    state, ledger = _inputs(tmp_path)
    bundle = tmp_path / "signed"
    monkeypatch.setattr(sys, "argv", ["paper_audit_export", "export", "--state", str(state),
                                         "--ledger", str(ledger), "--signing-key", str(private),
                                         "--out", str(bundle)])
    main()
    assert json.loads(capsys.readouterr().out)["ledger_event_count"] == 1
    monkeypatch.setattr(sys, "argv", ["paper_audit_export", "verify", "--bundle", str(bundle),
                                         "--trusted-public-key", str(public)])
    main()
    assert json.loads(capsys.readouterr().out)["verified"] is True


def test_later_signed_snapshot_must_strictly_extend_retained_history(tmp_path, monkeypatch, capsys):
    state, ledger, previous, private, public = _export(tmp_path)
    earlier_bytes = ledger.read_bytes()
    ledger.write_bytes(earlier_bytes + (json.dumps(_row("b" * 32)) + "\n").encode())
    current = tmp_path / "current"
    export_snapshot(state, ledger, current, private)
    result = verify_continuity(previous, current, public)
    assert result["verified"] and result["new_events"] == 1
    assert result["previous_ledger_sha256"] == verify_snapshot(previous, public)["ledger_sha256"]
    monkeypatch.setattr(sys, "argv", ["paper_audit_export", "verify-continuity",
                                     "--previous-bundle", str(previous), "--bundle", str(current),
                                     "--trusted-public-key", str(public)])
    main()
    assert json.loads(capsys.readouterr().out)["new_events"] == 1


def test_valid_resigned_truncation_or_rewritten_history_fails_continuity(tmp_path):
    state, ledger, previous, private, public = _export(tmp_path)
    original = ledger.read_bytes()
    # Each later bundle verifies in isolation; their relationship to the
    # retained prior signature is the new control.
    ledger.write_bytes((json.dumps(_row("b" * 32)) + "\n").encode())
    truncated = tmp_path / "truncated"
    export_snapshot(state, ledger, truncated, private)
    assert verify_snapshot(truncated, public)["verified"]
    with pytest.raises(AuditError, match="no new events"):
        verify_continuity(previous, truncated, public)

    changed = _row()
    changed["signal"] = "SELL"
    ledger.write_bytes((json.dumps(changed) + "\n" + json.dumps(_row("c" * 32)) + "\n").encode())
    rewritten = tmp_path / "rewritten"
    export_snapshot(state, ledger, rewritten, private)
    assert verify_snapshot(rewritten, public)["verified"]
    with pytest.raises(AuditError, match="preserve the previous signed history"):
        verify_continuity(previous, rewritten, public)

    ledger.write_bytes(original)
    replay = tmp_path / "replay"
    shutil.copytree(previous, replay)
    with pytest.raises(AuditError, match="not later"):
        verify_continuity(previous, replay, public)


def test_continuity_requires_an_independent_trusted_key(tmp_path):
    state, ledger, previous, private, public = _export(tmp_path)
    ledger.write_bytes(ledger.read_bytes() + (json.dumps(_row("b" * 32)) + "\n").encode())
    current = tmp_path / "current"
    export_snapshot(state, ledger, current, private)
    _, wrong_public = _keypair(tmp_path, "wrong")
    with pytest.raises(AuditError, match="fingerprint"):
        verify_continuity(previous, current, wrong_public)
    with pytest.raises(AuditError, match="different"):
        verify_continuity(previous, previous, public)


def test_new_pilots_reject_same_ticker_cross_pairing_and_continuity(tmp_path):
    from bot.paper_harness import PaperLoop

    private, public = _keypair(tmp_path)
    sources = []
    for name in ("first", "second"):
        state, ledger = tmp_path / f"{name}.json", tmp_path / f"{name}.jsonl"
        loop = PaperLoop(state, ledger)
        loop.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                        now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
        bundle = tmp_path / f"{name}-bundle"
        assert export_snapshot(state, ledger, bundle, private)["pilot_identity_status"] == "bound"
        assert verify_snapshot(bundle, public)["pilot_id"] == loop.pilot_id
        sources.append((state, ledger, bundle))

    with pytest.raises(AuditError, match="same pilot identity"):
        export_snapshot(sources[0][0], sources[1][1], tmp_path / "mixed", private)
    assert not (tmp_path / "mixed").exists()
    with pytest.raises(AuditError, match="different pilot identities"):
        verify_continuity(sources[0][2], sources[1][2], public)


def test_bound_snapshot_refuses_valid_prefix_history_loss_before_signing(tmp_path):
    from bot.paper_harness import PaperLoop

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    harness = PaperLoop(state, ledger)
    for day in (29, 30):
        harness.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                           now=datetime(2026, 9, day, 14, tzinfo=timezone.utc))
    ledger.write_bytes(ledger.read_bytes().splitlines(keepends=True)[0])
    private, _ = _keypair(tmp_path)
    with pytest.raises(AuditError, match="saved checkpoint"):
        export_snapshot(state, ledger, tmp_path / "signed", private)
    assert not (tmp_path / "signed").exists()


def test_resigned_v2_bundle_with_other_pilot_state_is_rejected(tmp_path):
    from bot.paper_harness import PaperLoop

    private, public = _keypair(tmp_path)
    bundles = []
    for name in ("first", "second"):
        state, ledger = tmp_path / f"{name}.json", tmp_path / f"{name}.jsonl"
        PaperLoop(state, ledger).run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                                            now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
        bundle = tmp_path / f"{name}-bundle"
        export_snapshot(state, ledger, bundle, private)
        bundles.append(bundle)
    forged, other = bundles
    replacement = (other / "state.json").read_bytes()
    (forged / "state.json").write_bytes(replacement)
    manifest = json.loads((forged / "manifest.json").read_bytes())
    manifest["files"]["state.json"] = {"sha256": hashlib.sha256(replacement).hexdigest(),
                                       "size_bytes": len(replacement)}
    manifest_bytes = paper_audit_export._canonical(manifest)
    key = serialization.load_pem_private_key(private.read_bytes(), password=None)
    (forged / "manifest.json").write_bytes(manifest_bytes)
    (forged / "signature.ed25519").write_bytes(
        base64.b64encode(key.sign(BOUND_DOMAIN + manifest_bytes)) + b"\n")
    with pytest.raises(AuditError, match="same pilot identity"):
        verify_snapshot(forged, public)


def test_replays_buy_no_change_sell(tmp_path):
    from bot.paper_harness import PaperLoop

    class FakePaperGateway:
        def __init__(self):
            self.position = 0.0
            self.orders = {}
            self.submissions = []

        def market_open(self):
            return True

        def last_completed_session(self, now):
            return {(9, 29): date(2026, 9, 28),
                    (9, 30): date(2026, 9, 29),
                    (10, 1): date(2026, 9, 30)}[(now.month, now.day)]

        def position_qty(self, ticker):
            return self.position

        def by_client_id(self, client_id):
            return self.orders.get(client_id)

        def submit_market(self, ticker, side, qty, client_id):
            self.submissions.append((side, qty))
            self.position += qty if side == "BUY" else -qty
            order = {"id": client_id, "client_order_id": client_id,
                     "symbol": ticker, "side": side, "qty": qty,
                     "status": "filled", "filled_qty": qty,
                     "filled_avg_price": 110.11 if side == "BUY" else 89.91}
            self.orders[client_id] = order
            return order

        def order(self, order_id):
            return self.orders[order_id]

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    broker = FakePaperGateway()
    harness = PaperLoop(state, ledger, broker=broker, submit_paper=True)
    buy = [100.0] * 30 + [110.0] * 20
    sell = [110.0] * 30 + [90.0] * 20
    for day, session, bars in [(29, 28, buy), (30, 29, buy), (1, 30, sell)]:
        month = 9 if day != 1 else 10
        harness.run_ticker("NVDA", bars, now=datetime(2026, month, day, 14, tzinfo=timezone.utc),
                           mark_date=date(2026, 9, session), source_kind="alpaca_iex_daily_bars")
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "order_intent", "decision", "decision", "order_intent", "decision",
    ]
    assert rows[2]["order_status"] == "no_change"
    assert rows[2]["input_closes"] == buy
    assert rows[2]["source_kind"] == "alpaca_iex_daily_bars"
    assert broker.submissions == [("BUY", 1), ("SELL", 1.0)]
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    exported = export_snapshot(state, ledger, bundle, private)
    assert exported["decision_replay_coverage"]["verified_rows"] == 5
    assert verify_snapshot(bundle, public)["decision_replay_coverage"] == {
        "eligible_rows": 5, "verified_rows": 5, "unverified_rows": 0,
    }


def test_pending_fill_reconciliation_excluded_from_signed_decision_replay(tmp_path):
    from bot.paper_harness import PaperLoop

    class FakePendingPaperGateway:
        def __init__(self):
            self.position = 0.0
            self.order_record = None

        def market_open(self):
            return True

        def last_completed_session(self, now):
            return date(2026, 9, 28) if now.day == 29 else date(2026, 9, 29)

        def position_qty(self, ticker):
            return self.position

        def by_client_id(self, client_id):
            return None

        def submit_market(self, ticker, side, qty, client_id):
            self.order_record = {"id": "paper-1", "client_order_id": client_id,
                                 "symbol": ticker, "side": side, "qty": qty,
                                 "status": "new", "filled_qty": 0,
                                 "filled_avg_price": 0}
            return self.order_record

        def order(self, order_id):
            return self.order_record

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    broker = FakePendingPaperGateway()
    harness = PaperLoop(state, ledger, broker=broker, submit_paper=True)
    bars = [100.0] * 30 + [110.0] * 20
    first = harness.run_ticker("NVDA", bars, now=datetime(2026, 9, 29, 14, tzinfo=timezone.utc),
                               mark_date=date(2026, 9, 28))
    assert first["order_status"] == "new"
    broker.order_record.update(status="filled", filled_qty=1, filled_avg_price=110.11)
    broker.position = 1.0
    second = harness.run_ticker("NVDA", bars, now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc),
                                mark_date=date(2026, 9, 29))
    assert second["order_status"] == "no_change"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "order_intent", "decision", "reconciliation", "decision",
    ]
    assert rows[2]["filled_qty"] == 1
    assert "input_closes" not in rows[2]
    assert rows[3]["input_closes"] == bars
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    assert verify_snapshot(bundle, public)["decision_replay_coverage"] == {
        "eligible_rows": 3, "verified_rows": 3, "unverified_rows": 0,
    }


@pytest.mark.parametrize(("field", "replacement", "error"), [
    ("signal", "SELL", "does not replay"),
    ("sma20", 1.0, "does not replay"),
    ("signal_price", 1.0, "does not replay"),
    ("input_closes_sha256", "0" * 64, "input hash"),
])
def test_validly_resigned_malicious_decision_still_fails_replay(tmp_path, field, replacement, error):
    from bot.paper_harness import PaperLoop

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    PaperLoop(state, ledger).run_ticker(
        "NVDA", [100.0] * 30 + [110.0] * 20,
        now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
    private_path, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private_path)
    forged = json.loads(ledger.read_text().strip())
    forged[field] = replacement  # Contradicts the stored transformed closes.
    forged_bytes = (json.dumps(forged, sort_keys=True) + "\n").encode()
    ledger.write_bytes(forged_bytes)
    with pytest.raises(AuditError, match=error):
        export_snapshot(state, ledger, tmp_path / "newly_signed", private_path)

    # Simulate a signer who knowingly signs newly malicious but valid bytes.
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    manifest["files"]["ledger.jsonl"] = {
        "sha256": hashlib.sha256(forged_bytes).hexdigest(), "size_bytes": len(forged_bytes),
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False) + "\n").encode()
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    (bundle / "ledger.jsonl").write_bytes(forged_bytes)
    (bundle / "manifest.json").write_bytes(manifest_bytes)
    (bundle / "signature.ed25519").write_bytes(
        base64.b64encode(key.sign(BOUND_DOMAIN + manifest_bytes)) + b"\n")
    with pytest.raises(AuditError, match=error):
        verify_snapshot(bundle, public)


def test_data_block_has_no_replay_claim(tmp_path):
    from bot.paper_harness import PaperLoop

    state, ledger = tmp_path / "state.json", tmp_path / "ledger.jsonl"
    harness = PaperLoop(state, ledger)
    blocked = harness.run_ticker("NVDA", [], now=datetime(2026, 9, 29, 14, tzinfo=timezone.utc))
    assert blocked["signal"] == "HOLD" and "input_closes" not in blocked
    harness.run_ticker("NVDA", [100.0] * 30 + [110.0] * 20,
                       now=datetime(2026, 9, 30, 14, tzinfo=timezone.utc))
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert "input_closes" not in rows[0]
    private, public = _keypair(tmp_path)
    bundle = tmp_path / "signed"
    export_snapshot(state, ledger, bundle, private)
    assert verify_snapshot(bundle, public)["decision_replay_coverage"] == {
        "eligible_rows": 1, "verified_rows": 1, "unverified_rows": 0,
    }
