"""Run an explicitly optional, local GLiNER checkpoint against a frozen protocol.

Use a separate research environment. No project runtime dependency is added.
Dataset, checkpoint and protocol identities are checked before inference. The
output log is exclusive; interruptions leave a partial log, never a scored subset.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time

from eval.news_entity_extraction import canonical_hash, corpus, evaluate_extractions
from eval.news_entity_sentiment import _local_scorer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.input.read_bytes()
    protocol = json.loads(args.protocol.read_text())
    if hashlib.sha256(raw).hexdigest() != protocol["dataset_sha256"]:
        parser.error("Dataset hash differs from frozen protocol")
    manifest = json.loads(args.model_manifest.read_text())
    if manifest["revision"] != protocol["model"]["revision"]:
        parser.error("Model revision differs from protocol")
    required = {"config.json", "encoder_config/config.json", "tokenizer.json",
                "tokenizer_config.json", "model.safetensors"}
    if {entry["path"] for entry in manifest["files"]} != required:
        parser.error("Model manifest does not contain exactly the required files")
    for entry in manifest["files"]:
        content = (args.model_dir / entry["path"]).read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            parser.error("Checkpoint file differs from manifest")
    if args.output.exists() or args.predictions.exists():
        parser.error("Outputs already exist; choose new paths")
    package = importlib.metadata.version("gliner2")
    if "gliner2==" + package != protocol["model"]["package"]:
        parser.error("Installed GLiNER version differs from protocol")
    rows = json.loads(raw)
    data = corpus(rows)
    selected = protocol["selected_rows"]
    labels, baselines = {}, {}
    for backend in ("vader", "keywords"):
        scorer, baselines[backend] = _local_scorer(backend)
        labels[backend] = {index: scorer(data[index]["text"])["label"] for index in selected}

    # Imports and flags are confined to this optional CLI process.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from gliner2 import AutoExtractor, AttributeGroup
    torch.set_num_threads(protocol["inference"]["torch_threads"])
    torch.manual_seed(protocol["selection"]["seed"])
    started = time.monotonic()
    model = AutoExtractor.from_pretrained(str(args.model_dir), local_files_only=True, map_location="cpu")
    load_seconds = time.monotonic() - started
    schema = model.create_schema().entities({protocol["schema"]["entity_type"]: protocol["schema"]["description"]})
    schema.entity_attributes({"sentiment": AttributeGroup(protocol["schema"]["labels"],
                              applies_to=[protocol["schema"]["entity_type"]],
                              qualify_labels=protocol["schema"]["qualify_labels"])})
    batch_size = protocol["inference"]["batch_size"]
    predictions = []
    with args.predictions.open("x", encoding="utf-8") as log:
        for offset in range(0, len(selected), batch_size):
            indices = selected[offset:offset + batch_size]
            start = time.monotonic()
            try:
                outputs = model.batch_extract([data[index]["text"] for index in indices], schema,
                          batch_size=batch_size, threshold=protocol["inference"]["threshold"],
                          include_confidence=True, include_spans=True)
                if len(outputs) != len(indices):
                    raise ValueError("Model returned an unexpected batch length")
                errors = [None] * len(indices)
            except Exception as exc:
                outputs = [{"entities": {}} for _ in indices]
                errors = [type(exc).__name__] * len(indices)
            elapsed = time.monotonic() - start
            for index, output, error in zip(indices, outputs, errors):
                entities = output.get("entities", {}).get(protocol["schema"]["entity_type"], [])
                if not isinstance(entities, list):
                    entities, error = [], "InvalidEntityContainer"
                record = {"row_index": index, "text_sha256": data[index]["text_sha256"],
                          "protocol_sha256": canonical_hash(protocol), "entities": entities,
                          "document_labels": {key: labels[key][index] for key in labels},
                          "error_type": error, "elapsed_seconds": elapsed / len(indices)}
                predictions.append(record)
                log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            log.flush()
            print(json.dumps({"completed": len(predictions), "selected": len(selected),
                              "batch_seconds": round(elapsed, 3), "batch_errors": sum(bool(e) for e in errors)}), flush=True)
    result = evaluate_extractions(rows, protocol, predictions)
    result.update(model_manifest=manifest, baseline_implementations=baselines,
                  runtime={"python": platform.python_version(),
                           "packages": {name: importlib.metadata.version(name) for name in
                                        ("gliner2", "torch", "transformers", "peft", "vaderSentiment")},
                           "device": "cpu", "dtype": str(next(model.parameters()).dtype),
                           "load_seconds": load_seconds,
                           "timing_basis": "batch wall time divided by batch size; not serial response latency"},
                  implementation_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (Path(__file__), Path("eval/news_entity_extraction.py"),
                                   Path("eval/news_entity_sentiment.py"))})
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"complete": True, "cohorts": result["cohorts"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
