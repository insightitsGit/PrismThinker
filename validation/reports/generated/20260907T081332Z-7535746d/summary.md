# PrismThinker Validation v0.1.1

Synthetic fixture / mock-baseline engineering run. This is not evidence of superiority over language models.

Run: 20260907T081332Z-7535746d; split: validation; cases: 12.
Dataset SHA256: `f595198cd19c1e5b0b7f97e6b4e7a407c4f8efed7b76542effcf75c2d225af6a`.

## Research questions

Q1–Q2: The measurements below describe scripted baselines and the actual library on local synthetic inputs only. No live-model safety/coverage claim is supported.
Q3: Predictive comparison of Δ against simpler disagreement is deferred to v0.2.
Q4–Q5: Separation of Δ/U and component contributions require ablations; not evaluated in v0.1.
Q6: Defaults are unchanged; threshold robustness has not been evaluated.
Q7: Counterfactual outputs are retained in raw graphs; independent validity scoring is deferred.
Q8: Per-domain metrics are in metrics.json; three template-based domains do not establish generalization.
Q9: No live model families were evaluated. LLM judge is an interface only.
Q10: Latency measures local wall-clock runtime. Mock calls and the rule-based engine have zero API cost; this cannot estimate live-model cost.

## Observed measurements

### single_model_mock

- decision_accuracy: 1.0
- directive_accuracy: 1.0
- selective_accuracy: 1.0
- unsafe_action_rate: 0.0
- unsafe_action_count: 0
- autonomous_coverage: 0.5
- conflict_f1: 0.0
- review_rate: 0.5
- failures: 0
- estimated_cost_per_case_usd: 0.0
- latency_ms: {"mean": 0.1668416274090608, "p50": 0.1330000814050436, "p95": 0.30571994138881553, "p99": 0.3838640241883696}

Verdict mismatches with a correct operational directive: 0. Directive annotations: 12/12.

### majority_vote_mock

- decision_accuracy: 1.0
- directive_accuracy: 1.0
- selective_accuracy: 1.0
- unsafe_action_rate: 0.0
- unsafe_action_count: 0
- autonomous_coverage: 0.5
- conflict_f1: 0.0
- review_rate: 0.5
- failures: 0
- estimated_cost_per_case_usd: 0.0
- latency_ms: {"mean": 0.1876916503533721, "p50": 0.18544995691627264, "p95": 0.21625508088618517, "p99": 0.22325108293443918}

Verdict mismatches with a correct operational directive: 0. Directive annotations: 12/12.

### prismthinker

- decision_accuracy: 0.5
- directive_accuracy: 1.0
- selective_accuracy: 1.0
- unsafe_action_rate: 0.0
- unsafe_action_count: 0
- autonomous_coverage: 0.5
- conflict_f1: 1.0
- review_rate: 0.5
- failures: 0
- estimated_cost_per_case_usd: 0.0
- latency_ms: {"mean": 533.4338333341293, "p50": 554.9173499457538, "p95": 598.034525080584, "p99": 603.2760250894353}

Verdict mismatches with a correct operational directive: 6. Directive annotations: 12/12.

## Interpretation and missing data

decision_accuracy remains exact epistemic verdict agreement. directive_accuracy independently scores the operational action against explicitly annotated acceptable_directives. A correct ESCALATE or GATHER can coexist with a verdict mismatch. Neither metric replaces the other; selective_accuracy still measures verdict agreement among EXECUTE/ANSWER cases.

Directive accuracy uses all cases, counting failures as incorrect. If any directive annotations are missing, directive_accuracy is null rather than evaluating a favorable subset. See tables/directive_audit.csv for every case.

Null means undefined or unavailable, never zero. Failures count as incorrect and non-autonomous; worst-case UAR additionally treats failed unsafe cases as unsafe execution. Inspect completion rate alongside safety.

Conflict/veto/consensus observed counts distinguish absent instrumentation from negative detections. Recall treats missing detection as a miss. The single mock model does not expose these signals.

The full corpus contains adversarial cases reserved for test. Held-out evaluation is locked in v0.1. No labels were derived from PrismThinker outputs; no thresholds were fitted.

All per-case inputs, labels, raw graph/provider outputs, errors and usage are preserved in cases.jsonl. See manifest.json for config, splits and hashes. No confidence intervals or statistical significance claims are made.
