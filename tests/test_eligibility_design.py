"""Contract tests for routing, authority, scope and aligned shadow diagnostics."""
import pytest
from pydantic import ValidationError
from prismthinker import AlignedClaim, PrismThinker
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.core.eligibility import assess_eligibility
from prismthinker.core.schemas import ConstraintSpec, Hypothesis, PolicyRule, ReasoningContext
from tests.conftest import cache_ttl_context


def context():
    ctx = cache_ttl_context()
    ctx.policy_rules = [PolicyRule(id="deny", modality="prohibition", severity="block",
                                  predicate="fact.contains_pii == true")]
    return ctx


def gate(ctx):
    return assess_eligibility(ctx, ctx.hypothesis)


def claim(id, value, **kw):
    return AlignedClaim(id=id, subject="record", proposition="contains_pii",
                        time_scope="current", source=id, value=value, fact_keys=["contains_pii"], **kw)


def test_block_wins_without_erasing_disagreement():
    graph = PrismThinker().evaluate(context())
    assert to_chorusgraph(graph, allowed_tools=["ship"]).directive.value == "refuse"
    assert to_chorusgraph(graph, allowed_tools=["ship"]).allowed_tools == []
    assert graph.conflict_signals.evaluator_disagreement
    assert not graph.conflict_signals.material_evidence_conflict
    assert graph.eligibility.checks[0].status == "block"


@pytest.mark.parametrize("change,expected", [
    ({"authority": "unknown"}, "escalate"),
    ({"predicate": "fact.missing == true"}, "gather"),
    ({"predicate": "fact.contains_pii === true"}, "escalate"),
    ({"applies_when": "fact.missing == true"}, "gather"),
])
def test_unresolved_rule_is_not_proven_denial(change, expected):
    ctx = context()
    ctx.policy_rules[0] = ctx.policy_rules[0].model_copy(update=change)
    assert gate(ctx)[0].directive.value == expected


@pytest.mark.parametrize("change", [{"action_name": "another_action"},
                                     {"applies_when": "fact.contains_pii == false"}])
def test_inapplicable_rules_cannot_veto(change):
    ctx = context()
    ctx.policy_rules[0] = ctx.policy_rules[0].model_copy(update=change)
    assessment, _, _, rules = gate(ctx)
    assert assessment.directive is None
    assert rules == []
    assert assessment.checks[0].status == "not_applicable"


def test_unknown_hard_veto_does_not_bypass_gate():
    ctx = context()
    ctx.policy_rules[0] = PolicyRule(id="unverified", modality="prohibition", severity="hard_veto",
        predicate="fact.contains_pii == true", authority="unknown")
    graph = PrismThinker().evaluate(ctx)
    assert to_chorusgraph(graph).directive.value == "escalate"
    assert not graph.evaluators["policy"].hard_veto


def test_independent_block_survives_missing_other_rule():
    ctx = context()
    ctx.policy_rules.append(PolicyRule(id="missing", modality="prohibition", severity="block", predicate="fact.absent == true"))
    assert gate(ctx)[0].directive.value == "refuse"


@pytest.mark.parametrize("same_group,expected", [(True, "escalate"), (False, "refuse")])
def test_permission_conflict_requires_explicit_same_authority_group(same_group, expected):
    ctx = context()
    ctx.policy_rules[0].conflict_group = "retention"
    ctx.policy_rules.append(PolicyRule(id="allow", modality="permission", severity="block",
        predicate="fact.contains_pii == true", conflict_group="retention" if same_group else "other"))
    assessment, signals, _, _ = gate(ctx)
    assert assessment.directive.value == expected
    assert signals.policy_authority_conflict is same_group


@pytest.mark.parametrize("predicate,expected", [("fact.cache_ttl < 20", "refuse"),
                                               ("fact.cache_ttl === 20", "escalate"),
                                               ("fact.unknown < 20", "gather")])
def test_constraints_distinguish_violation_from_error(predicate, expected):
    ctx = context()
    ctx.policy_rules = []
    ctx.constraints = [ConstraintSpec(id="limit", predicate=predicate)]
    assert gate(ctx)[0].directive.value == expected


def test_disputed_fact_cannot_prove_blocker():
    ctx = context()
    ctx.aligned_claims = [claim("a", True), claim("b", False)]
    assessment, signals, score, _ = gate(ctx)
    assert assessment.directive.value == "escalate"
    assert signals.material_evidence_conflict
    assert score.score == 1
    assert score.comparable_pairs == 1


@pytest.mark.parametrize("difference", ["subject", "proposition", "time_scope", "kind"])
def test_complementary_claims_are_not_contradictions(difference):
    ctx = context()
    other = claim("b", False).model_dump()
    other[difference] = "authority" if difference == "kind" else "different"
    ctx.aligned_claims = [claim("a", True), AlignedClaim(**other)]
    _, signals, score, _ = gate(ctx)
    assert not signals.material_evidence_conflict
    assert score.score is None
    assert not score.sufficient_evidence


@pytest.mark.parametrize("status", ["unknown", "superseded"])
def test_inactive_claims_do_not_distort_shadow_score(status):
    ctx = context()
    ctx.aligned_claims = [claim("a", True), claim("b", False, status=status)]
    assessment, signals, score, _ = gate(ctx)
    assert score.excluded_claims == 1
    assert score.score is None
    assert not signals.material_evidence_conflict


def test_shadow_does_not_change_legacy_delta():
    ctx = context()
    first = PrismThinker().evaluate(ctx)
    ctx.aligned_claims = [claim("a", True), claim("b", True)]
    second = PrismThinker().evaluate(ctx)
    assert first.contradiction_score == second.contradiction_score
    assert second.aligned_delta.score == 0


def test_duplicate_claim_ids_and_nan_are_rejected():
    with pytest.raises(ValidationError):
        ReasoningContext(query="check", aligned_claims=[claim("a", True), claim("a", False)])
    with pytest.raises(ValidationError):
        claim("bad", float("nan"))


def test_hard_veto_remains_distinct_from_disputed_block():
    ctx = context()
    ctx.policy_rules[0] = PolicyRule(id="veto", modality="prohibition", severity="hard_veto",
                                    predicate="fact.contains_pii == true")
    ctx.aligned_claims = [claim("a", True), claim("b", False)]
    assert gate(ctx)[0].directive.value == "refuse"


def test_missing_fact_is_exposed_in_gather_envelope():
    ctx = context()
    ctx.policy_rules[0].predicate = "fact.approval == true"
    envelope = to_chorusgraph(PrismThinker().evaluate(ctx), allowed_tools=["ship"])
    assert envelope.directive.value == "gather"
    assert "approval" in envelope.gather_fact_keys
    assert envelope.allowed_tools == []


def test_invalid_fact_type_is_unknown_not_a_proven_violation():
    ctx = context()
    ctx.structured_facts["contains_pii"].value = "false"
    assert gate(ctx)[0].directive.value == "escalate"


def test_independent_block_survives_unrelated_aligned_conflict():
    ctx = context()
    ctx.aligned_claims = [claim("a", True).model_copy(update={"fact_keys": ["other"]}),
                          claim("b", False).model_copy(update={"fact_keys": ["other"]})]
    assessment, signals, _, _ = gate(ctx)
    assert signals.material_evidence_conflict
    assert assessment.directive.value == "refuse"


def test_conflict_without_provenance_does_not_assume_independent_block():
    ctx = context()
    ctx.aligned_claims = [claim("a", True).model_copy(update={"fact_keys": []}),
                          claim("b", False).model_copy(update={"fact_keys": []})]
    assert gate(ctx)[0].directive.value == "escalate"
