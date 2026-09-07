from __future__ import annotations

from collections import Counter

from prismthinker.config import EngineConfig
from prismthinker.core.thresholds import EffectiveThresholds, priors_only
from prismthinker.core.schemas import (
    EvaluatorCapability,
    EvaluatorError,
    EvaluatorResult,
    ReasoningDisposition,
    Verdict,
)
from prismthinker.reason_codes import (
    REASON_REVIEW_CONFLICT,
    REASON_REVIEW_EVIDENCE,
    REASON_REVIEW_POLICY_CAUTION,
    REASON_REVIEW_UNCERTAINTY,
    REASON_REVIEW_VETO,
    REASON_UNAUTHORIZED_VETO,
    REVIEW_TRIGGERS,
)


def strip_unauthorized_vetoes(
    results: dict[str, EvaluatorResult],
    capabilities: dict[str, EvaluatorCapability],
) -> tuple[dict[str, EvaluatorResult], list[EvaluatorError]]:
    cleaned: dict[str, EvaluatorResult] = {}
    errors: list[EvaluatorError] = []
    for name, result in results.items():
        cap = capabilities.get(name)
        authorized = bool(cap and cap.may_hard_veto and result.verdict is Verdict.REJECT)
        if result.hard_veto and not authorized:
            errors.append(
                EvaluatorError(
                    evaluator=name,
                    error_type="unauthorized_veto",
                    message="hard_veto ignored; head is not veto-capable",
                )
            )
            result = result.model_copy(
                update={
                    "hard_veto": False,
                    "reason_codes": list(dict.fromkeys(result.reason_codes + [REASON_UNAUTHORIZED_VETO])),
                }
            )
        elif result.hard_veto and result.verdict is not Verdict.REJECT:
            errors.append(
                EvaluatorError(
                    evaluator=name,
                    error_type="unauthorized_veto",
                    message="hard_veto ignored; verdict is not reject",
                )
            )
            result = result.model_copy(update={"hard_veto": False})
        cleaned[name] = result
    return cleaned, errors


def apply_uncited_penalty(
    results: dict[str, EvaluatorResult],
    penalty: float,
) -> dict[str, EvaluatorResult]:
    from prismthinker.reason_codes import REASON_UNCITED_CLAIM

    out: dict[str, EvaluatorResult] = {}
    for name, result in results.items():
        claims = []
        tagged = False
        for claim in result.claims:
            if claim.citations:
                claims.append(claim)
                continue
            tagged = True
            claims.append(
                claim.model_copy(
                    update={"confidence": max(0.0, claim.confidence * penalty)}
                )
            )
        codes = list(result.reason_codes)
        if tagged:
            codes.append(REASON_UNCITED_CLAIM)
        out[name] = result.model_copy(update={"claims": claims, "reason_codes": list(dict.fromkeys(codes))})
    return out


def drop_mismatched_claims(results: dict[str, EvaluatorResult]) -> dict[str, EvaluatorResult]:
    from prismthinker.core.schemas import polarity_matches_verdict
    from prismthinker.reason_codes import REASON_POLARITY_MISMATCH

    out: dict[str, EvaluatorResult] = {}
    for name, result in results.items():
        mismatched = False
        for claim in result.claims:
            if not polarity_matches_verdict(claim.polarity, result.verdict):
                mismatched = True
        codes = list(result.reason_codes)
        if mismatched:
            codes.append(REASON_POLARITY_MISMATCH)
        out[name] = result.model_copy(update={"reason_codes": list(dict.fromkeys(codes))})
    return out


class LatticeDecision:
    def __init__(
        self,
        disposition: ReasoningDisposition,
        recommended_verdict: Verdict | None,
        rationale: str,
        review_required: bool,
        review_reasons: list[str],
    ) -> None:
        self.disposition = disposition
        self.recommended_verdict = recommended_verdict
        self.rationale = rationale
        self.review_required = review_required
        self.review_reasons = review_reasons


def apply_lattice(
    results: dict[str, EvaluatorResult],
    delta_max: float,
    uncertainty: float,
    evidence_conflicts_severe: bool,
    config: EngineConfig,
    capabilities: dict[str, EvaluatorCapability] | None = None,
    thresholds: EffectiveThresholds | None = None,
) -> LatticeDecision:
    determined = [r for r in results.values() if r.verdict is not Verdict.UNDETERMINED]
    authorized_veto = False
    for name, result in results.items():
        cap = (capabilities or {}).get(name)
        may_veto = cap.may_hard_veto if cap is not None else True
        if result.hard_veto and result.verdict is Verdict.REJECT and may_veto:
            authorized_veto = True
            break

    bars = thresholds or priors_only(config)
    if authorized_veto:
        disposition = ReasoningDisposition.HARD_VETO
        recommended = Verdict.REJECT
        rationale = "lattice.hard_veto"
    elif len(determined) < 2 or uncertainty >= config.u_insufficient:
        disposition = ReasoningDisposition.INSUFFICIENT_EVIDENCE
        recommended = None
        rationale = "lattice.insufficient"
    elif delta_max > bars.tau:
        disposition = ReasoningDisposition.CONFLICT
        recommended = None
        rationale = "lattice.conflict"
    else:
        counts = Counter(r.verdict for r in determined)
        if not counts:
            disposition = ReasoningDisposition.INSUFFICIENT_EVIDENCE
            recommended = None
            rationale = "lattice.insufficient"
        else:
            top = counts.most_common()
            majority_verdict, majority_n = top[0]
            tied = len(top) > 1 and top[1][1] == majority_n
            if tied:
                disposition = ReasoningDisposition.CONFLICT
                recommended = None
                rationale = "lattice.tie"
            else:
                dissent = any(r.verdict is not majority_verdict for r in determined)
                any_caution = any(r.verdict is Verdict.CAUTION for r in determined)
                if (
                    delta_max > bars.qualified_tau
                    or any_caution
                    or dissent
                ):
                    disposition = ReasoningDisposition.QUALIFIED_CONSENSUS
                    recommended = majority_verdict
                    rationale = "lattice.qualified"
                else:
                    disposition = ReasoningDisposition.CONSENSUS
                    recommended = majority_verdict
                    rationale = "lattice.consensus"

    review_reasons: list[str] = []
    if disposition is ReasoningDisposition.HARD_VETO:
        review_reasons.append(REASON_REVIEW_VETO)
    if disposition is ReasoningDisposition.CONFLICT:
        review_reasons.append(REASON_REVIEW_CONFLICT)
    if uncertainty >= config.u_insufficient:
        review_reasons.append(REASON_REVIEW_UNCERTAINTY)
    if evidence_conflicts_severe:
        review_reasons.append(REASON_REVIEW_EVIDENCE)
    policy = results.get("policy")
    if (
        disposition is ReasoningDisposition.QUALIFIED_CONSENSUS
        and policy is not None
        and policy.verdict in {Verdict.CAUTION, Verdict.REJECT}
    ):
        review_reasons.append(REASON_REVIEW_POLICY_CAUTION)
    for result in results.values():
        if REVIEW_TRIGGERS.intersection(result.reason_codes):
            review_reasons.extend(sorted(REVIEW_TRIGGERS.intersection(result.reason_codes)))

    review_required = bool(review_reasons)
    return LatticeDecision(
        disposition=disposition,
        recommended_verdict=recommended,
        rationale=rationale,
        review_required=review_required,
        review_reasons=list(dict.fromkeys(review_reasons)),
    )
