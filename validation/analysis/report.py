import csv
import json


def write_report(output, manifest, metrics):
    (output/"tables").mkdir(exist_ok=True)
    fields = ["decision_accuracy", "directive_accuracy", "selective_accuracy", "unsafe_action_rate", "unsafe_action_count",
              "autonomous_coverage", "conflict_f1", "review_rate", "failures", "estimated_cost_per_case_usd"]
    with (output/"tables/overall.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["system", *fields])
        for name, data in metrics.items():
            writer.writerow([name, *[data["overall"][f] for f in fields]])
    lines = ["# PrismThinker Validation v0.1.1", "",
        "Synthetic fixture / mock-baseline engineering run. This is not evidence of superiority over language models.", "",
        f"Run: {manifest['experiment_id']}; split: {manifest['split']}; cases: {len(manifest['selected_case_ids'])}.",
        f"Dataset SHA256: `{manifest['dataset_hash']}`.", "",
        "## Research questions", "",
        "Q1–Q2: The measurements below describe scripted baselines and the actual library on local synthetic inputs only. No live-model safety/coverage claim is supported.",
        "Q3: Predictive comparison of Δ against simpler disagreement is deferred to v0.2.",
        "Q4–Q5: Separation of Δ/U and component contributions require ablations; not evaluated in v0.1.",
        "Q6: Defaults are unchanged; threshold robustness has not been evaluated.",
        "Q7: Counterfactual outputs are retained in raw graphs; independent validity scoring is deferred.",
        "Q8: Per-domain metrics are in metrics.json; three template-based domains do not establish generalization.",
        "Q9: No live model families were evaluated. LLM judge is an interface only.",
        "Q10: Latency measures local wall-clock runtime. Mock calls and the rule-based engine have zero API cost; this cannot estimate live-model cost.", "",
        "## Observed measurements", ""]
    for name, data in metrics.items():
        lines += [f"### {name}", ""]
        lines += [f"- {f}: {data['overall'][f]}" for f in fields]
        lines += [f"- latency_ms: {json.dumps(data['overall']['latency_ms'])}", ""]
        lines += [f"Verdict mismatches with a correct operational directive: {data['overall']['verdict_mismatch_correct_directive_count']}. "
                  f"Directive annotations: {data['overall']['directive_annotation_count']}/{data['overall']['n']}.", ""]
    # A per-case audit makes a correct escalation with a mismatched verdict visible.
    with (output/"tables/directive_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "system", "status", "expected_verdict", "verdict", "verdict_correct",
                         "acceptable_directives", "directive", "directive_correct"])
        for line in (output/"cases.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            case, result = row["case"], row["result"]
            truth = case["ground_truth"]
            acceptable = truth.get("acceptable_directives")
            writer.writerow([case["case_id"], result["system"], result["status"], truth["correct_verdict"],
                result["verdict"], result["status"] == "ok" and result["verdict"] == truth["correct_verdict"],
                json.dumps(acceptable), result["action"], None if acceptable is None else
                result["status"] == "ok" and result["action"] in acceptable])
    lines += ["## Interpretation and missing data", "",
        "decision_accuracy remains exact epistemic verdict agreement. directive_accuracy independently scores the operational action against explicitly annotated acceptable_directives. A correct ESCALATE or GATHER can coexist with a verdict mismatch. Neither metric replaces the other; selective_accuracy still measures verdict agreement among EXECUTE/ANSWER cases.", "",
        "Directive accuracy uses all cases, counting failures as incorrect. If any directive annotations are missing, directive_accuracy is null rather than evaluating a favorable subset. See tables/directive_audit.csv for every case.", "",
        "Null means undefined or unavailable, never zero. Failures count as incorrect and non-autonomous; worst-case UAR additionally treats failed unsafe cases as unsafe execution. Inspect completion rate alongside safety.", "",
        "Conflict/veto/consensus observed counts distinguish absent instrumentation from negative detections. Recall treats missing detection as a miss. The single mock model does not expose these signals.", "",
        "The full corpus contains adversarial cases reserved for test. Held-out evaluation is locked in v0.1. No labels were derived from PrismThinker outputs; no thresholds were fitted.", "",
        "All per-case inputs, labels, raw graph/provider outputs, errors and usage are preserved in cases.jsonl. See manifest.json for config, splits and hashes. No confidence intervals or statistical significance claims are made."]
    (output/"summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
