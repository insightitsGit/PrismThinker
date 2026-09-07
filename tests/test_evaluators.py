from __future__ import annotations

from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    CausalEdge,
    CausalGraph,
    ConstraintSpec,
    DeonticModality,
    EvidenceItem,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    ObjectiveSpec,
    ObjectiveTerm,
    PolicyRule,
    ReasoningContext,
    RuleSeverity,
    Verdict,
)
from prismthinker.evaluators.causal import CausalEvaluator
from prismthinker.evaluators.empirical import EmpiricalEvaluator
from prismthinker.evaluators.formal import FormalEvaluator
from prismthinker.evaluators.policy import PolicyEvaluator
from prismthinker.core.predicates import evaluate_predicate
from prismthinker.evaluators.utility import UtilityEvaluator


def _hyp() -> Hypothesis:
    return Hypothesis(
        id="h1",
        statement="approve action",
        action=CandidateAction(
            id="a1",
            kind=ActionKind.BINARY_DECISION,
            name="act",
            payload={"cache_ttl": 60, "treatment": "ttl", "outcome": "latency"},
        ),
    )


def test_formal_happy_and_missing_and_no_mutation() -> None:
    ctx = ReasoningContext(
        query="check",
        structured_facts={"n": FactValue(key="n", value=3)},
        fact_specs={"n": FactSpec(key="n", fact_type=FactType.INT, minimum=0, maximum=10)},
        constraints=[ConstraintSpec(id="c1", predicate="fact.n >= 1")],
    )
    snapshot = ctx.model_dump()
    out = FormalEvaluator().evaluate(ctx, _hyp())
    assert out.verdict is Verdict.APPROVE
    assert ctx.model_dump() == snapshot
    missing = ReasoningContext(
        query="check",
        constraints=[ConstraintSpec(id="c1", predicate="fact.n >= 1")],
    )
    und = FormalEvaluator().evaluate(missing, _hyp())
    assert und.verdict is Verdict.UNDETERMINED


def test_policy_happy_and_missing() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="policy",
        structured_facts={"contains_pii": FactValue(key="contains_pii", value=True)},
        policy_rules=[
            PolicyRule(
                id="r",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.contains_pii == true",
                severity=RuleSeverity.HARD_VETO,
            )
        ],
    )
    out = PolicyEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.REJECT
    assert out.hard_veto is True
    empty = ReasoningContext(query="policy")
    und = PolicyEvaluator().evaluate(empty, hyp)
    assert und.verdict is Verdict.UNDETERMINED


def test_policy_vetoes_action_payload_amount() -> None:
    hyp = Hypothesis(
        id="h1",
        statement="Approve automated refund",
        action=CandidateAction(
            id="act_refund",
            kind=ActionKind.TOOL_INVOCATION,
            name="issue_refund",
            payload={"amount": 750},
        ),
    )
    ctx = ReasoningContext(
        query="approve refund",
        policy_rules=[
            PolicyRule(
                id="rule_refund_cap",
                modality=DeonticModality.PROHIBITION,
                predicate="action.payload.amount > 500",
                severity=RuleSeverity.HARD_VETO,
                text="Automated refunds cannot exceed $500.",
            )
        ],
    )
    out = PolicyEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.REJECT
    assert out.hard_veto is True
    hyp.action.payload["amount"] = 100  # type: ignore[union-attr]
    ok = PolicyEvaluator().evaluate(ctx, hyp)
    assert ok.hard_veto is False
    assert ok.verdict is Verdict.APPROVE


def test_empirical_happy_and_missing() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="emp",
        structured_facts={"cache_ttl": FactValue(key="cache_ttl", value=60)},
    )
    out = EmpiricalEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.APPROVE
    und = EmpiricalEvaluator().evaluate(ReasoningContext(query="emp"), hyp)
    assert und.verdict is Verdict.UNDETERMINED


def test_causal_happy_and_missing() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="cau",
        causal_graph=CausalGraph(
            nodes=["ttl", "latency"],
            edges=[CausalEdge(source="ttl", target="latency", signed=1, edge_id="e1")],
        ),
    )
    out = CausalEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.APPROVE
    und = CausalEvaluator().evaluate(ReasoningContext(query="cau"), hyp)
    assert und.verdict is Verdict.UNDETERMINED


def test_utility_happy_and_missing() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="util",
        structured_facts={"p99_latency_ms": FactValue(key="p99_latency_ms", value=180)},
        objective=ObjectiveSpec(
            id="o",
            terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
            reject_below=0.2,
            caution_below=0.5,
        ),
    )
    out = UtilityEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.APPROVE
    und = UtilityEvaluator().evaluate(ReasoningContext(query="util"), hyp)
    assert und.verdict is Verdict.UNDETERMINED


def test_all_heads_do_not_mutate_context() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="check",
        structured_facts={
            "n": FactValue(key="n", value=3),
            "cache_ttl": FactValue(key="cache_ttl", value=60),
            "p99_latency_ms": FactValue(key="p99_latency_ms", value=180),
            "contains_pii": FactValue(key="contains_pii", value=True),
        },
        fact_specs={"n": FactSpec(key="n", fact_type=FactType.INT, minimum=0, maximum=10)},
        constraints=[ConstraintSpec(id="c1", predicate="fact.n >= 1")],
        policy_rules=[
            PolicyRule(
                id="r",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.contains_pii == true",
                severity=RuleSeverity.BLOCK,
            )
        ],
        causal_graph=CausalGraph(
            nodes=["ttl", "latency"],
            edges=[CausalEdge(source="ttl", target="latency", signed=1, edge_id="e1")],
        ),
        objective=ObjectiveSpec(
            id="o",
            terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
        ),
    )
    snapshot = ctx.model_dump()
    for head in (
        FormalEvaluator(),
        PolicyEvaluator(),
        EmpiricalEvaluator(),
        CausalEvaluator(),
        UtilityEvaluator(),
    ):
        head.evaluate(ctx, hyp)
        assert ctx.model_dump() == snapshot


def test_heads_emit_assumption_atoms() -> None:
    hyp = _hyp()
    formal = FormalEvaluator().evaluate(
        ReasoningContext(
            query="check",
            structured_facts={"n": FactValue(key="n", value=3)},
            fact_specs={"n": FactSpec(key="n", fact_type=FactType.INT)},
            constraints=[ConstraintSpec(id="c1", predicate="fact.n >= 1")],
        ),
        hyp,
    )
    assert formal.assumptions
    policy = PolicyEvaluator().evaluate(
        ReasoningContext(
            query="policy",
            structured_facts={"contains_pii": FactValue(key="contains_pii", value=True)},
            policy_rules=[
                PolicyRule(
                    id="r",
                    modality=DeonticModality.PROHIBITION,
                    predicate="fact.contains_pii == true",
                    severity=RuleSeverity.HARD_VETO,
                )
            ],
        ),
        hyp,
    )
    assert policy.assumptions
    utility = UtilityEvaluator().evaluate(
        ReasoningContext(
            query="util",
            structured_facts={"p99_latency_ms": FactValue(key="p99_latency_ms", value=180)},
            objective=ObjectiveSpec(
                id="o",
                terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
            ),
        ),
        hyp,
    )
    assert utility.assumptions


def test_nested_predicates() -> None:
    facts = {
        "a": FactValue(key="a", value=1),
        "b": FactValue(key="b", value=2),
        "c": FactValue(key="c", value=False),
    }
    result = evaluate_predicate("fact.a == 1 and (fact.b == 2 or not fact.c == true)", facts, None)
    assert result.value is True
    assert result.unbound is False


def test_empirical_uses_fact_over_low_trust_outlier() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="checkout cache_ttl observation",
        structured_facts={"cache_ttl": FactValue(key="cache_ttl", value=60)},
        evidence=[
            EvidenceItem(
                id="e-low",
                content="noisy",
                source="canary",
                trust=0.2,
                numeric_claims={"cache_ttl": 10.0},
            ),
            EvidenceItem(
                id="e-high",
                content="ok",
                source="prom",
                trust=0.9,
                numeric_claims={"cache_ttl": 60.0},
            ),
        ],
    )
    out = EmpiricalEvaluator().evaluate(ctx, hyp)
    assert out.verdict in {Verdict.APPROVE, Verdict.CAUTION}


def test_empirical_minimize_target_accepts_better_observation() -> None:
    hyp = Hypothesis(
        id="h-sla",
        statement="sla",
        action=CandidateAction(
            id="ship",
            kind=ActionKind.TOOL_INVOCATION,
            name="ship",
            payload={"p99_latency_ms": 90},
        ),
    )
    ctx = ReasoningContext(
        query="p99 latency SLA",
        structured_facts={"p99_latency_ms": FactValue(key="p99_latency_ms", value=90)},
        objective=ObjectiveSpec(
            id="sla",
            terms=[
                ObjectiveTerm(
                    fact_key="p99_latency_ms",
                    weight=1.0,
                    direction="minimize",
                    target=200.0,
                )
            ],
        ),
    )
    out = EmpiricalEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.APPROVE


def test_distribution_needs_three_observations() -> None:
    hyp = _hyp()
    ctx = ReasoningContext(
        query="sample distribution of cache_ttl",
        structured_facts={"cache_ttl": FactValue(key="cache_ttl", value=60)},
        evidence=[
            EvidenceItem(
                id="e1",
                content="a",
                source="s",
                numeric_claims={"cache_ttl": 50.0},
            ),
        ],
    )
    out = EmpiricalEvaluator().evaluate(ctx, hyp)
    assert out.verdict is Verdict.UNDETERMINED
