# Why the local results are mixed, and what to change

This is a source-level diagnosis and retrospective analysis of run 002, not a new
validation result. Reproduce the counts with `python -m validation.analysis.root_cause
validation/reports/local-v0.2-L-002/cases.jsonl` (one command).
The [machine-readable diagnosis](root-cause-v0.2-L.json) preserves example case IDs.
The original runs remain unchanged.

## 1. Confirmed implementation bug: incomplete policy checks approve

In `src/prismthinker/evaluators/policy.py`, predicate errors and missing paths were
skipped, then `if permission_only or rules` returned APPROVE because the rule list
was nonempty. A matching permission could also mask an unevaluated prohibition.
The original malformed run exposed this, and all five missing-data cases in run
002 also have an incorrect policy APPROVE. Formal abstention happened to protect
those five cases; this is not a dependable policy boundary.

Fixed locally: unknown checks now return UNDETERMINED rather than APPROVE.
`REASON_POLICY_INCOMPLETE` also requires review even when other heads approve.
Proven rejection or caution is retained, and a known hard veto still refuses.
Tests cover malformed/missing predicates, mixed permission plus unknown rules,
other-head approval, known denial, and the public tool envelope. This deliberately
does not treat malformed input as a proven policy violation.

## 2. Design issue: the heads answer different questions but vote together

All 84 expected refusals have formal APPROVE and policy REJECT. Every other head
abstains. Formal's claim is "state is structurally valid"; policy's is "this is
prohibited." Both can be true simultaneously. Turning them into opposite votes
about the action creates a false dispute, followed by escalation.

Only policy and formal are determined anywhere in this corpus; this is not a
substantive five-perspective reasoning test. A retrospective mapping of the saved
policy verdict alone gives 175/180 correct directives, versus 96/180 for the full
engine. Its five errors are the incomplete checks above. This is an ablation,
not a validated replacement controller; it shows that a deterministic rule-engine
baseline is essential in the next study.

Recommended design: separate action eligibility from epistemic agreement. An
authoritative, applicable BLOCK is a non-compensatory execution constraint; utility
or structural validity cannot outvote it. A definite blocker should support REFUSE;
unresolved authority, applicability or evidence should support ESCALATE/GATHER.
Keep review metadata separate from the action directive, so a refusal may still
be audited. Preserve HARD_VETO as an explicitly distinct authority mechanism.

Implement this with typed blocker records carrying rule ID, authority, applicability,
evaluation status and fact provenance. Do not merely special-case the head name or
rename every BLOCK as HARD_VETO. Existing tests explicitly expect the current
conflict lattice: this change needs a documented contract migration, not a hidden
threshold adjustment. Validate policy/utility opposition, conflicting authorities,
missing facts and independent prohibitions before running a fresh benchmark.

## 3. Benchmark and output mismatch: zero conflict F1 is not the full story

All 180 cases have `evidence=[]`. The 12 positive conflict cases encode opposing
records as differently named structured facts and a caution policy. The evidence
detector in `core/evidence.py` compares EvidenceItems, shared numeric claim keys,
timestamps and explicit negation metadata; those inputs were never provided.
It cannot infer relationships between arbitrary fact names.

All 12 positives reach `lattice.tie` (formal APPROVE versus policy CAUTION), but
the validation adapter reports conflict only from critical pairs, evidence conflicts
or conflicting assumptions. It omits conflict dispositions caused by ties. Their
Delta is below the critical-pair threshold, so the reported flag is false. Conversely,
all 84 known prohibitions generate critical pairs and become false-positive material
conflicts. Simply adding tie dispositions to the flag would improve recall while
retaining the semantic mismatch and false positives.

Recommended design: distinguish `material_evidence_conflict`, `policy_authority_conflict`,
`evaluator_disagreement` and `decision_tie`. Give normalized claims a proposition key,
subject, value/polarity, time scope, source and authority; compare only aligned claims.
Benchmark structured-input reasoning separately from raw-text claim extraction.
Use true contradictions plus complementary facts, temporal supersession, different
subjects, missing records and malicious quoted instructions as negative controls.
Do not retrospectively add gold conflict flags to evidence and call it discovery.

## 4. Delta is mostly a policy-disagreement proxy in this experiment

Across all 84 critical pairs, the only nonzero components are conclusion and premise
disagreement. Evidence, constraint and assumption conflict components are all zero.
Safe executions all have Delta 0.1; true conflicts have about 0.235-0.242; known
denials have about 0.400-0.433. This ordering explains high unsafe-eligibility AUROC
and poor conflict discrimination without establishing multidimensional value.

Premise Jaccard distance treats different information as conflict, even if complementary.
One determined head against an abstaining head can still contribute premise distance.
Taking the maximum over pairs amplifies one noisy or irrelevant comparison. These
are design limitations to test, not grounds for selecting weights on these cases.

Recommended redesign: only compare claims answering the same proposition; represent
contradiction, information diversity and missingness separately. Record eligible
comparison count and evidence sufficiency. Compare aligned conclusion disagreement,
typed conflict counts, Delta components and full Delta with preregistered ablations.
Report discrimination separately for eligibility, real conflict and operational
error. Confidence averaging is not calibrated safety probability and should not be
marketed as one.

## Next implementation and evaluation sequence

1. Ship the incomplete-policy correctness fix after regression checks. Keep historical
   reports and source snapshots, since their measurements describe the old engine.
2. Specify and implement an eligibility gate with explicit blocker/unknown provenance.
   Acceptance: structural approval cannot override an applicable prohibition; unknown
   policy cannot permit execution; independently proven refusal remains available.
3. Add aligned evidence/authority claim types and distinct conflict outputs. Acceptance:
   contradictions are detected without flagging compatible or superseded records.
4. Add a plain deterministic policy/constraint controller to the baselines, plus
   abstention-aware disagreement and aligned Delta ablations. Freeze definitions first.
5. Curate a new independently reviewed, family-separated holdout with enough active
   evidence, causal and utility inputs to test each claimed capability. Freeze it before
   comparing the changed system. Include review burden and refusal correctness alongside
   unsafe execution and coverage; preserve all failures and negative results.

The answer is therefore **both implementation and design, plus a benchmark mismatch**.
The architecture is not disproven, but the present experiment does not demonstrate
that combining these heads adds value over the policy evaluator. The highest-value
improvement is semantic separation and stronger comparison, not more models or tuned
Delta weights on the same 180 cases.
