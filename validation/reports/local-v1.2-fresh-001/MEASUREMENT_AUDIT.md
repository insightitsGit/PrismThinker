# Post-run measurement audit

The frozen run completed with 1,080 real model calls, 180 engine evaluations and
180 gate-only evaluations. There were 18 truncated model responses, zero engine
runtime errors, zero engine predicate-error messages and no missing model usage.
No source, dataset, prompt or engine setting was changed during evaluation.

## Aggregated conflict flag mismatch

`validation/experiments/local_models.py:aggregate` retains a legacy conflict flag:
`len(verdicts) > 1`. Thus self-consistency and majority vote measure vote disagreement,
although the new study intended semantic evidence/authority conflict. Single-model
and judge outputs use the requested semantic definition; engine/gate flags use typed
semantic outputs. The two aggregated methods' frozen conflict precision/recall/F1
are **not directly comparable under that semantic definition**.

This does not alter operational directives, unsafe-action rates, coverage, selective
accuracy, latency, paired action comparisons or prediction targets. The original
calls, cases, metrics and plots are retained. This is a reporting defect, not an
input-predicate defect or a reason to rerun inference until results improve.

An explicitly post-run correction is saved in
[semantic_vote_reanalysis.json](semantic_vote_reanalysis.json). It takes strict
majority of the saved samples' semantic conflict booleans; incomplete panels remain
missing detections, and missing positive detections count as recall misses. It does
not change actions or call models. The file records every corrected flag and the
raw case file hash so the calculation is independently checkable.

Under that post-run rule, self-consistency semantic conflict F1 is 0.140 and majority
vote F1 is 0.378. These are labeled reanalyses, not presented as frozen primary
measurements. Engine/gate semantic F1 is 0.921 in the original measurement.

## Presentation

The generic generated summary retains its harness title v0.2-L; the actual study ID
is local-v1.2-fresh-001. The findings document uses the correct study name. A second
aligned-score figure spaces overlapping labels; its values are unchanged and the
original figure is preserved.

## Limits unaffected by the audit

The cases are fresh but assistant-authored after knowing the design, not externally
reviewed. The aligned-comparable prediction cohort contains 51 cases; its perfect
conflict AUROC is also achieved by simple aligned binary/count signals. It does not
establish a unique benefit from the new score or performance on raw-text extraction.
