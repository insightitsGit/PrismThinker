# Local validation findings: post-audit repeat

This completed experiment compares five methods on 180 authored adversarial cases
in 30 scenario families, using 1,080 real Ollama calls across Qwen3 4B, Llama3.2 3B
and Gemma3 4B, plus 180 PrismThinker evaluations. See the [full report](summary.md),
[numeric comparison](tables/comparison.csv) and [protocol](../../LOCAL_SCIENCE.md).

**This is exploratory comparative evidence, not a pristine held-out result.**
The [original run audit](../local-v0.2-L-001/AUDIT.md) found unsupported typed
predicate syntax in 72 cases. All 41 unsafe PrismThinker executions in that run
occurred in those cases. The raw results and exact source snapshot are retained.
The repeat repairs the input translation, preserves labels and settings, and
repeats every model call. Engine logic and thresholds were not tuned. The original
fail-open behavior on malformed policy predicates remains an unresolved library
finding; repairing the benchmark input does not repair that behavior.

## Safety and coverage

At the ungated operating point, unsafe executions out of 101 unsafe cases were
18 for the single model, 16 for self-consistency, 7 for majority vote, 17 for the
judge and **0 for PrismThinker**. PrismThinker executed 79 of 180 cases (43.9%
coverage), with 100% selective accuracy. Majority vote had 38.3% coverage and
89.9% selective accuracy.

The paired 10,000-draw family bootstrap estimates PrismThinker minus majority
vote unsafe-action rate at -6.93 percentage points (95% interval -13.46 to -1.94).
The coverage difference is +5.56 points (-1.67 to +13.33); its interval includes
zero. These results support a favorable observed operating point on this corpus,
not an established general coverage improvement or zero population risk.

![Safety versus coverage](plots/safety_coverage.png)

## Operational and conflict weaknesses

PrismThinker escalated all 84 cases labeled REFUSE. It correctly executed 79,
gathered evidence in 5 and escalated the 12 mandatory-review cases. This yields
only **53.3% directive accuracy**, despite 100% review recall and selective accuracy.
Escalation avoids unsafe execution but still imposes unnecessary human work.

Conflict precision, recall and F1 were all zero. The engine's conflict flags did
not identify the labeled material evidence conflicts. Operational escalation and
successful conflict detection must therefore not be treated as equivalent.

## Delta usefulness

On the common 180-case prediction cohort, Delta predicts unsafe eligibility well
(AUROC 0.975, average precision 0.978). It does not reliably predict true conflict
(AUROC 0.500), or the fixed majority reference's seven unsafe executions (0.549).
Local-panel confidence spread scores 0.778 on conflict; local binary disagreement
scores 0.637 on reference unsafe execution. There is no consistent Delta win.

The frozen same-head one-minus-majority-margin has AUROC 0.000 for unsafe
eligibility: its ordering is perfectly reversed. This is evidence that signal
orientation matters, not evidence that Delta uniquely contains predictive
information. No scores were inverted or thresholds selected after evaluation.
Simple definitions include UNDETERMINED votes; abstention-aware alternatives need
a separate preregistered experiment. Conflict and required-review labels coincide
here, as do the two reference-action error targets; they are not independent wins.

## Verification and limits

The corrected run completed with zero predicate parsing errors and zero engine
errors. Two truncated model responses remain recorded as failures. The full test
suite passed 185 tests. Both runs preserve frozen hashes, exact source snapshots,
raw requests/responses, case outputs and machine-readable metrics.

The same project assistant authored this synthetic, structured-rule corpus; there
was no independent expert review. The 180 variants are only 30 scenario families.
All systems receive normalized typed facts/rules, whose construction is not
evaluated. The three compact model families use a bounded non-thinking protocol.
Latency is sequential, machine-specific and includes logical dependencies.

A stronger next experiment requires an independently curated, freshly frozen
holdout, preregistered abstention/orientation ablations and stronger local reasoning
baselines where hardware permits. These results do not justify a numerical
scientific rating or a general superiority claim.
