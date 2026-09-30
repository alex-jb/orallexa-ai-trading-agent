# Offline fault injection for the signed PAPER audit snapshot

This study checks the local snapshot exporter and verifier from [the PAPER
harness](PAPER_HARNESS.md). It creates fictional state and JSONL ledger files,
temporary Ed25519 keys, and disposable signed bundles in a temporary directory.
It makes **no Alpaca or LLM calls**, places no orders, and does not measure a
trading strategy's returns.

## Reproduce

From the repository root with `requirements.txt` installed:

```bash
python -m eval.paper_audit_fault_study --output /tmp/orallexa-audit-fault-report.json
python -m pytest -q tests/test_paper_audit_fault_study.py tests/test_paper_audit_export.py
```

The checked-in [state](../eval/fixtures/paper_audit_fault_state_v1.json) and
[ledger](../eval/fixtures/paper_audit_fault_ledger_v1.jsonl) contain only synthetic
records. `synthetic_inputs(20260930)` in
[`eval/paper_audit_fault_study.py`](../eval/paper_audit_fault_study.py) generates
their exact bytes and checks for fixture drift. `--seed N` generates a different
fictional cohort; default seed is `20260930`. The JSON report includes input
SHA-256 hashes, script version, audit module SHA-256, dependency version, seed,
and each case's expected and observed rejection. Runtime durations use local
`perf_counter_ns` and vary by machine; they are descriptive diagnostics rather
than benchmark results. No private key or signed bundle is retained or checked
in. The `--output` file contains only the JSON report.
The [2026-09-30 local run report](../eval/reports/paper_audit_fault_study_2026-09-30.json)
records one execution against the audit module hash inside it. Its per-case
durations are machine-specific observations; rerunning the script is the
verification step, and exact timings are not expected to match.

## Predeclared cases and outcomes

Each verification case starts with its own copy of the same correctly signed
four-row bundle. A failure counts as detected **only** when the audited API
raises `AuditError`; an unexpected crash fails the study. `passed` requires
every observation to match the predeclared expectation.

| Phase | Case | Expected |
| --- | --- | --- |
| Verify | Intact signed bundle | Accept |
| Verify | Remove one complete ledger row after signing | Reject |
| Verify | Reorder complete JSONL rows after signing | Reject |
| Verify | Modify a valid row's signal after signing | Reject |
| Verify | Modify valid state JSON after signing | Reject |
| Verify | Modify canonical manifest after signing | Reject |
| Verify | Modify signature while keeping base64 well formed | Reject |
| Verify | Remove a required bundle member | Reject |
| Verify | Add an unexpected bundle member | Reject |
| Verify | Append a malformed JSONL tail after signing | Reject |
| Verify | Supply the wrong independently held public key | Reject |
| Export | Present a malformed tail before signing | Reject |
| Export then verify | Remove a valid whole row **before the first signature** | Accept: known blind spot |

For the default seed, the expected result is **13/13 controls matched**, with
11 rejected inputs and two accepted controls. The final accepted case shows why
a valid signature cannot reconstruct absent pre-signature history. Its signed
ledger has three rows; the reference synthetic data has four.

## Scope and cost assumptions

The only costs modeled here are **$0.00 broker API cost**, **$0.00 LLM API
cost**, and **$0.00 assumed PAPER commission**. There are zero broker and LLM
calls. Slippage is not modeled because the rows are fictional and the study
does not compute P&L. These are study assumptions, not measurements of Alpaca
fees or a backtest transaction-cost model.

The result supports a narrow statement: these injected errors were accepted or
rejected by this version of the local exporter/verifier. It cannot establish
that original records were complete, that the signing key belonged to a
particular owner, that paper orders actually filled, or that a strategy has an
edge. A malicious signer can sign altered records; a replayed old valid bundle
also remains verifiable without a separately trusted later anchor. Preserve
the trusted public key and snapshot fingerprints outside the exported bundle.
