from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import FactSpec, FactType, ReasoningContext, Verdict
from prismthinker.core.uncertainty import uncertainty_score
from tests.conftest import result


def test_uncertainty_capped_with_many_unresolved() -> None:
    results = {
        "formal": result("formal", Verdict.UNDETERMINED, unresolved=[f"q{i}" for i in range(40)]),
        "policy": result("policy", Verdict.UNDETERMINED, unresolved=[f"p{i}" for i in range(40)]),
    }
    u = uncertainty_score(results, ReasoningContext(query="q"), EngineConfig())
    assert 0.0 <= u <= 1.0


def test_empty_evidence_rule_only_does_not_inflate_coverage() -> None:
    results = {
        "formal": result("formal", Verdict.APPROVE, confidence=1.0),
        "policy": result("policy", Verdict.APPROVE, confidence=1.0),
    }
    ctx = ReasoningContext(
        query="q",
        fact_specs={"n": FactSpec(key="n", fact_type=FactType.INT, required=False)},
    )
    u = uncertainty_score(results, ctx, EngineConfig())
    assert u == 0.0
