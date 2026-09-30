"""Offline controls for the predeclared fault study and its blind spot."""
import json
import subprocess
import sys
from pathlib import Path

import eval.paper_audit_fault_study as study


def test_default_data_is_checked_in_and_a_changed_seed_changes_the_data():
    state, ledger = study.synthetic_inputs(study.DEFAULT_SEED)
    assert state == (study.FIXTURES / "paper_audit_fault_state_v1.json").read_bytes()
    assert ledger == (study.FIXTURES / "paper_audit_fault_ledger_v1.jsonl").read_bytes()
    assert len(ledger.splitlines()) == 4
    assert study.synthetic_inputs(study.DEFAULT_SEED + 1)[1] != ledger


def test_cli_reports_independent_failure_controls_and_documented_blind_spot(tmp_path):
    output = tmp_path / "fault-report.json"
    run = subprocess.run([sys.executable, "-m", "eval.paper_audit_fault_study",
                          "--output", str(output)], capture_output=True, text=True, check=True)
    report = json.loads(run.stdout)
    assert json.loads(output.read_text()) == report
    assert report["passed"] is True
    assert len(report["results"]) == 13
    assert len({row["case"] for row in report["results"]}) == 13
    assert sum(row["rejected"] for row in report["results"]) == 11
    assert all(row["matched_expected"] and row["unexpected_error_type"] is None
               for row in report["results"])
    outcomes = {row["case"]: row for row in report["results"]}
    assert outcomes["intact_signed_bundle"]["rejected"] is False
    assert outcomes["valid_history_loss_before_first_signature"]["rejected"] is False
    assert outcomes["malformed_tail_before_signing"]["phase"] == "export"
    assert outcomes["wrong_independent_trusted_key"]["rejected"] is True
    assert report["fixture"]["synthetic"] and report["fixture"]["row_count"] == 4
    assert report["cost_assumptions"]["broker_calls"] == 0
    assert report["cost_assumptions"]["llm_calls"] == 0
    assert all(row["elapsed_ms"] >= 0 for row in report["results"])


def test_study_fails_if_verifier_accepts_every_mutated_bundle(monkeypatch):
    # This tests the study's rejection oracle, beyond retesting the verifier.
    monkeypatch.setattr(study.audit, "verify_snapshot",
                        lambda bundle, trusted_key: {"ledger_event_count": 3})
    report = study.run_study()
    assert report["passed"] is False
    assert len([row for row in report["results"] if not row["matched_expected"]]) >= 10
    assert report["results"][0]["matched_expected"] is True
    assert report["results"][-1]["matched_expected"] is True


def test_modified_valid_rows_stay_well_formed_but_differ_from_signed_source(tmp_path):
    _, original_ledger = study.synthetic_inputs(study.DEFAULT_SEED)
    for case in ("ledger_complete_row_truncation", "ledger_row_reorder", "ledger_valid_row_modify"):
        bundle = tmp_path / case
        bundle.mkdir()
        ledger = bundle / "ledger.jsonl"
        ledger.write_bytes(original_ledger)
        study._mutate(case, bundle)
        modified = ledger.read_bytes()
        assert modified != original_ledger and modified.endswith(b"\n")
        assert all(isinstance(json.loads(row), dict) for row in modified.splitlines())
