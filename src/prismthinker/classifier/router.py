from __future__ import annotations

from prismthinker.classifier.ast_safe import FastPathAttempt, probe_expression
from prismthinker.classifier.features import feature_scores
from prismthinker.config import EngineConfig
from prismthinker.core.schemas import ClassifierTrace, EpistemicRegime, ReasoningContext
from prismthinker.reason_codes import (
    REASON_AST_REJECTED,
    REASON_FAST_PATH,
    REASON_NONSTANDARD_MATH,
    REASON_REGIME_LOW_SCORE,
    REASON_REGIME_MARGIN,
    REASON_REGIME_OVERRIDE,
)

_SCORE_TO_REGIME = {
    "empirical": EpistemicRegime.EMPIRICAL,
    "policy_normative": EpistemicRegime.POLICY_NORMATIVE,
    "pragmatic_systems": EpistemicRegime.PRAGMATIC_SYSTEMS,
    "open_dialectic": EpistemicRegime.OPEN_DIALECTIC,
}


def classify(
    context: ReasoningContext,
    config: EngineConfig | None = None,
) -> tuple[ClassifierTrace, FastPathAttempt]:
    cfg = config or EngineConfig()
    attempt = probe_expression(context.query)
    if attempt.eligible:
        return (
            ClassifierTrace(
                regime=EpistemicRegime.CLOSED_FORMAL,
                fast_path=True,
                feature_scores={},
                reason_codes=[REASON_FAST_PATH],
                override_applied=False,
            ),
            attempt,
        )

    scores = feature_scores(context, cfg)
    codes = [REASON_AST_REJECTED]
    if attempt.math_shaped or attempt.division_by_zero:
        codes.append(REASON_NONSTANDARD_MATH)

    if context.force_regime is not None:
        return (
            ClassifierTrace(
                regime=context.force_regime,
                fast_path=False,
                feature_scores=scores,
                reason_codes=codes + [REASON_REGIME_OVERRIDE],
                override_applied=True,
            ),
            attempt,
        )

    if attempt.math_shaped or attempt.division_by_zero:
        return (
            ClassifierTrace(
                regime=EpistemicRegime.CLOSED_FORMAL,
                fast_path=False,
                feature_scores=scores,
                reason_codes=codes,
                override_applied=False,
            ),
            attempt,
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < cfg.classifier.score_floor:
        return (
            ClassifierTrace(
                regime=EpistemicRegime.OPEN_DIALECTIC,
                fast_path=False,
                feature_scores=scores,
                reason_codes=codes + [REASON_REGIME_LOW_SCORE],
                override_applied=False,
            ),
            attempt,
        )
    if top_score - second_score < cfg.classifier.score_margin:
        return (
            ClassifierTrace(
                regime=EpistemicRegime.OPEN_DIALECTIC,
                fast_path=False,
                feature_scores=scores,
                reason_codes=codes + [REASON_REGIME_MARGIN],
                override_applied=False,
            ),
            attempt,
        )
    return (
        ClassifierTrace(
            regime=_SCORE_TO_REGIME[top_name],
            fast_path=False,
            feature_scores=scores,
            reason_codes=codes,
            override_applied=False,
        ),
        attempt,
    )
