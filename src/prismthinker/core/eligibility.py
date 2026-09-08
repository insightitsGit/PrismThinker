"""Non-compensatory execution checks, independent of evaluator voting."""
from itertools import combinations

from prismthinker.core.predicates import evaluate_predicate
from prismthinker.core.schemas import (
    AlignedDelta, ChorusGraphDirective, ConflictSignals, DeonticModality,
    EligibilityAssessment, EligibilityCheck, RuleSeverity,
)
from prismthinker.evaluators.formal import _range_ok, _type_ok


def aligned_conflicts(context, action):
    active = [c for c in context.aligned_claims
              if c.status == "active" and c.authority == "trusted"
              and (c.action_name is None or action is not None and c.action_name == action.name)]
    signals = ConflictSignals()
    compared = contradicted = 0
    for left, right in combinations(active, 2):
        if (left.subject, left.proposition, left.time_scope, left.kind) != (
                right.subject, right.proposition, right.time_scope, right.kind):
            continue
        compared += 1
        # bool and numeric values are different claims (True is not the number 1).
        equal = left.value == right.value and (isinstance(left.value, bool) == isinstance(right.value, bool))
        if equal:
            continue
        contradicted += 1
        signals.aligned_conflict_pairs.append([left.id, right.id])
        if left.kind == "authority":
            signals.policy_authority_conflict = True
        else:
            signals.material_evidence_conflict = True
    return signals, AlignedDelta(
        score=contradicted / compared if compared else None,
        comparable_pairs=compared, contradictory_pairs=contradicted,
        excluded_claims=len(context.aligned_claims) - len(active),
        sufficient_evidence=bool(compared),
    )


def assess_eligibility(context, hypothesis, config=None):
    from prismthinker.config import EngineConfig
    from prismthinker.core.evidence import detect_evidence_conflicts
    action = hypothesis.action
    checks = []
    eligible_rules = []
    groups = {}

    def add(id, kind, status, detail, cited=(), authority="trusted"):
        check = EligibilityCheck(id=id, kind=kind, status=status, detail=detail,
                                 cited_fact_keys=list(cited), authority=authority)
        checks.append(check)
        return check

    def predicate_status(expression):
        result = evaluate_predicate(expression, context.structured_facts, action)
        status = "missing" if result.unbound else "unknown" if result.error else "pass"
        return result, status

    for key, spec in context.fact_specs.items():
        fact = context.structured_facts.get(key)
        if fact is None:
            if spec.required:
                add(key, "fact", "missing", f"missing required fact {key}", [key])
        elif not _type_ok(spec, fact.value):
            add(key, "fact", "unknown", f"invalid fact type {key}", [key])
        elif not _range_ok(spec, fact.value):
            add(key, "fact", "block", f"fact {key} violates declared range", [key])

    invalid_facts = {c.id for c in checks if c.kind == "fact" and c.status == "unknown"}
    for constraint in context.constraints:
        result, status = predicate_status(constraint.predicate)
        if invalid_facts.intersection(result.cited_fact_keys):
            status = "unknown"
        if status == "pass" and not result.value:
            status = "block"
        add(constraint.id, "constraint", status, result.error or f"constraint {status}", result.cited_fact_keys)

    for rule in context.policy_rules:
        if rule.action_name is not None and (action is None or rule.action_name != action.name):
            add(rule.id, "policy", "not_applicable", "different action scope", authority=rule.authority)
            continue
        if rule.applies_when:
            applicability, status = predicate_status(rule.applies_when)
            if invalid_facts.intersection(applicability.cited_fact_keys):
                status = "unknown"
            if status != "pass":
                add(rule.id, "policy", status, "unresolved applicability", applicability.cited_fact_keys, rule.authority)
                continue
            if not applicability.value:
                add(rule.id, "policy", "not_applicable", "applicability predicate is false", authority=rule.authority)
                continue
        if rule.authority != "trusted":
            add(rule.id, "policy", "unknown", "unresolved authority", authority=rule.authority)
            continue
        eligible_rules.append(rule)
        result, status = predicate_status(rule.predicate)
        if invalid_facts.intersection(result.cited_fact_keys):
            status = "unknown"
        if status != "pass":
            add(rule.id, "policy", status, result.error or "missing policy facts", result.cited_fact_keys)
            continue
        violated = ((rule.modality == DeonticModality.PROHIBITION and result.value)
                    or (rule.modality == DeonticModality.OBLIGATION and not result.value))
        status = "review" if violated and rule.severity == RuleSeverity.CAUTION else "block" if violated else "pass"
        check = add(rule.id, "policy", status, f"{rule.modality.value}: {bool(result.value)}", result.cited_fact_keys)
        if rule.conflict_group:
            groups.setdefault(rule.conflict_group, []).append((rule, result, check))

    signals, shadow = aligned_conflicts(context, action)
    legacy_conflicts = [c for c in detect_evidence_conflicts(context, config or EngineConfig())
                        if c.conflict_type.value in {"numeric_mismatch", "explicit_negation"}]
    signals.material_evidence_conflict |= bool(legacy_conflicts)
    for group, members in groups.items():
        permissions = [r for r, result, c in members if r.modality == DeonticModality.PERMISSION and result.value]
        blocks = [(r, c) for r, result, c in members if c.status == "block"]
        if permissions and blocks:
            signals.policy_authority_conflict = True
            for rule, check in blocks:
                # Explicit hard veto remains a distinct non-overridable authority.
                if rule.severity != RuleSeverity.HARD_VETO:
                    check.status = "review"
                    check.detail = f"opposed permission in authority group {group}"
            add(group, "authority", "review", "opposed rules in the same explicit authority group")
    if signals.material_evidence_conflict:
        add("aligned-evidence", "evidence", "review", "contradictory aligned evidence")
    if signals.policy_authority_conflict:
        add("aligned-authority", "authority", "review", "contradictory authority")
    for claim in context.aligned_claims:
        if claim.action_name is not None and (action is None or claim.action_name != action.name):
            continue
        if claim.status == "unknown" or claim.status == "active" and claim.authority == "unknown":
            add(claim.id, claim.kind, "unknown", "claim status or authority unresolved", authority=claim.authority)

    # A blocker supported by disputed facts is not independently proven.
    disputed = {key for pair in signals.aligned_conflict_pairs for key in pair}
    disputed_claims = [c for c in context.aligned_claims if c.id in disputed]
    disputed_keys = {key for c in disputed_claims for key in c.fact_keys}
    unknown_provenance = any(not c.fact_keys for c in disputed_claims)
    legacy_ids = {id for c in legacy_conflicts for id in (c.left_id, c.right_id)}
    for item in context.evidence:
        if item.id in legacy_ids:
            disputed_keys.update(item.numeric_claims)
            unknown_provenance |= not bool(item.numeric_claims)
    for check in checks:
        if check.kind == "policy" and any(r.id == check.id and r.severity == RuleSeverity.HARD_VETO
                                           for r in eligible_rules):
            # Preserve the existing explicit, trusted hard-veto authority contract.
            continue
        if check.status == "block" and (unknown_provenance or disputed_keys.intersection(check.cited_fact_keys)):
            check.status = "review"
            check.detail = "blocker depends on disputed evidence"
    statuses = {c.status for c in checks}
    directive = (ChorusGraphDirective.REFUSE if "block" in statuses else
                 ChorusGraphDirective.ESCALATE if statuses.intersection({"unknown", "review"}) else
                 ChorusGraphDirective.GATHER if "missing" in statuses else None)
    return EligibilityAssessment(directive=directive, checks=checks), signals, shadow, eligible_rules

