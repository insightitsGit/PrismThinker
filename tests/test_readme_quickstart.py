from __future__ import annotations

from prismthinker import (
    ActionKind,
    CandidateAction,
    DeonticModality,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    PolicyRule,
    PrismThinker,
    ReasoningContext,
    ReasoningDisposition,
    RuleSeverity,
)
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.core.schemas import ChorusGraphDirective


def _refund_context() -> ReasoningContext:
    return ReasoningContext(
        query="Process emergency customer refund exception",
        hypothesis=Hypothesis(
            id="hyp_tx_901",
            statement="Disburse unverified refund payment",
            action=CandidateAction(
                id="act_01",
                kind=ActionKind.TOOL_INVOCATION,
                name="disburse_refund",
                payload={"amount": 4200, "user_tier": "standard"},
            ),
        ),
        structured_facts={
            "amount": FactValue(key="amount", value=4200),
            "user_tier": FactValue(key="user_tier", value="standard"),
        },
        fact_specs={
            "amount": FactSpec(
                key="amount",
                fact_type=FactType.INT,
                mutable=True,
                minimum=0,
                maximum=10000,
                step=500,
            )
        },
        policy_rules=[
            PolicyRule(
                id="rule_refund_cap",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.amount > 2500 and fact.user_tier == standard",
                severity=RuleSeverity.HARD_VETO,
                text="Standard tier refunds cannot exceed $2,500 without manager signature.",
            )
        ],
    )


def test_readme_refund_is_hard_veto_with_empty_tools() -> None:
    graph = PrismThinker().evaluate(_refund_context())
    assert graph.disposition is ReasoningDisposition.HARD_VETO
    assert graph.recommended_rationale
    envelope = to_chorusgraph(graph, allowed_tools=["disburse_refund"])
    assert envelope.directive is ChorusGraphDirective.REFUSE
    assert envelope.allowed_tools == []
    resolving = [cf for cf in graph.counterfactuals if cf.resolving]
    assert resolving
    assert resolving[0].parameter_changed == "amount"
    assert resolving[0].value_after <= 2500
