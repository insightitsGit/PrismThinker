"""Effective τ is derived from the prior. The prior is an input, not a global lock."""

from __future__ import annotations

from dataclasses import dataclass

from prismthinker.classifier.features import POLICY_DOMAINS
from prismthinker.config import EngineConfig
from prismthinker.core.schemas import EpistemicRegime, EvaluatorResult, Verdict

TAU_FLOOR = 0.22
TAU_CEILING = 0.58

_REGIME_SHIFT = {
    EpistemicRegime.CLOSED_FORMAL: -0.05,
    EpistemicRegime.EMPIRICAL: 0.00,
    EpistemicRegime.POLICY_NORMATIVE: -0.03,
    EpistemicRegime.PRAGMATIC_SYSTEMS: 0.03,
    EpistemicRegime.OPEN_DIALECTIC: 0.06,
}


@dataclass(frozen=True)
class EffectiveThresholds:
    tau: float
    qualified_tau: float
    tau_base: float
    qualified_base: float
    adjustments: dict[str, float]

    @property
    def adapted(self) -> bool:
        return abs(self.tau - self.tau_base) > 1e-9


def priors_only(config: EngineConfig) -> EffectiveThresholds:
    return EffectiveThresholds(
        tau=config.tau_base,
        qualified_tau=config.qualified_tau,
        tau_base=config.tau_base,
        qualified_base=config.qualified_tau,
        adjustments={},
    )


def effective_thresholds(
    config: EngineConfig,
    *,
    results: dict[str, EvaluatorResult],
    uncertainty: float,
    evidence_severe: bool,
    regime: EpistemicRegime | None = None,
    domain: str | None = None,
) -> EffectiveThresholds:
    """Map the prior through run-local evidence. Deterministic. No learned weights."""
    if not config.dynamic_tau:
        return priors_only(config)

    determined_verdicts = [
        item.verdict for item in results.values() if item.verdict is not Verdict.UNDETERMINED
    ]
    determined = len(determined_verdicts)
    polar = Verdict.APPROVE in determined_verdicts and Verdict.REJECT in determined_verdicts
    adjustments: dict[str, float] = {}

    if polar:
        adjustments["polar"] = -0.06
    elif regime is not None:
        adjustments["regime"] = _REGIME_SHIFT.get(regime, 0.0)
    if determined <= 2:
        adjustments["thin_pool"] = -0.04
    elif determined >= 4 and not polar:
        adjustments["thick_pool"] = 0.03
    if evidence_severe and polar:
        adjustments["evidence"] = -0.03
    if uncertainty >= 0.35:
        adjustments["uncertainty"] = -0.03
    if domain and domain.lower() in POLICY_DOMAINS:
        adjustments["policy_domain"] = -0.02

    tau = _clip(config.tau_base + sum(adjustments.values()), TAU_FLOOR, TAU_CEILING)
    scale = tau / config.tau_base if config.tau_base > 1e-9 else 1.0
    qualified = _clip(config.qualified_tau * scale, 0.08, max(0.08, tau - 0.05))
    return EffectiveThresholds(
        tau=tau,
        qualified_tau=qualified,
        tau_base=config.tau_base,
        qualified_base=config.qualified_tau,
        adjustments=adjustments,
    )


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
