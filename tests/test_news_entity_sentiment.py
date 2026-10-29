"""Synthetic, deterministic diagnostics; no external dataset or models needed."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval.news_entity_sentiment import evaluate_document_scorer, main, _local_scorer


def row(text, annotations):
    return {"content": text, "annotations": [
        {"start": start, "end": end, "value": text[start:end], "label": label}
        for start, end, label in annotations]}


def test_gold_mentions_are_not_mistaken_for_documents_and_oracle_has_correct_bound():
    rows = [row("Alpha wins; Beta loses.", [(0, 5, "Positive"), (12, 16, "Negative")]),
            row("Gamma waits.", [(0, 5, "Neutral")])]
    calls = []

    def scorer(text):
        calls.append(text)
        return {"label": "positive" if text.startswith("Alpha") else "neutral"}

    result = evaluate_document_scorer(rows, scorer)
    assert calls == [r["content"] for r in rows]
    all_scores = result["subsets"]["all"]
    assert all_scores["documents"] == 2 and all_scores["mentions"] == 3
    assert all_scores["accuracy"] == pytest.approx(2 / 3)
    assert all_scores["macro_f1"] == pytest.approx(5 / 9)
    assert result["subsets"]["opposing_polarities"]["accuracy"] == .5
    assert result["subsets"]["mixed_labels"]["documents"] == 1
    assert result["document_label_oracle"]["accuracy_ceiling"] == pytest.approx(2 / 3)
    assert result["majority_label_oracle"]["accuracy"] == pytest.approx(1 / 3)
    assert result["scope"]["entity_detection_evaluated"] is False


def test_wrong_offsets_are_not_repaired_to_another_occurrence():
    record = row("AMD wins; AMD loses.", [(0, 3, "Positive"), (10, 13, "Negative")])
    record["annotations"][1].update(start=9, end=12)
    result = evaluate_document_scorer([record], lambda _: {"label": "positive"})
    assert result["audit"]["input_annotations"] == 2
    assert result["audit"]["valid_annotations"] == 1
    assert result["audit"]["invalid_annotations"][0]["reason"] == "span_mismatch"
    assert result["audit"]["documents_with_invalid_annotations"] == 1
    assert result["subsets"]["opposing_polarities"]["mentions"] == 0


def test_chinese_character_spans_validate_without_modifying_source_data():
    rows = [row("英伟达上涨，AMD下跌。", [(0, 3, "Positive"), (6, 9, "Negative")])]
    before = deepcopy(rows)
    result = evaluate_document_scorer(rows, lambda _: {"label": "neutral"})
    assert rows == before
    assert result["audit"]["valid_annotations"] == 2
    assert result["subsets"]["all"]["accuracy"] == 0


@pytest.mark.parametrize("labels", [("Positive", "Positive"), ("Positive", "Negative")])
def test_duplicate_and_conflicting_spans_are_excluded_together(labels):
    rows = [row("Alpha wins.", [(0, 5, label) for label in labels])]
    result = evaluate_document_scorer(rows, lambda _: pytest.fail("No usable annotations to score"))
    assert result["audit"]["valid_annotations"] == 0
    assert len(result["audit"]["invalid_annotations"]) == 2
    assert result["subsets"]["all"]["accuracy"] is None


def test_malformed_inputs_remain_in_audit_with_no_fake_neutral_prediction():
    rows = [None, {"content": "Bad schema"},
            {"content": "Alpha", "annotations": [None, {"label": "buy"},
                                                  {"label": "Neutral", "start": True, "end": 5, "value": "Alpha"}]}]
    result = evaluate_document_scorer(rows, lambda _: pytest.fail("No usable annotations"))
    assert result["audit"]["input_documents"] == 3
    assert len(result["audit"]["invalid_documents"]) == 3
    assert len(result["audit"]["invalid_annotations"]) == 3
    assert result["predictions"] == []
    assert result["document_label_oracle"]["accuracy_ceiling"] is None
    with pytest.raises(ValueError, match="JSON list"):
        evaluate_document_scorer({}, lambda _: None)


@pytest.mark.parametrize("output", [None, {"label": "bullish"}, {"label": "Positive"}])
def test_invalid_scorer_output_fails_instead_of_being_counted_as_neutral(output):
    with pytest.raises(ValueError, match="invalid label"):
        evaluate_document_scorer([row("Alpha", [(0, 5, "Positive")])], lambda _: output)


def test_cli_is_local_hash_bound_and_does_not_overwrite_prior_results(tmp_path, monkeypatch):
    from engine import sentiment
    monkeypatch.setattr(sentiment, "_initialized", False)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "none")
    monkeypatch.setattr(sentiment, "_SCORER", None)
    monkeypatch.setattr(sentiment, "_init_finbert", lambda: pytest.fail("No model downloads"))
    path, output = tmp_path / "data.json", tmp_path / "result.json"
    path.write_text(json.dumps([row("Alpha reports growth.", [(0, 5, "Positive")])]))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    args = ["--input", str(path), "--expected-sha256", digest, "--backend", "keywords",
            "--dataset-revision", "declared-fixture", "--output", str(output)]
    assert main(args) == 0
    result = json.loads(output.read_text())
    assert result["dataset"]["input_sha256"] == digest
    assert result["scorer"]["active_backend"] == "none"
    assert result["subsets"]["all"]["accuracy"] == 1
    assert "predictions" not in result and len(result["prediction_log_sha256"]) == 64
    full_args = [*args[:-1], str(tmp_path / "full.json"), "--include-predictions"]
    assert main(full_args) == 0
    full = json.loads((tmp_path / "full.json").read_text())
    assert len(full["predictions"]) == 1
    assert full["prediction_log_sha256"] == result["prediction_log_sha256"]
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        main(args)
    assert output.read_bytes() == original
    path.write_text("[]")
    with pytest.raises(SystemExit):
        main(args)


def test_scope_survives_real_fusion_and_never_turns_into_entity_attribution(monkeypatch):
    import engine.signal_fusion as fusion
    for name in ("_fetch_options_flow", "_fetch_institutional_signals", "_fetch_social_signal",
                 "_fetch_earnings_signal", "_fetch_prediction_markets_signal"):
        monkeypatch.setattr(fusion, name, lambda *_: {"available": False, "score": 0})
    result = fusion.fuse_signals("NVDA", news_items=[{"score": .5}], record_for_accuracy=False)
    news = result["sources"]["news_sentiment"]
    assert news["sentiment_scope"] == "text_sequence"
    assert news["target_sentiment"] == "not_extracted"
    assert news["score"] == 100  # Scope metadata must not silently retune legacy scores.
    assert "Headline tone: positive" in result["fusion_detail"]
    assert "entity sentiment not extracted" in result["fusion_detail"]


def test_explicit_vader_backend_uses_local_lexicon_without_transformer_initialization(monkeypatch):
    pytest.importorskip("vaderSentiment")
    from engine import sentiment
    monkeypatch.setattr(sentiment, "_initialized", False)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "none")
    monkeypatch.setattr(sentiment, "_SCORER", None)
    monkeypatch.setattr(sentiment, "_init_finbert", lambda: pytest.fail("No transformer loading"))
    scorer, meta = _local_scorer("vader")
    assert meta["active_backend"] == "vader"
    assert meta["package_version"]
    assert scorer("bullish growth and record profit")["label"] == "positive"


def test_missing_vader_fails_without_silently_substituting_another_backend(monkeypatch):
    from engine import sentiment
    monkeypatch.setattr(sentiment, "_init_vader", lambda: False)
    with pytest.raises(ValueError, match="VADER is unavailable"):
        _local_scorer("vader")
