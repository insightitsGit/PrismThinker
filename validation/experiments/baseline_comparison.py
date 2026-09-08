import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import platform
import pydantic
from time import perf_counter
from uuid import uuid4

from pydantic import Field
from prismthinker import __version__ as library_version, EngineConfig
from validation import __version__
from validation.schemas.case import StrictModel
from validation.schemas.result import Result, Status
from validation.datasets.splitting import digest, load_cases, split_cases
from validation.baselines.single_model import FixtureModel, SingleModel
from validation.baselines.majority_vote import MajorityVote
from validation.prismthinker_eval.adapter import PrismThinkerAdapter
from validation.metrics import calculate
from validation.analysis.report import write_report

ROOT = Path(__file__).resolve().parents[2]


class ExperimentConfig(StrictModel):
    seed: int
    dataset_version: str
    dataset: str
    responses: str
    output: str
    split: str
    splits: list[float]
    consensus_confidence: float = Field(ge=0, le=1)
    mock_samples: int = Field(ge=1)
    systems: list[str]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()


def source_hash():
    paths = sorted(list((ROOT/"src/prismthinker").rglob("*.py")) + list((ROOT/"validation").rglob("*.py")))
    return digest({str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in paths})


def run(config_path):
    config_path = Path(config_path).resolve()
    config = ExperimentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    # v0.1 deliberately has no held-out execution switch. A freeze/once ledger
    # belongs to v0.2; refuse test execution instead of merely warning.
    if config.split not in {"calibration", "validation"}:
        raise ValueError("v0.1 permits calibration/validation only; held-out execution is locked")
    cases = load_cases(config_path.parent / config.dataset)
    splits = split_cases(cases, config.seed, config.splits)
    selected = [c for c in cases if c.case_id in splits[config.split]]
    if not selected:
        raise ValueError("selected split is empty")
    responses = json.loads((config_path.parent / config.responses).read_text(encoding="utf-8"))
    providers = [FixtureModel(responses, i, config.seed) for i in range(config.mock_samples)]
    available = {"single_model_mock": SingleModel(providers[0]),
                 "majority_vote_mock": MajorityVote(providers, config.consensus_confidence),
                 "prismthinker": PrismThinkerAdapter(config.consensus_confidence)}
    if not config.systems or len(set(config.systems)) != len(config.systems) or set(config.systems)-available.keys():
        raise ValueError("systems must be a nonempty unique subset of supported systems")
    stamp = datetime.now(timezone.utc)
    experiment_id = stamp.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = (config_path.parent / config.output / experiment_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    dataset_hash = digest([c.model_dump(mode="json") for c in cases])
    effective = {"experiment": config.model_dump(mode="json"), "engine": EngineConfig().model_dump(mode="json")}
    try:
        commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    manifest = {"experiment_id": experiment_id, "git_commit": commit, "git_dirty": dirty,
        "source_hash": source_hash(), "prismthinker_version": library_version,
        "harness_version": __version__, "dataset_version": config.dataset_version,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "pydantic": pydantic.__version__},
        "dataset_hash": dataset_hash, "config_hash": digest(effective),
        "responses_hash": digest(responses), "timestamp": stamp.isoformat(), "random_seed": config.seed,
        "split": config.split, "splits": splits, "selected_case_ids": [c.case_id for c in selected],
        "benchmark_type": "synthetic/mock plumbing validation", "state": "running",
        "model_ids": [], "effective_config": effective,
        "limitations": ["No live LLMs or external/expert benchmarks", "No scientific model superiority inference",
                        "Related domain templates share structure; cross-domain generalization is not established",
                        "Held-out execution disabled until a frozen protocol is implemented"]}
    def save_manifest():
        (output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    save_manifest()
    all_results, metrics = [], {}
    with (output/"cases.jsonl").open("w", encoding="utf-8") as stream:
        for name in config.systems:
            results = []
            for case in selected:
                started = perf_counter()
                try:
                    result = available[name].evaluate(case.system_input())
                    if result.case_id != case.case_id or result.system != name:
                        raise ValueError("provider returned mismatched result identity")
                except Exception as exc:
                    result = Result(case_id=case.case_id, system=name,
                        status=Status.TIMEOUT if isinstance(exc, TimeoutError) else Status.ERROR,
                        error=f"{type(exc).__name__}: {exc}")
                result.latency_ms = (perf_counter()-started)*1000
                stream.write(json.dumps({"case": case.model_dump(mode="json"), "result": result.model_dump(mode="json")})+"\n")
                stream.flush()
                results.append(result)
            all_results.extend(results)
            metrics[name] = {"overall": calculate(selected, results), "domains": {}}
            for domain in sorted({c.domain for c in selected}):
                subset = [c for c in selected if c.domain == domain]
                ids = {c.case_id for c in subset}
                metrics[name]["domains"][domain] = calculate(subset, [r for r in results if r.case_id in ids])
    manifest.update(state="complete", model_ids=sorted({m for r in all_results for m in r.usage.model_ids}))
    save_manifest()
    (output/"metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
    write_report(output, manifest, metrics)
    return output


def main():
    parser = argparse.ArgumentParser(description="PrismThinker validation v0.1 (no external API calls)")
    parser.add_argument("--config", default=str(ROOT/"validation/config/experiment.json"))
    args = parser.parse_args()
    print(run(args.config))


if __name__ == "__main__":
    main()
