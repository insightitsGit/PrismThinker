"""Replay inspected development cases; never a fresh scientific validation."""
import hashlib
import json
from pathlib import Path

from validation.baselines.eligibility import EligibilityBaseline
from validation.datasets.splitting import load_cases
from validation.metrics import calculate
from validation.prismthinker_eval.adapter import PrismThinkerAdapter
from validation.experiments.local_models import source_hash


def run(dataset, output):
    output = Path(output)
    if output.exists():
        raise ValueError("refusing to overwrite existing regression results")
    cases = load_cases(Path(dataset))
    implementation_hash = source_hash()
    methods = [PrismThinkerAdapter(), EligibilityBaseline()]
    results = {m.name: [] for m in methods}
    records = []
    for i, case in enumerate(cases):
        for method in methods:
            result = method.evaluate(case.system_input())
            results[method.name].append(result)
            records.append({"case_id": case.case_id, "method": method.name,
                "expected": [a.value for a in case.ground_truth.acceptable_directives],
                "action": result.action.value, "conflict": result.conflict,
                "eligibility": result.raw.get("eligibility"),
                "conflict_signals": result.raw.get("conflict_signals"),
                "aligned_delta": result.raw.get("aligned_delta")})
        if (i+1) % 30 == 0:
            print(f"Development regression: {i+1}/{len(cases)}", flush=True)
    if implementation_hash != source_hash():
        raise ValueError("source changed during regression")
    output.write_text(json.dumps({
        "phase": "development regression on previously inspected cases, not held-out validation",
        "source_hash": implementation_hash,
        "dataset_sha256": hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
        "methods": {name: calculate(cases, rs) for name, rs in results.items()},
        "warning": "Eligibility-only shares gate code. This is an ablation, not independent validation. No new model calls.",
        "records": records,
    }, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    import sys
    print(run(*sys.argv[1:]))
