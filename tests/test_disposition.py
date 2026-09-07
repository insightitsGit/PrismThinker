from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.disposition import apply_lattice
from prismthinker.core.schemas import ReasoningDisposition, Verdict
from tests.conftest import result


def test_hard_veto() -> None:
    decision = apply_lattice(
        {"policy": result("policy", Verdict.REJECT, hard_veto=True)},
        delta_max=0.1,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert decision.disposition is ReasoningDisposition.HARD_VETO
    assert decision.recommended_verdict is Verdict.REJECT


def test_insufficient() -> None:
    decision = apply_lattice(
        {"formal": result("formal", Verdict.APPROVE)},
        delta_max=0.0,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert decision.disposition is ReasoningDisposition.INSUFFICIENT_EVIDENCE
    assert decision.recommended_verdict is None


def test_high_uncertainty() -> None:
    decision = apply_lattice(
        {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.APPROVE),
        },
        delta_max=0.0,
        uncertainty=0.7,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert decision.disposition is ReasoningDisposition.INSUFFICIENT_EVIDENCE


def test_conflict_high_delta() -> None:
    decision = apply_lattice(
        {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.REJECT),
        },
        delta_max=0.5,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert decision.disposition is ReasoningDisposition.CONFLICT
    assert decision.recommended_verdict is None


def test_qualified_and_consensus() -> None:
    qualified = apply_lattice(
        {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.APPROVE),
            "utility": result("utility", Verdict.CAUTION),
        },
        delta_max=0.1,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert qualified.disposition is ReasoningDisposition.QUALIFIED_CONSENSUS
    assert qualified.recommended_verdict is Verdict.APPROVE

    consensus = apply_lattice(
        {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.APPROVE),
        },
        delta_max=0.05,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert consensus.disposition is ReasoningDisposition.CONSENSUS
    assert consensus.recommended_verdict is Verdict.APPROVE


def test_majority_tie_is_conflict() -> None:
    decision = apply_lattice(
        {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.REJECT),
            "utility": result("utility", Verdict.CAUTION),
        },
        delta_max=0.15,
        uncertainty=0.1,
        evidence_conflicts_severe=False,
        config=EngineConfig(),
    )
    assert decision.disposition is ReasoningDisposition.CONFLICT
    assert decision.recommended_verdict is None
