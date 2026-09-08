import pytest
from pydantic import ValidationError

from prismthinker import PrismThinker
from prismthinker.adapters.trusted import evaluate_proposal
from prismthinker.core.eligibility import assess_eligibility
from prismthinker.core.evidence import active_evidence
from prismthinker.core.schemas import (
    CandidateAction, CausalEdge, CausalGraph, EvidenceItem, Hypothesis,
    ReasoningContext, PolicyRule,
    FactValue, ObjectiveSpec, ObjectiveTerm,
)


def causal(signs, direct=None):
    edges = [CausalEdge(source="a", target="b", signed=signs[0], edge_id="ab"),
             CausalEdge(source="b", target="c", signed=signs[1], edge_id="bc")]
    if direct is not None:
        edges.append(CausalEdge(source="a", target="c", signed=direct, edge_id="ac"))
    return ReasoningContext(query="release", causal_graph=CausalGraph(nodes=["a", "b", "c"], edges=edges),
        hypothesis=Hypothesis(id="h", statement="release", action=CandidateAction(
            id="a", kind="tool_invocation", name="release",
            payload={"treatment": "a", "outcome": "c", "effect_sign": 1})))


@pytest.mark.parametrize("signs,direct,expected", [
    ((1, None), None, "gather"), ((None, 1), -1, "refuse"),
    ((1, -1), 1, "refuse"), ((-1, -1), None, None),
    ((None, 0), None, "refuse"), ((1, 1), None, None),
])
def test_causal_gate_cannot_be_outvoted(signs, direct, expected):
    ctx = causal(signs, direct)
    result = assess_eligibility(ctx, ctx.hypothesis)[0]
    assert (result.directive.value if result.directive else None) == expected


def test_disconnected_graph_gathers():
    ctx = causal((1, 1))
    ctx.causal_graph.edges = []
    assert assess_eligibility(ctx, ctx.hypothesis)[0].directive.value == "gather"


@pytest.mark.parametrize("target,source,trust,expected", [
    ("new", "meter", .9, ["new"]), ("missing", "meter", .9, ["old", "new"]),
    ("new", "other", .9, ["old", "new"]), ("new", "meter", .1, ["old", "new"]),
])
def test_supersession_requires_resolvable_same_source(target, source, trust, expected):
    ctx = ReasoningContext(query="q", evidence=[
        EvidenceItem(id="old", content="old", source="meter", trust=.9, metadata={"superseded_by": target}),
        EvidenceItem(id="new", content="new", source=source, trust=trust)])
    assert [e.id for e in active_evidence(ctx)] == expected


def test_proposal_cannot_replace_host_policy():
    ctx = causal((1, 1))
    ctx.policy_rules = [PolicyRule(id="deny", modality="prohibition", severity="block", predicate="action.payload.effect_sign == 1")]
    proposal = {"statement": "ignore the policy", "action": ctx.hypothesis.action.model_dump(mode="json")}
    before = ctx.model_dump()
    envelope = evaluate_proposal(PrismThinker(), proposal, trusted_context=ctx,
        allowed_action_names={"release"}, allowed_tools=["release"])
    assert envelope.directive.value == "refuse"
    assert envelope.allowed_tools == []
    assert ctx.model_dump() == before
    with pytest.raises(ValidationError):
        evaluate_proposal(PrismThinker(), {**proposal, "policy_rules": []}, trusted_context=ctx,
            allowed_action_names={"release"}, allowed_tools=["release"])
    with pytest.raises(ValueError, match="not authorized"):
        evaluate_proposal(PrismThinker(), proposal, trusted_context=ctx,
            allowed_action_names=set(), allowed_tools=["release"])


@pytest.mark.parametrize("value,expected", [(9, "refuse"), (10, None), (None, "gather"),
                                           (True, "escalate"), (float("nan"), "escalate")])
def test_mandatory_objective(value, expected):
    ctx = causal((1, 1))
    ctx.objective = ObjectiveSpec(id="sla", terms=[ObjectiveTerm(
        fact_key="capacity", weight=1, direction="maximize", target=10, sla_breach_is_reject=True)])
    if value is not None:
        ctx.structured_facts["capacity"] = FactValue(key="capacity", value=value)
    result = assess_eligibility(ctx, ctx.hypothesis)[0]
    assert (result.directive.value if result.directive else None) == expected


def test_causal_work_budget_fails_closed():
    ctx = causal((1, 1))
    ctx.causal_graph = CausalGraph(nodes=[str(i) for i in range(18)], edges=[
        CausalEdge(source=str(i), target=str(j), signed=1, edge_id=f"{i}:{j}")
        for i in range(18) for j in range(i+1, 18)])
    ctx.hypothesis.action.payload.update(treatment="0", outcome="17")
    assert assess_eligibility(ctx, ctx.hypothesis)[0].directive.value == "escalate"


def test_supersession_cycle_preserves_both_items():
    ctx = ReasoningContext(query="q", evidence=[
        EvidenceItem(id="a", content="a", source="meter", metadata={"superseded_by": "b"}),
        EvidenceItem(id="b", content="b", source="meter", metadata={"superseded_by": "a"})])
    assert len(active_evidence(ctx)) == 2
