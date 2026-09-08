# Local Scientific Validation v0.2-L

Study: local-v0.2-L-002; 180 cases / 30 scenario families.

Real local models; newly authored synthetic adversarial data frozen before evaluation. No external API calls, no mock substitution. This is not an independently reviewed external benchmark.

Study phase: post-audit syntax-repaired repeat on the same cases; exploratory, not a pristine holdout. Original cases and labels unchanged. Only unsupported typed predicates were translated to the documented grammar after auditing run 001. All model calls are repeated and settings refrozen. No engine, thresholds, labels or baseline prompts were optimized. Prior exposure means this is a post-audit replication, not an untouched holdout.

## Safety versus coverage

![Unsafe-action rate versus autonomous coverage](plots/safety_coverage.png)

Points follow the confidence gates preregistered before execution. Only initially autonomous actions can be escalated by a gate; no threshold was selected on test results. Error bars at the ungated operating point are paired-family bootstrap marginal 95% intervals. Rates are fractions, not percentages.

### single_local

- directive_accuracy: 0.8444444444444444
- unsafe_action_rate: 0.1782178217821782
- unsafe_action_count: 18
- autonomous_coverage: 0.5166666666666667
- selective_accuracy: 0.8064516129032258
- human_review_recall: 0.0
- conflict_precision: None
- conflict_recall: 0.0
- conflict_f1: 0.0
- failures: 0
- latency_ms: {"mean": 947.9507544427179, "p50": 914.433200028725, "p95": 1205.6713548605328, "p99": 1413.4904399816883}

### self_consistency

- directive_accuracy: 0.85
- unsafe_action_rate: 0.15841584158415842
- unsafe_action_count: 16
- autonomous_coverage: 0.5055555555555555
- selective_accuracy: 0.8241758241758241
- human_review_recall: 0.0
- conflict_precision: 0.2
- conflict_recall: 0.25
- conflict_f1: 0.2222222222222222
- failures: 1
- latency_ms: {"mean": 2607.9772322179956, "p50": 2500.997650087811, "p95": 3380.5133150657634, "p99": 3909.0058040316235}

### majority_vote

- directive_accuracy: 0.8166666666666667
- unsafe_action_rate: 0.06930693069306931
- unsafe_action_count: 7
- autonomous_coverage: 0.38333333333333336
- selective_accuracy: 0.8985507246376812
- human_review_recall: 0.4166666666666667
- conflict_precision: 0.102803738317757
- conflict_recall: 0.9166666666666666
- conflict_f1: 0.18487394957983194
- failures: 0
- latency_ms: {"mean": 2450.5514166641256, "p50": 2396.4980500750244, "p95": 2677.1165000740434, "p99": 3084.338730124295}

### llm_judge

- directive_accuracy: 0.8444444444444444
- unsafe_action_rate: 0.16831683168316833
- unsafe_action_count: 17
- autonomous_coverage: 0.5111111111111111
- selective_accuracy: 0.8152173913043478
- human_review_recall: 0.0
- conflict_precision: None
- conflict_recall: 0.0
- conflict_f1: 0.0
- failures: 1
- latency_ms: {"mean": 3483.6815311030173, "p50": 3354.933300288394, "p95": 4082.465875102207, "p99": 4823.901388999078}

### prismthinker

- directive_accuracy: 0.5333333333333333
- unsafe_action_rate: 0.0
- unsafe_action_count: 0
- autonomous_coverage: 0.4388888888888889
- selective_accuracy: 1.0
- human_review_recall: 1.0
- conflict_precision: 0.0
- conflict_recall: 0.0
- conflict_f1: 0.0
- failures: 0
- latency_ms: {"mean": 592.5579833293644, "p50": 590.9282498760149, "p95": 692.2801550128497, "p99": 719.2138480697758}

## Delta usefulness

![Prediction AUROC](plots/prediction_auroc.png)

Targets are common across all predictors. 'unsafe_action' and 'incorrect_autonomous_decision' refer to the same fixed local-majority operational decision; failed reference decisions are missing, not negative. Unsafe eligibility, true conflict and required review use ground truth. Simple signals are separately computed from the same PrismThinker heads and the local-model panel.

Higher scores always mean more risk: majority margin is converted to one-minus-margin before the frozen run. PR-AUC is non-interpolated average precision with ties grouped. Single-class targets return null. All predictors use the same complete-case subset for each target; missing counts are in prediction.json. These are point estimates, not statistically significant superiority claims.

## Reproducibility and limits

freeze.json contains model digests, runtime, full config, source/dataset/prompt hashes, and the untouched engine defaults. calls.jsonl retains raw requests/responses and interrupted/failed calls. Logical method latency/token counts include shared dependencies; physical model calls are reused to avoid redundant inference. Judge costs include its candidate panel.

Self-consistency uses three temperature-0.6 samples; panel models are Qwen3 4B, Llama3.2 3B and Gemma3 4B. Qwen thinking is explicitly disabled for this fixed non-thinking protocol; judge temperature is zero. This is a hardware-constrained family comparison, not a test of the strongest available reasoning models.

The corpus uses 30 authored rule families, six cases each, rotating across three domains. It is independent of observed outputs but authored by the same project assistant and unreviewed. Typed rules and normalized facts are shared with all models. Their construction is not learned or costed; findings apply to supplied structured input, not raw-text extraction in production.

Bootstrap intervals resample whole families (10,000 draws); repeated variants are not independent trials. Zero observed errors do not establish zero population risk. No test case, timeout, invalid JSON or unfavorable domain is dropped from primary metrics. Failed calls do not act; inspect worst-case UAR and completion alongside measured UAR.

API cost is zero; electricity, hardware depreciation and operator time are not estimated. Model load costs are included when observed, and sequential wall-time measurements are machine-specific. Do not compare these numbers to differently provisioned production systems.
