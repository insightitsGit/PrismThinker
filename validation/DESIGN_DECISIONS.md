# Approved design changes — implementation record

The owner approved all three recommendations. The eligibility gate, aligned claim
schema, distinct conflict outputs and shadow score are implemented in v1.2. The
existing voting lattice and Delta weights remain diagnostic inputs; execution now
honors the gate first. See the [migration contract](../docs/eligibility-v1.2.md) for
the implemented semantics and limitations. Historical studies remain unchanged.

## Decision 1: execution permission

**Recommended: add an explicit eligibility gate before action routing.**

Today, structural APPROVE versus policy BLOCK becomes disagreement and usually
ESCALATE. Under the proposal, a proven applicable prohibition gives REFUSE even
if the action is structurally valid or useful. The graph still records disagreement
and whether an audit is needed. Refusal does not imply that every evaluator agrees.

Examples:

- A structurally valid export violates an authoritative retention rule: REFUSE.
- A useful operation lacks a required approval fact: GATHER; tools remain disabled.
- Two equally authoritative rules disagree about permission: ESCALATE.
- An explicitly authorized HARD_VETO applies: REFUSE under the existing contract.
- All required checks pass: retain the existing remaining execution checks.

The gate needs structured blocker records: rule/constraint ID, authority, scope,
applicability, evaluation status and cited facts. A formal failure must distinguish
an actual constraint violation from a parser or type error. Unknown authority cannot
be promoted to a proven blocker. BLOCK is not silently renamed HARD_VETO.

Alternative: keep all non-veto opposition as ESCALATE. This preserves today's
contract but intentionally retains unnecessary reviews for known prohibitions.

Compatibility impact: some CONFLICT/ESCALATE outputs become REFUSE. This needs
versioned behavior and migration notes. Acceptance tests must cover independent
blockers, contradictory authority, missing inputs, scope and permission overrides.

## Decision 2: what counts as a conflict

**Recommended: expose distinct evidence, authority, evaluator-disagreement and
decision-tie signals. Keep the current broad conflict flag for compatibility.**

Add typed claims with proposition/subject keys, value or polarity, time scope,
source, trust/authority and citations. Only claims about the same proposition and
compatible scope can contradict. Different facts or superseded records should not
automatically count as contradictions. No free-text interpretation is introduced
into the deterministic core.

Examples: two current records disagree about the same owner's identity -> evidence
conflict; an old ownership record replaced by a newer authoritative record ->
supersession; policy rejects while utility approves -> evaluator disagreement.

Alternative: retain the existing evidence schema and explicitly limit supported
conflicts to its numeric/negation relationships. This is smaller but leaves richer
authority and semantic conflicts outside the core's guarantees.

Compatibility impact: additive schema and outputs; material-conflict metrics need
new, prospectively frozen definitions. Claim extraction and structured-input reasoning
must be evaluated separately. Never inject benchmark labels as extracted claims.

## Decision 3: Delta

**Recommended: retain current Delta as a diagnostic while developing an aligned
candidate score in shadow mode. Do not replace the production formula yet.**

The candidate should compare aligned claims, separate missingness from disagreement,
and keep information diversity separate from contradiction. Record comparison counts
and sufficient-evidence status; an abstention should not create a contradiction merely
because its premise set differs. Any alternative aggregation/weights must be specified
before testing on a fresh holdout.

Compare against a deterministic policy/constraint controller, aligned binary
disagreement, dissent, confidence spread and individual Delta components. Measure
eligibility, actual execution errors and material conflicts separately. Promote a
new score only if it adds held-out value beyond these simpler signals.

Alternative: change Delta and its routing thresholds immediately. This is faster
to implement but lacks evidence and risks optimizing for the already inspected cases;
it is not recommended.

## Implementation sequence if approved

1. Specify and implement the eligibility gate and migration tests.
2. Add aligned claim types and distinct conflict outputs with adversarial controls.
3. Add simple deterministic and component-ablation baselines; shadow the new score.
4. Freeze a fresh independently reviewed corpus and comparison protocol before runs.

Success must include refusal correctness and review burden, not only unsafe execution.
All 180 old cases are development/regression data from this point onward.

## Implemented correctness fixes

- Policy predicate errors/missing paths cannot fall through to APPROVE. Incomplete
  policy checks require review even if other heads approve. Known denial is retained.
- Validation's broad conflict flag includes a CONFLICT disposition caused by a tie.
  This corrects omitted output; it does not claim material-conflict semantics are solved.
- Critical pair classification uses strict Delta > tau, matching the decision lattice.

The source-level diagnosis and limitations are in
[the root-cause report](reports/ROOT_CAUSE_v0.2-L.md). The historical zero-F1 result
remains historical; these fixes have not been presented as a new scientific run.
