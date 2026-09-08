# Fresh v1.2 local comparison — preregistered protocol

Study local-v1.2-fresh-001 evaluates 180 new cases in 30 authored families, six
variants each, equally distributed across agent execution, policy/compliance and
evidence reasoning. IDs, scenarios and prompts are new; no old case is reused.
Mechanisms can overlap development tests. The author knows the v1.2 design. This
is a fresh evaluation-only corpus, **not independently curated or expert reviewed**.

The standalone generator uses ordinary Python oracles for fictional operational
requirements. It does not import or run PrismThinker or language models. Only schema,
predicate syntax, identity/label consistency and selected hand-checked oracle controls
are tested before freezing. No case is selected, relabeled or discarded based on
system performance. Freeze resolves model/source/prompt/corpus/config hashes before
any evaluation. All raw outcomes, failures and unfavorable families are retained.

## Coverage

Cases cover scoped/temporal claims, identity and attribute separation, superseded
and unverified records, unknown authority, conflicting permissions, independent and
dependent blockers, explicit hard stops, measured capacity/delay, multiple service
constraints, and signed causal paths. Some requirements are expressed as objectives
or graphs rather than fully compiled policy predicates; this tests whether heads add
value over the gate. Legacy supersession metadata is deliberately included as an
interoperability challenge; it must not be silently removed if unsupported.

Every method sees the same prose, typed input and normalized facts. Labels and metadata
remain hidden. Representation construction and text extraction are outside the measured
system. Explicit missing signs, contradictory evidence and absent observations are
intentional cases; malformed predicate syntax is rejected before freezing.

## Methods and execution

Qwen3 4B single response; three-sample Qwen self-consistency; strict majority across
Qwen3 4B, Llama3.2 3B and Gemma3 4B; Qwen judge of the panel; PrismThinker v1.2 default
isolation; and eligibility-only. The last baseline shares gate implementation and
removes voting/Delta, so it is an ablation, not independent validation.

The same bounded non-thinking settings as prior runs are retained: temperatures
0.6/0 for samples/judge, 256 output tokens, 8192 context, recorded seeds and model
digests. No mocks, external API fees, automatic retries or outcome-dependent reruns.
Expected physical workload: 1,080 model calls, 180 engine and 180 gate evaluations.
Logical latency/token totals include shared dependencies. This is not a comparison
to stronger reasoning models or production hardware.

## Primary and supplemental measures

Primary: unsafe executions / unsafe cases, autonomous coverage, selective accuracy,
directive accuracy, review recall, semantic conflict precision/recall/F1, failures
and latency. Confidence gates are fixed at 0, .25, .5, .75, .9, .95, 1 before inference.
Ungated comparisons use 10,000 paired family-bootstrap samples and 95% intervals.
The safety-versus-coverage curve remains the main figure.

For this new study, conflict means material evidence or policy-authority contradiction.
The engine uses the union of its typed semantic flags; models receive the same
definition in the task. A voting tie, utility-policy opposition or missing data alone
is not a semantic conflict. This differs from historical broad flags, so historical
F1 values must not be compared as if definitions were unchanged.

Supplemental metrics include refusal recall/precision and unnecessary review over
all answerable cases not requiring human review, including known refusals. Missing
positive detections count as misses. Typed material and authority metrics are
available only for the engine/gate; models emit their semantic union.

Delta prediction analysis keeps the same fixed-majority reference for actual unsafe
and incorrect autonomous action. Other targets are unsafe eligibility, true semantic
conflict and review need. Compare original Delta, all five component maxima, full-head
and determinate-only disagreement signals, and local-panel signals. A second common
cohort adds aligned shadow ratio, aligned binary contradiction and contradiction count.
All predictors within a cohort use identical complete cases. Report exclusions;
no-comparison null scores are never replaced by zero. PR-AUC is average precision;
single-class targets return null. No test-time score inversion, fitted thresholds or
significance claims from AUC point estimates. Aligned and original Delta do not change
production formulas during the run.

## Reproduce

```bash
python -m validation.datasets.build_fresh_v12
python -m validation.experiments.local_models freeze validation/config/local_models_fresh_v12.json
python -m validation.experiments.local_models run validation/reports/local-v1.2-fresh-001
```

Freeze refuses an existing directory. Resume the same run command if interrupted;
completed calls are reused, interrupted calls remain failures. Fresh data, frozen
snapshots, raw calls, numeric reports, paired intervals and plots are preserved.
Any issue discovered after freezing must be audited openly; do not patch and continue
under the same study identity.
