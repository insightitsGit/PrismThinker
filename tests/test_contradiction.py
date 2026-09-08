from __future__ import annotations

from pydantic import ValidationError

from prismthinker.config import ContradictionWeights, EngineConfig
from prismthinker.core.contradiction import pairwise_delta
from prismthinker.core.schemas import (
    AssumptionAtom,
    ConstraintApplication,
    ConstraintStatus,
    EvaluatorPair,
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


def test_evaluator_pair_sorts_before_construct_without_mutating_input() -> None:
    payload = {"left": "utility", "right": "causal"}
    pair = EvaluatorPair.model_validate(payload)
    assert payload["left"] == "utility"
    assert pair.left == "causal"
    assert pair.right == "utility"
    again = EvaluatorPair(left="utility", right="formal")
    assert again.left == "formal"
    assert again.right == "utility"


def test_evaluator_pair_rejects_identical_and_is_frozen() -> None:
    try:
        EvaluatorPair(left="formal", right="formal")
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass
    pair = EvaluatorPair(left="policy", right="formal")
    try:
        pair.left = "utility"  # type: ignore[misc]
        raise AssertionError("expected frozen error")
    except ValidationError:
        pass


def test_pairwise_delta_emits_sorted_pair() -> None:
    left = result("utility", Verdict.APPROVE)
    right = result("causal", Verdict.REJECT)
    pair = pairwise_delta(left, right, EngineConfig())
    assert pair.pair.left <= pair.pair.right
    assert {pair.pair.left, pair.pair.right} == {"causal", "utility"}


def test_critical_pair_boundary_matches_lattice():
    from prismthinker.core.contradiction import critical_pairs
    pair = pairwise_delta(result("formal", Verdict.APPROVE),
                          result("policy", Verdict.REJECT), EngineConfig())
    assert critical_pairs([pair], pair.delta) == []
    assert critical_pairs([pair], pair.delta - 0.001) == [pair]
    assert critical_pairs([pair], pair.delta + 0.001) == []
