# Eligibility and aligned conflicts — v1.2 migration

This is a behavior change, implemented after owner approval. New graphs/configs
use schema 1.2.0; historical 1.1.0 graphs remain readable. This source change is not
a deployment or a published package release. The frozen v1.1 specification and local
scientific reports continue to describe the old implementation.

## Action routing

Use `to_chorusgraph(graph).directive` for execution decisions. Do not infer a directive
from the voting disposition or recommended verdict alone. In v1.2 the graph's
`eligibility` contains versioned checks and an optional directive which takes
precedence over the existing lattice mapping. A null directive means the existing
lattice and review checks still apply; it is not permission to execute.

Precedence: independently proven BLOCK -> REFUSE; unresolved authority, malformed
checks or review conditions -> ESCALATE; missing required information -> GATHER;
otherwise defer to the existing engine. Every non-execution route removes tools.
Review metadata can remain true on a refusal, preserving the audit requirement.
The explicit trusted, applicable HARD_VETO contract still refuses, including when
evidence is disputed. Unknown authority and missing applicability do not establish
a trusted veto.

Each eligibility check records kind, ID, authority, status, explanation and cited
fact keys. False constraints and declared range violations can prove a block.
Parser errors and invalid fact types are unknown, not proven violations. An ordinary
block depending on disputed evidence is reviewed. A demonstrably independent block
can still refuse. Missing conflict provenance conservatively prevents assuming
that an ordinary block is independent.

PolicyRule additions:

- `authority`: trusted (default, preserving caller-authoritative legacy rules) or unknown.
- `action_name`: exact action scope; null applies to the supplied context.
- `applies_when`: optional predicate evaluated before the policy predicate.
- `conflict_group`: explicit group identifying competing policies. A matching
  permission and ordinary blocker in the same group require review. An unrelated
  permission cannot override a prohibition. A HARD_VETO is not canceled by permission.

These declarations must come from the trusted application, not model-generated
assertions of authority. They do not verify signatures or infer legal precedence.
Scoped/unknown-authority rules are filtered before legacy evaluator dispatch.

## Aligned claims and conflict outputs

`ReasoningContext.aligned_claims` accepts exported `AlignedClaim` objects with ID,
subject, proposition, time_scope, source, scalar value, kind (evidence/authority),
authority, status (active/superseded/unknown), optional action_name, citations and
fact_keys. IDs must be unique; nonfinite values and extra fields are rejected.

Only trusted active claims of the same kind, subject, proposition and time scope are
compared. Values use exact equality after caller normalization; boolean true is
distinct from numeric 1. Units, tolerances, temporal precedence and free-text claim
extraction are not inferred. Superseded status is explicitly supplied by the caller,
not guessed from timestamps. `fact_keys` connects claims to facts supporting blockers.
Unknown authority/status is excluded from scoring but still prevents execution
unless an independent blocker already establishes refusal. An irrelevant action_name
excludes a claim from the current action.

The graph exposes `conflict_signals`:

- material_evidence_conflict: aligned evidence contradictions or legacy numeric/negation conflicts.
- policy_authority_conflict: aligned authority contradictions or opposed grouped rules.
- evaluator_disagreement: different determinate evaluator verdicts, excluding abstentions.
- decision_tie: the lattice explicitly selected its tie route.
- aligned_conflict_pairs: the claim IDs that contradict.

Legacy evidence inputs retain their existing numeric/negation detector. Fully scoped
comparisons require the new aligned representation; no benchmark labels are copied
into claims. The validation adapter retains a broad conflict flag for compatibility;
that flag must not be advertised as a dedicated material-conflict metric.

## Shadow score and ablation

The existing Delta formula, weights and thresholds are unchanged. `aligned_delta`
uses version aligned-shadow-v1: contradictory comparable pairs / comparable pairs.
It also records compared, contradictory and excluded counts. With no comparable
pairs the score is null and sufficient_evidence is false, not a fabricated zero.
Sufficient means a comparison exists, not source independence or statistical power.
This intentionally simple candidate is uncalibrated and does not drive routing.
Typed conflict detection does drive review; the numeric shadow score does not.

`validation.baselines.eligibility.EligibilityBaseline` removes voting and Delta while
keeping the same gate. Set `include_eligibility_baseline: true` in a new experiment
config before freezing to include it in local-model reports. It is a shared-code
ablation, not an independent rule-engine implementation. It gathers when no checks
establish any basis for action. Its confidence is a deterministic indicator, not a
probability.

## Validation boundary

Unit/integration tests cover blockers, missing facts, parse/type errors, authority,
scope, grouped policies, independent evidence, hard veto precedence, gather keys,
complementary claims, supersession, shadow invariance and tool suppression.
`validation.experiments.design_regression` replays the inspected corpus with the new
engine and gate-only baseline, saving a separate source-hashed development artifact.
It does not call models or overwrite old reports. Improved scores on those cases
are regression evidence only. A new independently reviewed holdout and preregistered
component/baseline comparisons are still required for scientific claims.
