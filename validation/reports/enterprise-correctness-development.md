# Enterprise correctness development replay

Source hash: `6848f7ffb204e3848bc7e6da57f433b3d178d78cac056d614f0e040ab6d6a769`.

This reuses all 180 inspected cases from `local-v1.2-fresh-001`. It makes no
new model calls. The original frozen dataset and results are unchanged.
[Machine-readable results](enterprise-correctness-development.json) include the
dataset hash, source hash and every predicted directive for both methods.

Both the full engine and shared eligibility-only ablation now produce:

- 180/180 correct directives; no evaluation failures.
- 0 unsafe executions among 93 unsafe cases.
- 87/180 executions (48.3% coverage), all correct.
- All 41 required escalations, with no unnecessary escalations.

The original full-engine run had 153/180 correct directives, 6 unsafe executions
and the same 87/180 execution coverage. The corrected engine no longer executes
those unsafe cases and releases the six valid superseded-evidence cases.

These results establish regression repair only. The cases informed the changes,
the baseline shares gate code, and neither result establishes independent
generalization or incremental value from the contradiction score.

## Measurement limits

This older development harness retains legacy graph-verdict and broad-conflict
metrics. Its engine verdict accuracy is 92/180, with 88 cases whose directive is
correct despite a different legacy verdict. Integrations must consume the final
directive through `to_chorusgraph`, not infer execution from the graph verdict.
Engine broad-conflict F1 is 0.686; this includes evaluator disagreement and is
not directly comparable with the gate's semantic-conflict F1 of 1.0.

Engine latency is not instrumented in this harness; the JSON's zero latency
fields are placeholders, not a performance measurement. Use the dedicated
latency harness before making operational claims.

See [behavior changes and remaining production gates](../../docs/enterprise-hardening.md).
