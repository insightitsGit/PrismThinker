"""Incomplete authoritative checks must not become permission to execute."""
import pytest

from prismthinker.config import EngineConfig
from prismthinker.core.disposition import apply_lattice
from prismthinker.core.schemas import (
    EvaluatorResult, Hypothesis, PolicyRule, ReasoningContext, Verdict,
)
from prismthinker.evaluators.policy import PolicyEvaluator
from prismthinker.reason_codes import REASON_POLICY_INCOMPLETE


@pytest.mark.parametrize("predicate", ["fact.absent == true", "fact.x === true"])
@pytest.mark.parametrize("with_permission", [False, True])
def test_incomplete_policy_never_approves(predicate, with_permission):
    rules = [PolicyRule(id="unknown", modality="prohibition", severity="block", predicate=predicate)]
    if with_permission:
        rules.insert(0, PolicyRule(id="allow", modality="permission", severity="block", predicate="fact.ok == true"))
    ctx = ReasoningContext(query="check", policy_rules=rules,
                           structured_facts={"ok": {"key": "ok", "value": True}})
    result = PolicyEvaluator().evaluate(ctx, Hypothesis(id="h", statement="act"))
    assert result.verdict is Verdict.UNDETERMINED
    assert result.confidence == 0
    assert REASON_POLICY_INCOMPLETE in result.reason_codes
    # Even two agreeing other heads cannot silently bypass an unknown policy.
    decision = apply_lattice({"policy": result, **{
        name: EvaluatorResult(evaluator=name, verdict=Verdict.APPROVE, confidence=1, backend="rules")
        for name in ("formal", "utility")
    }}, 0, 0, False, EngineConfig())
    assert decision.review_required
    assert REASON_POLICY_INCOMPLETE in decision.review_reasons


def test_proven_denial_survives_an_unknown_rule():
    ctx = ReasoningContext(query="check", structured_facts={"blocked": {"key": "blocked", "value": True}},
        policy_rules=[PolicyRule(id="unknown", modality="prohibition", severity="block", predicate="fact.absent == true"),
                      PolicyRule(id="deny", modality="prohibition", predicate="fact.blocked == true", severity="hard_veto")])
    result = PolicyEvaluator().evaluate(ctx, Hypothesis(id="h", statement="act"))
    assert result.verdict is Verdict.REJECT
    assert result.hard_veto


@pytest.mark.parametrize("predicate", ["fact.missing == true", "fact.cache_ttl === 60"])
def test_incomplete_policy_blocks_public_tool_envelope(predicate):
    from prismthinker import PrismThinker
    from prismthinker.adapters.chorusgraph import to_chorusgraph
    from tests.conftest import cache_ttl_context

    ctx = cache_ttl_context()
    ctx.policy_rules[0].predicate = predicate
    graph = PrismThinker().evaluate(ctx)
    envelope = to_chorusgraph(graph, allowed_tools=["ship"])
    assert envelope.directive.value != "execute"
    assert envelope.allowed_tools == []
    assert REASON_POLICY_INCOMPLETE in graph.review_reasons


