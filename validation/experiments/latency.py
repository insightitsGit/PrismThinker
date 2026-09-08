"""Measure the unmodified public engine; separately profile its implementation.

No monkeypatches, alternative engine logic, or persistent worker optimization.
Main-thread cProfile cannot measure child/thread evaluator computation. Explicit
sequential head replays measure that separately; never add them to pool latency.
"""
import argparse
import cProfile
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import pstats
import random
import subprocess
from time import perf_counter
from uuid import uuid4

import pydantic
from pydantic import Field, model_validator
from prismthinker import EngineConfig, PrismThinker, __version__ as library_version
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.core.selector import build_registry
from validation import __version__
from validation.datasets.splitting import digest, load_cases, split_cases
from validation.experiments.baseline_comparison import ROOT, git, source_hash
from validation.metrics.core import percentile
from validation.schemas.case import StrictModel


class LatencyConfig(StrictModel):
    seed: int
    dataset_version: str
    dataset: str
    split: str
    splits: list[float]
    output: str
    warmup_rounds: int = Field(ge=0)
    repetitions: int = Field(ge=1)
    profile_repetitions: int = Field(ge=1)
    head_repetitions: int = Field(ge=1)
    modes: list[bool] = Field(min_length=1)

    @model_validator(mode="after")
    def valid(self):
        if self.split not in {"calibration", "validation"}:
            raise ValueError("held-out latency execution is locked")
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("duplicate isolation modes")
        return self


STAGES = {
    "classifier": ("classifier/router.py", "classify"),
    "selector": ("core/selector.py", "select_evaluators"),
    "evidence": ("core/evidence.py", "detect_evidence_conflicts"),
    "pool": ("core/engine.py", "_run_pool"),
    "worker_launch": ("core/isolation.py", "start_head_workers"),
    "worker_ready_wait": ("core/isolation.py", "wait_workers_ready"),
    "worker_cleanup": ("core/isolation.py", "terminate_process"),
    "contradiction": ("core/contradiction.py", "contradiction_matrix"),
    "uncertainty": ("core/uncertainty.py", "uncertainty_score"),
    "counterfactual": ("core/counterfactual.py", "probe_counterfactuals"),
    "disposition": ("core/disposition.py", "apply_lattice"),
}


def stage_times(profiler):
    stats = pstats.Stats(profiler).stats
    result = {}
    for stage, (suffix, function) in STAGES.items():
        matches = [v for (filename, _, name), v in stats.items()
                   if filename.replace("\\", "/").endswith(suffix) and name == function]
        result[stage] = {"calls": sum(v[1] for v in matches),
                         "cumulative_ms": sum(v[3] for v in matches)*1000} if matches else None
    return result


def measure(engine, case, profile_path=None):
    row = {"case_id": case.case_id, "status": "ok", "timings_ms": {}}
    started = perf_counter()
    profiler = cProfile.Profile() if profile_path else None
    try:
        t0 = perf_counter()
        context = case.system_input().reasoning_context()
        row["timings_ms"]["input_adapter"] = (perf_counter()-t0)*1000
        t0 = perf_counter()
        if profiler: profiler.enable()
        try:
            graph = engine.evaluate(context)
        finally:
            if profiler: profiler.disable()
            row["timings_ms"]["evaluate"] = (perf_counter()-t0)*1000
        t0 = perf_counter()
        envelope = to_chorusgraph(graph)
        row["timings_ms"]["egress"] = (perf_counter()-t0)*1000
        t0 = perf_counter()
        serialized = graph.model_dump_json()
        row["timings_ms"]["serialization"] = (perf_counter()-t0)*1000
        # Stop before report parsing/writing. Full raw output is still retained.
        row["timings_ms"]["total"] = (perf_counter()-started)*1000
        row.update(directive=envelope.directive.value, graph=json.loads(serialized),
                   head_errors=len(graph.errors))
    except Exception as exc:
        row.update(status="error", error=f"{type(exc).__name__}: {exc}")
        row["timings_ms"]["total"] = (perf_counter()-started)*1000
    finally:
        if profiler:
            profiler.dump_stats(str(profile_path))
            row["profile_stages"] = stage_times(profiler)
    return row


def distribution(values):
    return {"n": len(values), "mean": sum(values)/len(values) if values else None,
            **{name: percentile(values, q) for name,q in [("p50", .5), ("p95", .95), ("p99", .99)]}}


def decision_signature(row):
    if row["status"] != "ok": return None
    graph = row["graph"]
    return {"directive": row["directive"], "verdict": graph["recommended_verdict"],
            "disposition": graph["disposition"], "delta": graph["contradiction_score"],
            "uncertainty": graph["uncertainty_score"], "errors": graph["errors"]}


def summarize(rows, heads):
    result = {}
    for mode in sorted({r["mode"] for r in rows}):
        timed = [r for r in rows if r["mode"] == mode and r["phase"] == "measurement"]
        profiled = [r for r in rows if r["mode"] == mode and r["phase"] == "profile"]
        result[mode] = {
            "evaluations": len(timed), "failures": sum(r["status"] != "ok" for r in timed),
            "head_errors": sum(r.get("head_errors", 0) for r in timed),
            "timings_ms": {key: distribution([r["timings_ms"][key] for r in timed if key in r["timings_ms"]])
                for key in ["total", "evaluate", "input_adapter", "egress", "serialization"]},
            "profile_stages_ms": {stage: distribution([r["profile_stages"][stage]["cumulative_ms"]
                for r in profiled if r.get("profile_stages", {}).get(stage) is not None]) for stage in STAGES},
        }
    paired = {}
    for row in rows:
        if row["phase"] == "measurement":
            paired.setdefault((row["case_id"], row["repetition"]), {})[row["mode"]] = row
    complete = [pair for pair in paired.values() if set(pair) == {"isolated", "thread"}]
    result["paired"] = {"pairs": len(complete), "unavailable_pairs": sum(
        any(r["status"] != "ok" for r in pair.values()) for pair in complete),
        "decision_mismatches": [key for key, pair in paired.items() if set(pair) == {"isolated", "thread"}
            and all(r["status"] == "ok" for r in pair.values())
            and decision_signature(pair["isolated"]) != decision_signature(pair["thread"])]}
    result["head_replay"] = {name: {"latency_ms": distribution([h["latency_ms"] for h in heads if h["head"] == name]),
        "failures": sum(h["status"] != "ok" for h in heads if h["head"] == name)}
        for name in sorted({h["head"] for h in heads})}
    return result


def write_report(output, manifest, metrics):
    lines = ["# Local latency diagnostic", "", f"Run: {manifest['experiment_id']}", "",
        "Unmodified PrismThinker, synthetic validation cases. No architecture changes or optimizations.", "",
        "Headline distributions use unprofiled calls. Warmups and cProfile calls are saved but excluded. Each case/repetition uses both modes in seeded randomized order; engines are reused but isolated head processes are still created per evaluation.", ""]
    for mode in ("isolated", "thread"):
        if mode not in metrics: continue
        data = metrics[mode]
        lines += [f"## {mode}", "", f"Evaluations: {data['evaluations']}; outer failures: {data['failures']}; internal head errors: {data['head_errors']}.", ""]
        for name, values in data["timings_ms"].items():
            lines += [f"- {name} (ms): {json.dumps(values)}"]
        lines += ["", "Separate cProfile cumulative stage measurements (ms):", ""]
        for stage, values in data["profile_stages_ms"].items():
            lines += [f"- {stage}: {json.dumps(values)}"]
        lines += [""]
    lines += ["## Evaluator compute replay", "",
        "Sequential, in-process replays of the same selected heads and inputs, separate from the public engine runs. These timings exclude process/thread startup, IPC and engine sanitation. They are not per-worker compute measurements from the isolated run.", ""]
    lines += [f"- {head}: {json.dumps(values)}" for head, values in metrics["head_replay"].items()]
    lines += ["", f"Paired checks: {json.dumps(metrics['paired'])}", "",
        "## Interpretation", "",
        "Pool time includes startup, scheduling, readiness, IPC, evaluator execution and cleanup. worker_launch and worker_ready_wait are parent-side measurements: ready-wait includes child imports/setup and scheduling, and can overlap head execution. Do not interpret either as pure CPU time.", "",
        "Profile stages are inclusive and nested: pool contains launch/readiness/cleanup; counterfactual can contain reruns. They must not be stacked or summed as disjoint components. Missing stages have n=0/null rather than invented timings.", "",
        "The engine's per-head latency fields measure result collection/waiting rather than evaluator computation. Raw values are retained, but direct head replays are used for the separate compute diagnostic.", "",
        "Serialization measures graph.model_dump_json; total includes input adaptation, evaluate, egress and serialization but excludes artifact I/O and engine construction (recorded in manifest). cProfile runs have instrumentation overhead. Small-sample p99 is an interpolated descriptive value, not a production latency guarantee.", "",
        "Thread mode changes isolation and timeout semantics; lower latency alone is not a reason to change the default. No persistent workers were introduced. Test data remains locked."]
    (output/"summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (output/"tables").mkdir(exist_ok=True)
    with (output/"tables/latency.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["mode", "phase", "metric", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms"])
        for mode in ("isolated", "thread"):
            if mode not in metrics: continue
            for category in ("timings_ms", "profile_stages_ms"):
                for metric, values in metrics[mode][category].items():
                    writer.writerow([mode, category, metric, *[values[k] for k in ("n","mean","p50","p95","p99")]])


def run(config_path):
    path = Path(config_path).resolve()
    config = LatencyConfig.model_validate_json(path.read_text(encoding="utf-8"))
    cases = load_cases(path.parent/config.dataset)
    splits = split_cases(cases, config.seed, config.splits)
    selected = [c for c in cases if c.case_id in splits[config.split]]
    if not selected: raise ValueError("selected split is empty")
    stamp = datetime.now(timezone.utc)
    experiment_id = "latency-"+stamp.strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8]
    output = (path.parent/config.output/experiment_id).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/"profiles").mkdir()
    engines, configs, initialization = {}, {}, {}
    for isolate in config.modes:
        mode = "isolated" if isolate else "thread"
        engine_config = EngineConfig(isolate_heads=isolate)
        configs[mode] = engine_config.model_dump(mode="json")
        started = perf_counter()
        engines[mode] = PrismThinker(engine_config)
        initialization[mode] = (perf_counter()-started)*1000
    effective = {"experiment": config.model_dump(mode="json"), "engines": configs}
    try: commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError): commit, dirty = None, None
    manifest = {"experiment_id": experiment_id, "timestamp": stamp.isoformat(), "state": "running",
        "git_commit": commit, "git_dirty": dirty, "source_hash": source_hash(),
        "harness_version": __version__, "prismthinker_version": library_version,
        "dataset_version": config.dataset_version, "dataset_hash": digest([c.model_dump(mode="json") for c in cases]),
        "config_hash": digest(effective), "effective_config": effective, "random_seed": config.seed,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(), "pydantic": pydantic.__version__},
        "model_ids": [], "split": config.split, "splits": splits, "initialization_ms": initialization,
        "selected_case_ids": [c.case_id for c in selected], "benchmark_type": "synthetic local latency diagnostic"}
    def save(): (output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    save()
    rng = random.Random(config.seed)
    rows = []
    with (output/"cases.jsonl").open("w", encoding="utf-8") as stream:
        for phase, repetitions in [("warmup", config.warmup_rounds), ("measurement", config.repetitions), ("profile", config.profile_repetitions)]:
            for repetition in range(repetitions):
                order = list(selected)
                rng.shuffle(order)
                for case in order:
                    modes = list(engines)
                    rng.shuffle(modes)
                    for mode in modes:
                        # Numeric index prevents untrusted case IDs becoming paths.
                        profile = output/"profiles"/f"{len(rows)}.prof" if phase == "profile" else None
                        row = measure(engines[mode], case, profile)
                        row.update(phase=phase, repetition=repetition, mode=mode, case=case.model_dump(mode="json"))
                        rows.append(row)
                        stream.write(json.dumps(row)+"\n")
                        stream.flush()
    heads = []
    registry = build_registry(EngineConfig())
    with (output/"heads.jsonl").open("w", encoding="utf-8") as stream:
        for case in selected:
            context = case.system_input().reasoning_context()
            names = sorted({name for r in rows if r["case_id"] == case.case_id and r["status"] == "ok"
                            for name in r["graph"]["selected_evaluators"]})
            for name in names:
                for repetition in range(config.head_repetitions):
                    row = {"case_id": case.case_id, "head": name, "repetition": repetition, "status": "ok"}
                    # Copy before timing to isolate evaluator compute from preparation.
                    ctx, hyp = context.model_copy(deep=True), context.hypothesis.model_copy(deep=True)
                    started = perf_counter()
                    try:
                        res = registry[name].evaluate(ctx, hyp)
                        row["latency_ms"] = (perf_counter()-started)*1000
                        row["raw"] = res.model_dump(mode="json")
                    except Exception as exc:
                        row.update(status="error", error=f"{type(exc).__name__}: {exc}", latency_ms=(perf_counter()-started)*1000)
                    heads.append(row)
                    stream.write(json.dumps(row)+"\n")
                    stream.flush()
    metrics = summarize(rows, heads)
    (output/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_report(output, manifest, metrics)
    manifest["state"] = "complete"
    save()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT/"validation/config/latency.json"))
    print(run(parser.parse_args().config))
