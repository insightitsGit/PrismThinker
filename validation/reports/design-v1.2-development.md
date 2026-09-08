# v1.2 development regression

The approved eligibility gate, typed conflict outputs and aligned shadow score are
implemented. [Migration and API contract](../../docs/eligibility-v1.2.md).

Replaying the 180 previously inspected cases produced 180 correct operational
directives for both PrismThinker and the shared eligibility-only baseline. Both had
zero unsafe executions, 43.9% autonomous coverage and 100% selective accuracy.
The 84 known prohibitions now refuse instead of escalating. No new model calls
were made and no historical run was overwritten.

The engine's broad legacy conflict F1 is 0.222; the baseline's is zero. The old
corpus has no aligned claims and is not a test of the new typed conflict schema.
Operational correctness must not be confused with semantic conflict detection.
The shadow score is null without comparable claims, as intended.

This is development/regression evidence, **not held-out scientific validation**.
The shared baseline matching the full engine means this corpus still does not
demonstrate incremental value from evaluator voting or Delta. A fresh independent
holdout and prospectively defined ablations remain necessary.

Verification: 225 tests passed; required isolation and predicate suites each achieved
100% coverage. Wheel and source distribution built successfully; both passed
`twine check`. Nothing was published.

[Machine-readable results and source/dataset hashes](design-v1.2-development.json).

Reproduce with a new output path:

```bash
python -m validation.experiments.design_regression validation/datasets/processed/adversarial-v0.2-L-syntax2.jsonl validation/reports/design-regression-new.json
```
