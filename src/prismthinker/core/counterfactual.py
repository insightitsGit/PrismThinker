from __future__ import annotations

import time
from typing import Any, Callable

from prismthinker.config import EngineConfig
from prismthinker.core.contradiction import contradiction_matrix
from prismthinker.core.schemas import (
    CounterfactualProbe,
    FactType,
    FactValue,
    Hypothesis,
    ReasoningContext,
    Verdict,
)
from prismthinker.reason_codes import REASON_COUNTERFACTUAL_NO_SCHEMA, REASON_COUNTERFACTUAL_RESOLVED

PROBEABLE = {FactType.BOOL, FactType.INT, FactType.FLOAT, FactType.DURATION_MS, FactType.ENUM}


def _authorized_veto(results: dict) -> bool:
    return any(r.hard_veto and r.verdict is Verdict.REJECT for r in results.values())


def _is_resolving(
    delta_after: float,
    veto_after: bool,
    veto_before: bool,
    tau_base: float,
) -> bool:
    if delta_after <= tau_base and not veto_after:
        return True
    if veto_before and not veto_after:
        return True
    return False


def _candidates(spec, current: Any) -> list[Any]:
    if spec.fact_type is FactType.BOOL:
        return [not bool(current)]
    if spec.fact_type is FactType.ENUM:
        return [v for v in spec.enum_values if v != current]
    if spec.step is not None:
        step = spec.step
    elif spec.minimum is not None and spec.maximum is not None:
        step = 0.1 * (spec.maximum - spec.minimum) or 1.0
    else:
        step = 1.0
    lo = spec.minimum if spec.minimum is not None else None
    hi = spec.maximum if spec.maximum is not None else None
    values: list[Any] = []
    for k in range(1, 64):
        down = current - k * step
        up = current + k * step
        if spec.fact_type is FactType.INT:
            down, up = int(round(down)), int(round(up))
        added = False
        if lo is None or down >= lo:
            if hi is None or down <= hi:
                values.append(down)
                added = True
        if lo is None or up >= lo:
            if hi is None or up <= hi:
                values.append(up)
                added = True
        if not added:
            break
    return values


def probe_counterfactuals(
    context: ReasoningContext,
    hypothesis: Hypothesis,
    results: dict,
    delta_max: float,
    config: EngineConfig,
    run_heads: Callable[[ReasoningContext, Hypothesis], dict],
    tau: float | None = None,
) -> list[CounterfactualProbe]:
    bar = config.tau_base if tau is None else tau
    if delta_max <= bar and not _authorized_veto(results):
        return []

    mutable = []
    for key, spec in context.fact_specs.items():
        if not spec.mutable or spec.fact_type not in PROBEABLE:
            continue
        if key not in context.structured_facts:
            continue
        mutable.append(key)

    if not mutable:
        return [
            CounterfactualProbe(
                parameter_changed="",
                value_before=None,
                value_after=None,
                delta_before=delta_max,
                delta_after=delta_max,
                resolving=False,
                resolving_condition="no_mutable_facts",
                flips=[],
            )
        ]

    veto_before = _authorized_veto(results)
    prior: list[tuple[int, str]] = []
    conflicting_text = " ".join(
        a.predicate for r in results.values() for a in r.assumptions
    )
    for key in mutable:
        score = sum(1 for r in results.values() if key in r.premise_ids)
        if key in conflicting_text:
            score += 1
        prior.append((score, key))
    prior.sort(reverse=True)
    keys = [k for _, k in prior[: config.max_probe_params]]

    probes: list[CounterfactualProbe] = []
    deadline = time.perf_counter() + config.counterfactual_timeout_ms / 1000.0
    for key in keys:
        spec = context.fact_specs[key]
        before = context.structured_facts[key].value
        resolved_this_param = False
        for new_value in _candidates(spec, before):
            if len(probes) >= config.max_probes:
                break
            if time.perf_counter() > deadline:
                break
            copied = context.model_copy(deep=True)
            copied.structured_facts[key] = FactValue(
                key=key,
                value=new_value,
                unit=context.structured_facts[key].unit,
                observed_at=context.structured_facts[key].observed_at,
            )
            after_results = run_heads(copied, hypothesis)
            _, delta_after = contradiction_matrix(after_results, config)
            veto_after = _authorized_veto(after_results)
            resolving = _is_resolving(delta_after, veto_after, veto_before, bar)
            flips = [
                name
                for name, res in after_results.items()
                if name in results and res.verdict is not results[name].verdict
            ]
            condition = (
                f"If {key} changes from {before!r} to {new_value!r}, "
                f"Δ drops from {delta_max:.2f} to {delta_after:.2f}."
            )
            if resolving:
                condition = condition + " " + REASON_COUNTERFACTUAL_RESOLVED
            probes.append(
                CounterfactualProbe(
                    parameter_changed=key,
                    value_before=before,
                    value_after=new_value,
                    delta_before=delta_max,
                    delta_after=delta_after,
                    resolving=resolving,
                    resolving_condition=condition,
                    flips=flips,
                )
            )
            if resolving:
                resolved_this_param = True
                if config.stop_on_first_resolving:
                    break
            if resolved_this_param:
                break
        if len(probes) >= config.max_probes:
            break
        if time.perf_counter() > deadline:
            break

    probes.sort(key=lambda p: (not p.resolving, -(p.delta_before - p.delta_after)))
    return probes[: config.max_probes]


def no_schema_reason() -> str:
    return REASON_COUNTERFACTUAL_NO_SCHEMA
