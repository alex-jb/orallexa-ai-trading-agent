"""Exercise the optional CLI without installing neural packages in application CI."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from eval.news_entity_extraction import freeze_protocol
from eval.run_news_entity_probe import main


@pytest.mark.parametrize("failure", [False, True])
def test_offline_cli_keeps_all_rows_and_distinguishes_backend_labels(tmp_path, monkeypatch, failure):
    import eval.run_news_entity_probe as probe
    rows = [{"content": "Alpha rises; Beta falls.", "annotations": [
        {"start": 0, "end": 5, "value": "Alpha", "label": "Positive"},
        {"start": 13, "end": 17, "value": "Beta", "label": "Negative"}]}]
    raw = json.dumps(rows).encode()
    input_path = tmp_path / "input.json";input_path.write_bytes(raw)
    protocol = freeze_protocol(rows, dataset_sha256=hashlib.sha256(raw).hexdigest(), model_revision="fixture")
    protocol_path = tmp_path / "protocol.json";protocol_path.write_text(json.dumps(protocol))
    model_dir = tmp_path / "checkpoint";model_dir.mkdir()
    manifest = {"model": "fastino/gliner2.5-small-v1", "revision": "fixture", "files": []}
    for name in ("config.json", "encoder_config/config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors"):
        path = model_dir / name;path.parent.mkdir(exist_ok=True);path.write_bytes(b"fixture")
        manifest["files"].append({"path": name, "bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()})
    manifest_path = tmp_path / "manifest.json";manifest_path.write_text(json.dumps(manifest))
    current = {"backend": None}

    def local_scorer(backend):
        current["backend"] = backend
        return lambda _: {"label": "positive" if current["backend"] == "vader" else "neutral"}, {"backend": backend}

    monkeypatch.setattr(probe, "_local_scorer", local_scorer)
    monkeypatch.setattr(probe.importlib.metadata, "version", lambda name: "2.1.0" if name == "gliner2" else "fixture")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None, manual_seed=lambda _: None))

    class Schema:
        def entities(self, _): return self
        def entity_attributes(self, _): return self

    class Model:
        def create_schema(self): return Schema()
        def parameters(self): return iter([SimpleNamespace(dtype="fixture")])
        def batch_extract(self, texts, schema, **kwargs):
            assert texts == [rows[0]["content"]]
            assert kwargs["include_spans"] and kwargs["include_confidence"]
            assert kwargs["threshold"] == .5
            if failure: raise RuntimeError("synthetic inference failure")
            return [{"entities": {"financial_entity": [
                {"start": 0, "end": 5, "text": "Alpha", "sentiment": {"label": "positive"}},
                {"start": 13, "end": 17, "text": "Beta", "sentiment": {"label": "negative"}}]}}]

    def load(path, **kwargs):
        assert path == str(model_dir)
        assert kwargs == {"local_files_only": True, "map_location": "cpu"}
        assert os.environ["HF_HUB_OFFLINE"] == os.environ["TRANSFORMERS_OFFLINE"] == "1"
        return Model()

    monkeypatch.setitem(sys.modules, "gliner2", SimpleNamespace(
        AutoExtractor=SimpleNamespace(from_pretrained=load), AttributeGroup=lambda *args, **kwargs: object()))
    predictions_path, output_path = tmp_path / "predictions.jsonl", tmp_path / "output.json"
    args = ["--input", str(input_path), "--protocol", str(protocol_path), "--model-dir", str(model_dir),
            "--model-manifest", str(manifest_path), "--predictions", str(predictions_path), "--output", str(output_path)]
    assert main(args) == 0
    result = json.loads(output_path.read_text())
    assert result["complete"] is True
    metrics = result["cohorts"]["seeded_random"]
    assert metrics["detection"]["gold"] == 2
    assert metrics["inference_errors"] == int(failure)
    assert metrics["joint_span_and_sentiment"]["recall"] == (0 if failure else 1)
    output = json.loads(predictions_path.read_text())
    assert output["document_labels"] == {"vader": "positive", "keywords": "neutral"}
    before = output_path.read_bytes()
    with pytest.raises(SystemExit): main(args)
    assert output_path.read_bytes() == before
    input_path.write_bytes(b"[]")
    with pytest.raises(SystemExit): main(args)
