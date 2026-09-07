from __future__ import annotations

from dataclasses import dataclass

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import BackendKind, EpistemicRegime, IndependenceClass, ReasoningContext
from prismthinker.evaluators.causal import CausalEvaluator
from prismthinker.evaluators.empirical import EmpiricalEvaluator
from prismthinker.evaluators.formal import FormalEvaluator
from prismthinker.evaluators.policy import PolicyEvaluator
from prismthinker.evaluators.utility import UtilityEvaluator
from prismthinker.reason_codes import (
    REASON_SELECTOR_FILL,
    REASON_SELECTOR_FORCED,
    REASON_SELECTOR_INDEPENDENCE,
    REASON_SELECTOR_OVERLAY,
)


def build_registry(config: EngineConfig) -> dict[str, object]:
    return {
        "formal": FormalEvaluator(),
        "policy": PolicyEvaluator(),
        "empirical": EmpiricalEvaluator(config),
        "causal": CausalEvaluator(),
        "utility": UtilityEvaluator(),
    }


@dataclass(frozen=True)
class Selection:
    names: list[str]
    reason_codes: list[str]
    independence_ok: bool


def select_evaluators(
    regime: EpistemicRegime,
    context: ReasoningContext,
    config: EngineConfig,
    registry: dict[str, object],
) -> Selection:
    table = config.selector
    required = list(table.regime_required.get(regime.value, ()))
    optional = list(table.regime_optional.get(regime.value, ()))
    selected: list[str] = list(required)
    codes: list[str] = []

    for name in optional:
        if name not in selected:
            selected.append(name)

    domain = (context.domain or "").lower()
    overlays = table.domain_overlays.get(domain, ())
    if overlays:
        codes.append(REASON_SELECTOR_OVERLAY)
        for name in overlays:
            if name not in selected:
                selected.append(name)

    if context.force_evaluators:
        codes.append(REASON_SELECTOR_FORCED)
        for name in context.force_evaluators:
            if name not in selected:
                selected.append(name)

    unknown = [n for n in selected if n not in registry]
    if unknown:
        return Selection(selected, codes + [REASON_SELECTOR_INDEPENDENCE], False)

    if len(selected) < config.min_heads:
        codes.append(REASON_SELECTOR_FILL)
        for name in table.fill_order:
            if name not in selected and name in registry:
                selected.append(name)
            if len(selected) >= config.min_heads:
                break

    classes: list[IndependenceClass] = []
    backends: list[BackendKind] = []
    llm_count = 0
    for name in selected:
        cap = getattr(registry[name], "capability")
        classes.append(cap.independence_class)
        backends.append(cap.backend)
        if cap.backend is BackendKind.LLM:
            llm_count += 1
    if len(set(classes)) != len(classes) or llm_count > 1:
        return Selection(selected, codes + [REASON_SELECTOR_INDEPENDENCE], False)
    return Selection(selected, codes, True)
