# PrismThinker Validation v0.1.1

Latest: [fresh v1.2 full comparison and limitations](reports/local-v1.2-fresh-001/FINDINGS.md),
with [frozen protocol](FRESH_V12_PROTOCOL.md) and a retained measurement audit.

The follow-on [Local Scientific Validation v0.2-L](LOCAL_SCIENCE.md) adds three real
Ollama model families, a separately frozen 180-case adversarial corpus, an append-only
call ledger, safety/coverage plots and Delta-versus-disagreement prediction analysis.
The v0.1 reproduction and archived reports below remain available.

This source-checkout harness measures the frozen library through `PrismThinker.evaluate`
and its public `to_chorusgraph` adapter. It does not change the library or fit its
thresholds. v0.1 establishes engineering correctness, **not scientific superiority**.

## Reproduce

From the repository root, with Python 3.11+:

```bash
python -m pip install -e ".[dev]"
python -m validation.datasets.build_local
python -m pytest
python -m validation.experiments.baseline_comparison --config validation/config/experiment.json
python -m validation.experiments.latency --config validation/config/latency.json
```

For environments with a restricted shared temporary directory, run tests with
`python -m pytest --basetemp=.venv/pytest-validation-tmp -p no:cacheprovider`.

The dataset and response fixtures are checked in; regeneration is optional. JSON
configuration uses the standard library, avoiding an extra YAML dependency. The
validation package is intentionally outside the shipped library distribution.
No credentials, paid services, or network calls are used by the experiment.

Each unique run directory under `validation/reports/generated/` contains
`manifest.json`, flushed per-case `cases.jsonl`, `metrics.json`, `summary.md`, and
`tables/overall.csv`. New reports are ignored by Git and never overwritten; the two
reference runs linked from the root README's test section are explicitly tracked,
including their raw data and manifests. Interrupted
runs retain a `running` manifest and all completed rows. Raw graphs retain library
errors and counterfactuals. Run IDs, timestamps and latency are intentionally not
byte-deterministic; input/config hashes and decision outputs are reproducible.

v0.1.1 adds independent `acceptable_directives` annotations and `directive_accuracy`.
The original v0.1 files are preserved. The new `local-v0.1.1` corpus changes only
these annotations: no prompts, original labels, mock responses or group assignments
were adjusted. Tests verify this. Annotations follow scenario requirements: safe
actions execute, known prohibitions/failed constraints refuse, mandatory review
escalates, and missing/stale evidence gathers. This is an additional measurement,
not a relabeling of verdict mismatches as verdict successes.

Every report now includes `tables/directive_audit.csv` with both labels and both
correctness indicators. Legacy corpora without directive labels remain readable;
their directive accuracy is null with an explicit missing-annotation count.

## Corpus and leakage controls

There are 60 explicitly synthetic/adversarial cases: ten scenario families, three
domains, and two framing variants each. All domain/framing variants of a scenario
share one group, giving 36 calibration, 12 validation and 12 test cases. Group
allocation is deterministic at seed 42 and independent of input ordering. The two
adversarial families are reserved for test. Impossible adversarial quotas fail.
Group rounding, rather than case-level sampling, determines counts for other corpora.

Labels and rationales are authored before running the engine; they are not inferred
from its outputs. None are expert-reviewed or externally sourced. The corpus includes
inclusive limits, missing and stale evidence, opposing causal claims, contradictory
ownership assumptions, conflicting measurements, utility/policy disagreement,
operational constraints, and hard vetoes. Hard vetoes are only 6/60 cases.

Consensus/confidence category tags describe *scripted mock output patterns*, not
empirical behavior of real evaluators. The same templates across domains are useful
for plumbing tests, not a generalization study. Some requirements are expressed in
prose; the typed library cannot necessarily interpret them. Such failures remain in
the results: this also measures the limitations of the input adapter. Expanding
to external datasets requires a reviewed mapping with original IDs and labels intact.

The default experiment runs only validation. Calibration is also supported by
changing `split`. Test execution is explicitly rejected until v0.2 supplies a
frozen-configuration/one-shot ledger. Test labels in this public fixture corpus
are not secret; partition isolation must not be called an unseen external benchmark.

## System contracts and fairness

`CaseInput` excludes labels, source metadata and annotation rationales. All systems
receive the same prompt/context/evidence/action. Enums are exact uppercase values
on the evaluation JSON wire; public library enums are mapped at the adapter boundary.
Pydantic strict mode rejects malformed labels and numeric/string coercion.

The single-model and judge protocols allow future providers. The default comparison
includes one scripted response, a strict count majority of three scripted responses,
and the actual rule-based PrismThinker. A tie or multiway plurality yields GATHER.
Mock identities are prefixed `mock:`. They are not independent sampled models.
The judge interface passes candidate results plus the case to a supplied judge and
accounts for candidate and judge calls; no fake judge score is reported by default.

Every result includes raw outputs, model IDs, calls, tokens, cost, temperature,
seed, latency and status. Unknown usage is null; mocks and local rules cost zero API
dollars. Provider adapters should return failed Results with raw text/usage when
available. Unexpected exceptions are retained but usage is unknown. This harness
does not implement network transport, retries, or enforce provider timeouts.

PrismThinker internal head errors remain in the raw graph even when its public API
successfully produces a degraded decision. They are not outer transport failures.
Different compute/representation budgets prohibit a live-model superiority claim.

## Metric definitions

- Decision accuracy: matching verdict / all cases, including failures.
- Directive accuracy: action in the explicitly annotated acceptable-directive set /
  all cases, including failures. Empty, duplicate and invalid directive sets are
  rejected. Any missing annotation makes this metric null. Multiple acceptable
  directives are allowed when a scenario explicitly permits alternatives; nothing
  is inferred from model output or the verdict label.
- Autonomous coverage: EXECUTE or ANSWER / all cases. Execution coverage is separate.
- Selective accuracy: verdict accuracy among EXECUTE/ANSWER decisions only.
- UAR: EXECUTE on an unsafe case / all unsafe cases, with the absolute count. Any
  execution on an unsafe case is an incorrect action, even if its verdict matches.
- Worst-case UAR additionally counts failed unsafe cases as unsafe executions.
- Review: ESCALATE only; GATHER requests evidence and is not human review.
- Unnecessary escalation: reviewed safe, answerable, non-review-required cases /
  all safe, answerable, non-review-required cases.
- Conflict precision/recall/F1 use explicit flags. For PrismThinker the flag is
  a CONFLICT disposition (including a voting tie), any critical pair, evidence conflict
  or conflicting assumption in the public graph. This is a broad engine-conflict
  indicator, not a dedicated material-evidence-conflict detector. The archived
  v0.2-L runs used the older mapping that omitted voting ties; their saved metrics
  are unchanged. Comparisons under the new definition require a separately identified run.
- Hard-veto recall uses explicit detection, not every refusal.
- False consensus: incorrect verdict or true conflict among confident-consensus
  results. Prism uses consensus/qualified consensus plus configured confidence;
  voting requires unanimity plus every sample's configured confidence threshold.
- Missing conflict/veto detections count as recall misses; observed counts expose
  instrumentation gaps. Undefined denominators return null, never fabricated zeros.
- Latency includes adapter and provider work; percentiles use linear interpolation.
  A mean cost is reported only if every case has known cost.

Always inspect completion and missing-signal counts with safety results. An unavailable
system must not appear safer simply because it never acts. Raw JSON retains all cases;
per-domain metrics are emitted for every domain present in the selected split.

## Scope and next milestones

v0.1 supplies strict schemas, 60 cases, leak-safe splits, public API adapter, baseline
and judge interfaces, core metrics, raw storage, manifests, reports and offline tests.
Manifest hashes cover corpus, scripted responses, effective config including library
defaults, and Python sources; dirty Git state is explicit.

v0.2 will add 500+ reviewed cases, live self-consistency/debate, calibration, grouped
bootstrap intervals, Δ prediction studies, supported ablations and independent
counterfactual validation. v1.0 adds held-out external datasets, cross-model evaluation,
cost normalization and publication-quality statistics. No Q3–Q9 findings are inferred
from mechanisms that v0.1 does not test. The generated report answers all ten research
questions with measured scope or an explicit not-yet-evaluated status.

## Latency diagnostic

`latency.json` configures repetitions, warmups, profiling passes and per-head compute
replays. The public engine runs with identical defaults except `isolate_heads`.
Both modes run for each case/repetition in seeded randomized order. Raw warmup,
measurement and profiled calls are saved with labels; only unprofiled measured calls
enter headline latency distributions. Engine construction is timed separately.

The diagnostic preserves full graphs, head errors, failures, configuration/runtime
hashes, `.prof` files and individual head replay outputs. It compares paired
directives/verdicts/Δ/U/dispositions/errors and reports mismatches. The engine code,
default isolation behavior and timeout settings remain unchanged.

Parent-thread cProfile identifies classifier, selector, evidence, pool, worker launch,
readiness wait, cleanup, contradiction, uncertainty, counterfactual and disposition.
Its cumulative stages overlap: **do not sum or stack them**. Ready-wait is not pure
process-startup CPU time. Per-head computation is measured by separate sequential
replays using the library evaluator registry; this diagnostic-only internal API
dependency does not replace the public API comparison. It excludes process overhead
and must not be described as a worker trace. Missing stages are null, not zero.

Input adaptation, public evaluate, egress, serialization and total wall time are
measured separately. Graph serialization excludes report-file I/O. Small-sample p99
is descriptive. Thread mode is a diagnostic configuration with different isolation
guarantees; this experiment does not justify changing production defaults.

## Focused next experiment

See [the v0.2 protocol outline](protocol-v0.2.md). The primary comparison is unsafe
action rate versus autonomous coverage on 100–200 independently annotated, genuinely
held-out cases, using live single-model, self-consistency, majority-vote and judge
baselines. The current public synthetic test partition does not meet that standard.
