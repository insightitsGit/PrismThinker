"""Retrospective diagnosis of saved outputs; no inference or benchmark rewriting."""
import json
from collections import Counter
from pathlib import Path


def diagnose(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["result"]["system"] == "prismthinker"]
    groups = {}
    components = Counter()
    policy_correct = 0
    for row in rows:
        case, result = row["case"], row["result"]
        graph = result["raw"]
        expected = case["ground_truth"]["acceptable_directives"][0]
        group = groups.setdefault(expected, {"count": 0, "head_patterns": Counter(),
            "rationales": Counter(), "deltas": set(), "examples": []})
        group["count"] += 1
        group["head_patterns"][str(sorted((k, v["verdict"]) for k,v in graph["evaluators"].items()))] += 1
        group["rationales"][graph["recommended_rationale"]] += 1
        group["deltas"].add(result["delta"])
        if len(group["examples"]) < 2:
            group["examples"].append(case["case_id"])
        for pair in graph.get("critical_conflicts", []):
            for name, value in pair["components"].items():
                components[name] += int(value != 0)
        policy = graph["evaluators"]["policy"]["verdict"]
        action = {"approve": "EXECUTE", "reject": "REFUSE", "caution": "ESCALATE", "undetermined": "GATHER"}[policy]
        policy_correct += action == expected
    for group in groups.values():
        group["deltas"] = sorted(group["deltas"])
    return {"phase": "retrospective diagnosis, not held-out validation",
        "source": str(path), "cases": len(rows),
        "cases_with_evidence": sum(bool(r["case"]["evidence"]) for r in rows),
        "groups": groups, "nonzero_critical_pair_components": components,
        "retrospective_policy_only_directive_correct": policy_correct,
        "policy_only_warning": "Post-hoc ablation of saved heads, not a preregistered baseline or a safe production controller."}


if __name__ == "__main__":
    import sys
    print(json.dumps(diagnose(sys.argv[1]), indent=2))
