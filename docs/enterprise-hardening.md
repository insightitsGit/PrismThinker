# Enterprise hardening: correctness and trusted SDK boundary

This development milestone does not establish production readiness. The frozen
scientific reports remain unchanged. Replays of inspected cases are development
regressions, not fresh evidence of generalization.

## Decision behavior

An explicit `action.payload.effect_sign` requests a universal signed-path check.
It must be integer `1` or `-1`. Every simple directed treatment-to-outcome path
must have that sign. A known opposing or zero path refuses execution, even when
another path is unknown. Unknown signs or a missing path gather evidence. A
malformed sign or exhausted traversal budget escalates. This contract is about
signed paths, not estimating a net causal effect from path magnitudes.

This requirement runs in eligibility, so other evaluator votes cannot compensate
for failure. Hosts must require the appropriate action fields using their own
action schemas; omitting `effect_sign` does not declare a mandatory causal check.
Causal evaluator traversal has a fixed 10,000-state/queue bound. This does not
constitute an overall request deadline or a bound on every input collection.

Mandatory objective terms (`sla_breach_is_reject`) with maximize/minimize targets
also run in eligibility. Missing measurements gather, invalid measurements
escalate, and known target breaches refuse. A `hit` target escalates until an
explicit acceptance interval is supplied as constraints; inferred scoring
tolerance does not establish a mandatory acceptance interval.

Evidence metadata `superseded_by` suppresses historical evidence only when the
entire replacement chain resolves to existing, unique IDs from the same source
with nondecreasing trust. Missing references, cycles and ambiguous IDs retain
evidence. This filtering applies to empirical evaluation and conflict detection.
Source and trust fields must come from authenticated host ingestion.

## Trusted SDK entry point

`prismthinker.adapters.trusted.evaluate_proposal` accepts only a statement and
candidate action from an untrusted proposer. It rejects additional top-level
fields, checks an action-name allowlist and evaluates a deep copy of host-owned
context. Policies, authority, evidence and evaluator selection come from the
host. The existing `evaluate(ReasoningContext)` API remains a trusted-caller API.

```python
from prismthinker.adapters.trusted import evaluate_proposal

envelope = evaluate_proposal(
    engine,
    {"statement": "Request a refund", "action": proposed_action},
    trusted_context=server_loaded_context,
    allowed_action_names={"issue_refund"},
    allowed_tools=["refund_service"],
)
```

The host must authenticate and authorize the caller, validate tool arguments,
load current policy and facts, and consume the envelope within its trusted
process. Do not treat a client-supplied envelope as authorization. Execute only
the exact evaluated action. This adapter does not provide signatures, replay
protection, transaction isolation or network authentication.

## Remaining production gates

1. Bind authorization to action arguments, policy version and context revision
   at the execution boundary, including expiry and atomic replay protection.
2. Bound request bytes, collection sizes and predicate complexity; enforce an
   end-to-end deadline and concurrency limits, then run load and fault tests.
3. Add redacted audit retention, operational metrics and rollback procedures.
4. Establish release provenance, dependency scanning and compatibility policy.
5. Run independently reviewed customer cases in shadow mode before considering
   autonomous use. Keep contradiction-score claims limited to measured evidence.
