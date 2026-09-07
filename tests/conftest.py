from __future__ import annotations

import pytest

from prismthinker import PrismThinker
from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    EvaluatorResult,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    ObjectiveSpec,
    ObjectiveTerm,
    PolicyRule,
    DeonticModality,
    ReasoningContext,
    RuleSeverity,
    Verdict,
    BackendKind,
)


@pytest.fixture
def thinker() -> PrismThinker:
    return PrismThinker()


def result(
    name: str,
    verdict: Verdict,
    *,
    confidence: float = 0.9,
    hard_veto: bool = False,
    support: list[str] | None = None,
    contradict: list[str] | None = None,
    premises: list[str] | None = None,
    unresolved: list[str] | None = None,
    codes: list[str] | None = None,
) -> EvaluatorResult:
    return EvaluatorResult(
        evaluator=name,
        verdict=verdict,
        confidence=confidence,
        supporting_evidence_ids=support or [],
        contradicting_evidence_ids=contradict or [],
        premise_ids=premises or [],
        unresolved_questions=unresolved or [],
        hard_veto=hard_veto,
        reason_codes=codes or [],
        backend=BackendKind.RULES,
    )


def cache_ttl_context(*, domain: str = "privacy") -> ReasoningContext:
    return ReasoningContext(
        query="Reduce cache_ttl stay at 60s for checkout.",
        hypothesis=Hypothesis(
            id="hyp:cache-ttl",
            statement="approve keeping cache_ttl at 60s",
            action=CandidateAction(
                id="keep_cache_ttl",
                kind=ActionKind.PARAMETER_CHANGE,
                name="keep_cache_ttl",
                payload={"cache_ttl": 60},
            ),
        ),
        structured_facts={
            "cache_ttl": FactValue(key="cache_ttl", value=60),
            "p99_latency_ms": FactValue(key="p99_latency_ms", value=180),
            "contains_pii": FactValue(key="contains_pii", value=True),
        },
        fact_specs={
            "cache_ttl": FactSpec(
                key="cache_ttl",
                fact_type=FactType.INT,
                mutable=True,
                minimum=1,
                maximum=300,
                step=10,
            ),
            "p99_latency_ms": FactSpec(
                key="p99_latency_ms",
                fact_type=FactType.FLOAT,
                mutable=False,
            ),
            "contains_pii": FactSpec(
                key="contains_pii",
                fact_type=FactType.BOOL,
                mutable=False,
            ),
        },
        policy_rules=[
            PolicyRule(
                id="pii-cache",
                modality=DeonticModality.PROHIBITION,
                predicate="fact.contains_pii == true and fact.cache_ttl >= 30",
                severity=RuleSeverity.HARD_VETO,
                text="PII cache retention",
            )
        ],
        objective=ObjectiveSpec(
            id="latency",
            terms=[
                ObjectiveTerm(
                    fact_key="p99_latency_ms",
                    weight=1.0,
                    direction="minimize",
                )
            ],
            reject_below=0.2,
            caution_below=0.5,
        ),
        domain=domain,
    )
