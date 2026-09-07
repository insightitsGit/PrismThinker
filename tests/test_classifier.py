from __future__ import annotations

from prismthinker.classifier.router import classify
from prismthinker.core.schemas import (
    CausalEdge,
    CausalGraph,
    DeonticModality,
    EpistemicRegime,
    FactValue,
    ObjectiveSpec,
    ObjectiveTerm,
    PolicyRule,
    ReasoningContext,
    RuleSeverity,
)


def test_policy_lexemes_and_rules() -> None:
    ctx = ReasoningContext(
        query="must not retain pii under gdpr",
        policy_rules=[
            PolicyRule(
                id="r1",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.contains_pii == true",
                severity=RuleSeverity.HARD_VETO,
            )
        ],
        domain="privacy",
    )
    trace, _ = classify(ctx)
    assert trace.fast_path is False
    assert trace.regime is EpistemicRegime.POLICY_NORMATIVE


def test_mixed_families_open_dialectic() -> None:
    ctx = ReasoningContext(
        query="cache p99 sla and pii retention under gdpr with sample distribution",
        structured_facts={"p99_latency_ms": FactValue(key="p99_latency_ms", value=100)},
        policy_rules=[
            PolicyRule(
                id="r1",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.contains_pii == true",
                severity=RuleSeverity.BLOCK,
            )
        ],
        objective=ObjectiveSpec(
            id="o",
            terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
        ),
        causal_graph=CausalGraph(nodes=["a", "b"], edges=[CausalEdge(source="a", target="b", edge_id="e1")]),
        domain="privacy",
    )
    trace, _ = classify(ctx)
    assert trace.regime is EpistemicRegime.OPEN_DIALECTIC


def test_force_regime() -> None:
    ctx = ReasoningContext(query="hello world", force_regime=EpistemicRegime.EMPIRICAL)
    trace, _ = classify(ctx)
    assert trace.regime is EpistemicRegime.EMPIRICAL
    assert trace.override_applied is True


def test_math_shaped_closed_formal_not_fast_path() -> None:
    ctx = ReasoningContext(query="2 + x")
    trace, attempt = classify(ctx)
    assert attempt.eligible is False
    assert trace.fast_path is False
    assert trace.regime is EpistemicRegime.CLOSED_FORMAL
