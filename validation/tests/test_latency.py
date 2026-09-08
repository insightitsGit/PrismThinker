import cProfile
import json
from pathlib import Path
import pytest
from prismthinker import PrismThinker, EngineConfig
from validation.datasets.splitting import load_cases, digest
from validation.experiments.latency import LatencyConfig, measure, stage_times, summarize, run

ROOT = Path(__file__).resolve().parents[1]


def test_measure_public_api_and_profile(tmp_path):
    case = load_cases(ROOT/"datasets/processed/local-v0.1.1.jsonl")[0]
    path = tmp_path/"profile.prof"
    row = measure(PrismThinker(EngineConfig(isolate_heads=False)), case, path)
    assert row["status"] == "ok"
    assert row["timings_ms"]["total"] >= row["timings_ms"]["evaluate"] > 0
    assert row["profile_stages"]["classifier"]["calls"] == 1
    assert row["profile_stages"]["worker_launch"] is None
    assert row["profile_stages"]["selector"]["calls"] == 1
    assert path.exists()
    assert "tau_effective" not in row["timings_ms"]


def test_failures_preserved():
    case = load_cases(ROOT/"datasets/processed/local-v0.1.1.jsonl")[0]
    class Broken:
        def evaluate(self, context): raise RuntimeError("deliberate test failure")
    row = measure(Broken(), case)
    assert row["status"] == "error"
    assert "deliberate test failure" in row["error"]
    assert row["timings_ms"]["total"] > 0


def test_excludes_warmups_and_profiles():
    rows = [{"mode":"thread", "phase":phase, "case_id":"one", "repetition":0,
             "status":"error", "timings_ms":{"total":value}}
            for phase,value in [("warmup",1000), ("measurement",5), ("profile",2000)]]
    metrics = summarize(rows, [])
    assert metrics["thread"]["timings_ms"]["total"]["mean"] == 5
    assert metrics["thread"]["failures"] == 1
    assert metrics["thread"]["profile_stages_ms"]["worker_launch"]["mean"] is None


def test_latency_runner_manifest_and_holdout_guard(tmp_path):
    config = json.loads((ROOT/"config/latency.json").read_text())
    config.update(dataset=str(ROOT/"datasets/processed/local-v0.1.1.jsonl"), output=str(tmp_path/"runs"),
                  warmup_rounds=0, repetitions=1, profile_repetitions=1, head_repetitions=1, modes=[False])
    path = tmp_path/"latency.json"
    path.write_text(json.dumps(config))
    out = run(path)
    manifest = json.loads((out/"manifest.json").read_text())
    assert manifest["state"] == "complete"
    assert manifest["config_hash"] == digest(manifest["effective_config"])
    assert len((out/"cases.jsonl").read_text().splitlines()) == 24
    assert (out/"heads.jsonl").read_text()
    assert (out/"summary.md").exists()
    config["split"] = "test"
    with pytest.raises(ValueError, match="locked"): LatencyConfig.model_validate_json(json.dumps(config))
