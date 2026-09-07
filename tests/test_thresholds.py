from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import EpistemicRegime, Verdict
from prismthinker.core.thresholds import TAU_CEILING, TAU_FLOOR, effective_thresholds
from tests.conftest import result


def _heads(*verdicts: Verdict) -> dict:
    names = ("formal", "policy", "utility", "empirical")
    return {name: result(name, verdict) for name, verdict in zip(names, verdicts)}


def test_dynamic_uses_prior_as_center() -> None:
    config = EngineConfig(tau_base=0.40, qualified_tau=0.20, dynamic_tau=True)
    bars = effective_thresholds(
        config,
        results=_heads(Verdict.APPROVE, Verdict.APPROVE, Verdict.APPROVE),
        uncertainty=0.1,
        evidence_severe=False,
        regime=EpistemicRegime.EMPIRICAL,
    )
    assert bars.tau_base == 0.40
    assert abs(bars.tau - 0.40) < 1e-9
    assert bars.adapted is False


def test_off_switch_returns_priors() -> None:
    config = EngineConfig(tau_base=0.40, dynamic_tau=False)
    bars = effective_thresholds(
        config,
        results=_heads(Verdict.APPROVE, Verdict.REJECT),
        uncertainty=0.5,
        evidence_severe=True,
        regime=EpistemicRegime.OPEN_DIALECTIC,
        domain="privacy",
    )
    assert bars.tau == 0.40
    assert bars.qualified_tau == 0.20
    assert bars.adjustments == {}


def test_severe_evidence_and_policy_domain_tighten() -> None:
    config = EngineConfig(dynamic_tau=True)
    bars = effective_thresholds(
        config,
        results=_heads(Verdict.APPROVE, Verdict.REJECT, Verdict.APPROVE),
        uncertainty=0.4,
        evidence_severe=True,
        regime=EpistemicRegime.POLICY_NORMATIVE,
        domain="privacy",
    )
    assert bars.tau < config.tau_base
    assert bars.tau >= TAU_FLOOR
    assert "polar" in bars.adjustments
    assert "policy_domain" in bars.adjustments
    assert bars.qualified_tau < bars.tau


def test_open_dialectic_widens_but_stays_bounded() -> None:
    config = EngineConfig(dynamic_tau=True)
    bars = effective_thresholds(
        config,
        results=_heads(Verdict.APPROVE, Verdict.APPROVE, Verdict.APPROVE, Verdict.CAUTION),
        uncertainty=0.1,
        evidence_severe=False,
        regime=EpistemicRegime.OPEN_DIALECTIC,
    )
    assert bars.tau > config.tau_base
    assert bars.tau <= TAU_CEILING


def test_polar_heads_do_not_widen() -> None:
    config = EngineConfig(dynamic_tau=True)
    bars = effective_thresholds(
        config,
        results=_heads(Verdict.APPROVE, Verdict.REJECT, Verdict.APPROVE, Verdict.APPROVE),
        uncertainty=0.1,
        evidence_severe=False,
        regime=EpistemicRegime.OPEN_DIALECTIC,
        domain="privacy",
    )
    assert bars.tau < config.tau_base
    assert "polar" in bars.adjustments
    assert "regime" not in bars.adjustments


def test_formula_is_deterministic() -> None:
    config = EngineConfig(dynamic_tau=True)
    kwargs = dict(
        results=_heads(Verdict.APPROVE, Verdict.REJECT),
        uncertainty=0.2,
        evidence_severe=True,
        regime=EpistemicRegime.PRAGMATIC_SYSTEMS,
        domain="sre",
    )
    left = effective_thresholds(config, **kwargs)
    right = effective_thresholds(config, **kwargs)
    assert left == right
