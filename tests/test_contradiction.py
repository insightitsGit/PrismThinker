from __future__ import annotations

from prismthinker.config import ContradictionWeights, EngineConfig
from prismthinker.core.contradiction import pairwise_delta
from prismthinker.core.schemas import (
    AssumptionAtom,
    ConstraintApplication,
    ConstraintStatus,
    Verdict,
)
from tests.conftest import result


def test_weights_sum_to_one() -> None:
    weights = ContradictionWeights()
    total = (
        weights.conclusion
        + weights.constraint
        + weights.evidence
        + weights.assumption
        + weights.premise
    )
    assert abs(total - 1.0) < 1e-12


def test_approve_vs_reject_conclusion_is_one() -> None:
    left = result("formal", Verdict.APPROVE)
    right = result("policy", Verdict.REJECT)
    pair = pairwise_delta(left, right, EngineConfig())
    assert pair.components.conclusion_conflict == 1.0


def test_inverted_constraint_is_one() -> None:
    left = result("formal", Verdict.APPROVE)
    right = result("policy", Verdict.REJECT)
    left.constraints_applied = [
        ConstraintApplication(constraint_id="c1", status=ConstraintStatus.SATISFIED)
    ]
    right.constraints_applied = [
        ConstraintApplication(constraint_id="c1", status=ConstraintStatus.VIOLATED)
    ]
    pair = pairwise_delta(left, right, EngineConfig())
    assert pair.components.constraint_conflict == 1.0


def test_assumption_conflict_when_polarities_flip() -> None:
    left = result("formal", Verdict.APPROVE)
    right = result("policy", Verdict.REJECT)
    left.assumptions = [
        AssumptionAtom(id="a", predicate="fact.cache_ttl >= 30", polarity=True)
    ]
    right.assumptions = [
        AssumptionAtom(id="b", predicate="fact.cache_ttl >= 30", polarity=False)
    ]
    pair = pairwise_delta(left, right, EngineConfig())
    assert pair.components.assumption_conflict == 1.0
