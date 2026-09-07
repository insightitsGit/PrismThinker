from __future__ import annotations

import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, TimeoutError as FuturesTimeout
from datetime import datetime, timezone

from prismthinker.classifier.router import classify
from prismthinker.config import DEFAULT_CONFIG, EngineConfig, config_hash
from prismthinker.core.contradiction import (
    assumption_partition,
    contradiction_matrix,
    critical_pairs,
)
from prismthinker.core.counterfactual import probe_counterfactuals
from prismthinker.core.disposition import (
    apply_lattice,
    apply_uncited_penalty,
    drop_mismatched_claims,
    strip_unauthorized_vetoes,
)
from prismthinker.core.evidence import detect_evidence_conflicts
from prismthinker.core.failures import MAX_CRASH_MESSAGE, crash_message
from prismthinker.core.schemas import (
    ActionKind,
    BackendKind,
    CandidateAction,
    Citation,
    CitationKind,
    Claim,
    ClassifierTrace,
    DecisionGraph,
    EpistemicRadarPayload,
    EpistemicRegime,
    EvaluatorError,
    EvaluatorResult,
    FastPathResult,
    Hypothesis,
    PresentationContext,
    RadarAxis,
    ReasoningContext,
    ReasoningDisposition,
    Verdict,
    verdict_polarity,
)
from prismthinker.core.selector import build_registry, select_evaluators
from prismthinker.core.thresholds import effective_thresholds
from prismthinker.core.uncertainty import uncertainty_score
from prismthinker.reason_codes import (
    REASON_COUNTERFACTUAL_BUDGET,
    REASON_COUNTERFACTUAL_NO_SCHEMA,
    REASON_CRASH,
    REASON_LLM_INVALID,
    REASON_SELECTOR_INDEPENDENCE,
    REASON_TIMEOUT,
    REASON_UNSTRUCTURED_RULE_IGNORED,
)

HEAD_ORDER = ("formal", "policy", "empirical", "causal", "utility")


def materialize_hypothesis(context: ReasoningContext) -> Hypothesis:
    if context.hypothesis is not None:
        return context.hypothesis
    digest = hashlib.sha256(context.query.encode("utf-8")).hexdigest()[:16]
    hyp_id = f"hyp:{digest}"
    return Hypothesis(
        id=hyp_id,
        statement=context.query,
        action=CandidateAction(
            id=hyp_id,
            kind=ActionKind.ASSERTION,
            name="assert_query",
            payload={},
        ),
    )


class PrismThinker:
    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        if abs(sum(self.config.contradiction.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("invalid contradiction weights")
        self._hash = config_hash(self.config)
        self._registry = build_registry(self.config)
        self._capabilities = {name: ev.capability for name, ev in self._registry.items()}

    def evaluate(self, context: object) -> DecisionGraph:
        if isinstance(context, PresentationContext) or not isinstance(context, ReasoningContext):
            raise TypeError("PrismThinker.evaluate accepts ReasoningContext only")
        started = time.perf_counter()
        timings: dict[str, float] = {}
        hypothesis = materialize_hypothesis(context)

        if self.config.llm.enabled:
            return self._fail_closed(
                context,
                hypothesis,
                ClassifierTrace(
                    regime=EpistemicRegime.OPEN_DIALECTIC,
                    fast_path=False,
                    feature_scores={},
                    reason_codes=[REASON_LLM_INVALID],
                    override_applied=False,
                ),
                [],
                timings,
                started,
                extra_reasons=[REASON_LLM_INVALID],
            )

        t0 = time.perf_counter()
        trace, attempt = classify(context, self.config)
        timings["classify"] = (time.perf_counter() - t0) * 1000.0

        if trace.fast_path and attempt.eligible:
            return self._fast_path(context, hypothesis, trace, attempt.value, timings, started)

        t0 = time.perf_counter()
        evidence_conflicts = detect_evidence_conflicts(context, self.config)
        timings["evidence"] = (time.perf_counter() - t0) * 1000.0

        selection = select_evaluators(trace.regime, context, self.config, self._registry)
        extra_codes = list(selection.reason_codes)
        if context.rules:
            extra_codes.append(REASON_UNSTRUCTURED_RULE_IGNORED)
        trace = trace.model_copy(
            update={"reason_codes": list(dict.fromkeys(list(trace.reason_codes) + extra_codes))}
        )
        if not selection.independence_ok:
            return self._fail_closed(
                context, hypothesis, trace, selection.names, timings, started
            )

        t0 = time.perf_counter()
        results, errors, pool_over_budget = self._run_pool(selection.names, context, hypothesis)
        timings["pool"] = (time.perf_counter() - t0) * 1000.0

        results, veto_errors = strip_unauthorized_vetoes(results, self._capabilities)
        errors.extend(veto_errors)
        results = _restrict_evidence_ids(results, context)
        results = _sanitize_citations(results, context, hypothesis)
        results = apply_uncited_penalty(results, self.config.uncited_penalty)
        results = drop_mismatched_claims(results)

        pairs, delta_max = contradiction_matrix(results, self.config)
        u_score = uncertainty_score(results, context, self.config)
        shared, conflicting = assumption_partition(results)
        severe = any(c.severity >= 0.7 for c in evidence_conflicts)
        thresholds = effective_thresholds(
            self.config,
            results=results,
            uncertainty=u_score,
            evidence_severe=severe,
            regime=trace.regime,
            domain=context.domain,
        )
        crit = critical_pairs(pairs, thresholds.tau)

        def rerun(ctx: ReasoningContext, hyp: Hypothesis) -> dict:
            # Probes re-evaluate trusted in-process heads; isolation is for the primary pool.
            rerun_results, _, _ = self._run_thread_pool(selection.names, ctx, hyp)
            rerun_results, _ = strip_unauthorized_vetoes(rerun_results, self._capabilities)
            rerun_results = _restrict_evidence_ids(rerun_results, ctx)
            rerun_results = _sanitize_citations(rerun_results, ctx, hyp)
            rerun_results = apply_uncited_penalty(rerun_results, self.config.uncited_penalty)
            return rerun_results

        extra_questions: list[str] = []
        extra_review: list[str] = []
        for key in _missing_required_keys(context):
            extra_questions.append(f"missing required fact {key}")

        t0 = time.perf_counter()
        probes: list = []
        if pool_over_budget:
            extra_review.append(REASON_COUNTERFACTUAL_BUDGET)
            timings["counterfactual"] = 0.0
        else:
            probes = probe_counterfactuals(
                context, hypothesis, results, delta_max, self.config, rerun, tau=thresholds.tau
            )
            timings["counterfactual"] = (time.perf_counter() - t0) * 1000.0
            if (
                delta_max > thresholds.tau
                and probes
                and probes[0].resolving_condition == "no_mutable_facts"
            ):
                extra_review.append(REASON_COUNTERFACTUAL_NO_SCHEMA)
                extra_questions.append("provide FactSpec.mutable keys to probe")

        lattice = apply_lattice(
            results,
            delta_max,
            u_score,
            severe,
            self.config,
            self._capabilities,
            thresholds=thresholds,
        )
        review_reasons = list(lattice.review_reasons) + extra_review

        radar = _radar(
            results,
            crit,
            lattice.review_required,
            probes,
            evidence_conflicts,
            extra_questions,
            u_score,
            delta_max,
        )
        determined = [r for r in results.values() if r.verdict is not Verdict.UNDETERMINED]
        confidence = (
            sum(r.confidence for r in determined) / len(determined) if determined else 0.0
        )
        timings["total"] = (time.perf_counter() - started) * 1000.0
        timings["tau_effective"] = thresholds.tau
        timings["qualified_tau_effective"] = thresholds.qualified_tau
        timings["tau_base"] = thresholds.tau_base
        return DecisionGraph(
            run_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            config_hash=self._hash,
            query=context.query,
            hypothesis=hypothesis,
            regime=trace.regime,
            selected_evaluators=selection.names,
            classifier=trace,
            recommended_verdict=lattice.recommended_verdict,
            recommended_rationale=lattice.rationale,
            disposition=lattice.disposition,
            confidence=confidence,
            contradiction_score=delta_max,
            uncertainty_score=u_score,
            evaluators=results,
            evidence_conflicts=evidence_conflicts,
            critical_conflicts=crit,
            shared_assumptions=shared,
            conflicting_assumptions=conflicting,
            counterfactuals=probes,
            review_required=lattice.review_required or bool(extra_review),
            review_reasons=review_reasons,
            radar=radar,
            errors=errors,
            timings_ms=timings,
        )

    def _run_pool(
        self,
        names: list[str],
        context: ReasoningContext,
        hypothesis: Hypothesis,
    ) -> tuple[dict[str, EvaluatorResult], list[EvaluatorError], bool]:
        if self.config.isolate_heads and _all_standard_heads(names, self._registry):
            return self._run_isolated_pool(names, context, hypothesis)
        return self._run_thread_pool(names, context, hypothesis)

    def _run_thread_pool(
        self,
        names: list[str],
        context: ReasoningContext,
        hypothesis: Hypothesis,
    ) -> tuple[dict[str, EvaluatorResult], list[EvaluatorError], bool]:
        results: dict[str, EvaluatorResult] = {}
        errors: list[EvaluatorError] = []
        head_timeout = self.config.head_timeout_ms / 1000.0
        budget = self.config.pool_budget_ms / 1000.0
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
            futures = {
                name: pool.submit(
                    self._registry[name].evaluate,
                    context.model_copy(deep=True),
                    hypothesis.model_copy(deep=True),
                )
                for name in names
            }
            wait(list(futures.values()), timeout=budget)
            for name, fut in futures.items():
                t0 = time.perf_counter()
                remaining = max(0.0, min(head_timeout, budget - (t0 - started)))
                try:
                    if not fut.done() and remaining <= 0:
                        raise FuturesTimeout()
                    result = fut.result(timeout=remaining)
                    result = result.model_copy(
                        update={"latency_ms": (time.perf_counter() - t0) * 1000.0}
                    )
                    results[name] = result
                except FuturesTimeout:
                    errors.append(
                        EvaluatorError(evaluator=name, error_type="timeout", message="head timed out")
                    )
                    results[name] = _undetermined(name, REASON_TIMEOUT)
                except Exception as exc:  # noqa: BLE001 — isolate head crashes
                    errors.append(
                        EvaluatorError(
                            evaluator=name,
                            error_type="crash",
                            message=crash_message(exc, evaluator=name),
                        )
                    )
                    results[name] = _undetermined(name, REASON_CRASH)
        over_budget = (time.perf_counter() - started) * 1000.0 >= self.config.pool_budget_ms
        return results, errors, over_budget

    def _run_isolated_pool(
        self,
        names: list[str],
        context: ReasoningContext,
        hypothesis: Hypothesis,
    ) -> tuple[dict[str, EvaluatorResult], list[EvaluatorError], bool]:
        from prismthinker.core.isolation import (
            _queue_get,
            start_head_workers,
            terminate_process,
            wait_workers_ready,
        )

        results: dict[str, EvaluatorResult] = {}
        errors: list[EvaluatorError] = []
        head_timeout = self.config.head_timeout_ms / 1000.0
        budget = self.config.pool_budget_ms / 1000.0
        workers = start_head_workers(
            names,
            context.model_dump(mode="json"),
            hypothesis.model_dump(mode="json"),
            self.config.model_dump(mode="json"),
        )
        failures = wait_workers_ready(workers)
        for name, process, _queue in workers:
            if name not in failures:
                continue
            terminate_process(process)
            errors.append(
                EvaluatorError(
                    evaluator=name,
                    error_type="crash",
                    message=_sanitize_isolated_crash(failures[name]),
                )
            )
            results[name] = _undetermined(name, REASON_CRASH)
        started = time.perf_counter()
        for name, process, queue in workers:
            if name in failures:
                continue
            remaining = max(0.0, min(head_timeout, budget - (time.perf_counter() - started)))
            item = _queue_get(queue, remaining)
            if item is None:
                terminate_process(process)
                errors.append(
                    EvaluatorError(
                        evaluator=name,
                        error_type="timeout",
                        message="head timed out and worker was terminated",
                    )
                )
                results[name] = _undetermined(name, REASON_TIMEOUT)
                continue
            status, payload = item
            terminate_process(process)
            if status == "ok":
                result = EvaluatorResult.model_validate(payload)
                result = result.model_copy(
                    update={"latency_ms": (time.perf_counter() - started) * 1000.0}
                )
                results[name] = result
            else:
                errors.append(
                    EvaluatorError(
                        evaluator=name,
                        error_type="crash",
                        message=_sanitize_isolated_crash(payload),
                    )
                )
                results[name] = _undetermined(name, REASON_CRASH)
        over_budget = (time.perf_counter() - started) * 1000.0 >= self.config.pool_budget_ms
        return results, errors, over_budget

    def _fast_path(
        self,
        context: ReasoningContext,
        hypothesis: Hypothesis,
        trace: ClassifierTrace,
        value: object,
        timings: dict[str, float],
        started: float,
    ) -> DecisionGraph:
        claim = Claim(
            id="axiomatic-value",
            evaluator="axiomatic",
            statement=f"{context.query.strip()} = {value!r}",
            polarity=1.0,
            confidence=1.0,
            citations=[Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)],
            hypothesis_id=hypothesis.id,
        )
        result = EvaluatorResult(
            evaluator="axiomatic",
            verdict=Verdict.APPROVE,
            confidence=1.0,
            claims=[claim],
            backend=BackendKind.SOLVER,
        )
        timings["total"] = (time.perf_counter() - started) * 1000.0
        radar = EpistemicRadarPayload(
            contradiction=0.0,
            uncertainty=0.0,
            axes=[
                RadarAxis(
                    evaluator="axiomatic",
                    verdict=Verdict.APPROVE,
                    confidence=1.0,
                    polarity=1.0,
                    hard_veto=False,
                )
            ],
            critical_pairs=[],
            review_required=False,
            unresolved_questions=[],
            counterfactual_hints=[],
            evidence_conflict_count=0,
        )
        return DecisionGraph(
            run_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            config_hash=self._hash,
            query=context.query,
            hypothesis=hypothesis,
            regime=EpistemicRegime.CLOSED_FORMAL,
            selected_evaluators=["axiomatic"],
            classifier=trace,
            recommended_verdict=Verdict.APPROVE,
            recommended_rationale="lattice.consensus",
            disposition=ReasoningDisposition.CONSENSUS,
            confidence=1.0,
            contradiction_score=0.0,
            uncertainty_score=0.0,
            evaluators={"axiomatic": result},
            review_required=False,
            review_reasons=[],
            radar=radar,
            fast_path=FastPathResult(
                expression=context.query.strip(),
                value=value,
                value_type=type(value).__name__,
            ),
            timings_ms=timings,
        )

    def _fail_closed(
        self,
        context: ReasoningContext,
        hypothesis: Hypothesis,
        trace: ClassifierTrace,
        names: list[str],
        timings: dict[str, float],
        started: float,
        extra_reasons: list[str] | None = None,
    ) -> DecisionGraph:
        timings["total"] = (time.perf_counter() - started) * 1000.0
        reasons = list(extra_reasons or [REASON_SELECTOR_INDEPENDENCE])
        stubs = {name: _undetermined(name, reasons[0]) for name in names}
        radar = EpistemicRadarPayload(
            contradiction=0.0,
            uncertainty=1.0,
            axes=[],
            critical_pairs=[],
            review_required=True,
            unresolved_questions=["selector independence violation"] if not extra_reasons else [],
            counterfactual_hints=[],
            evidence_conflict_count=0,
        )
        return DecisionGraph(
            run_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            config_hash=self._hash,
            query=context.query,
            hypothesis=hypothesis,
            regime=trace.regime,
            selected_evaluators=names,
            classifier=trace,
            recommended_verdict=None,
            recommended_rationale="lattice.insufficient",
            disposition=ReasoningDisposition.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            contradiction_score=0.0,
            uncertainty_score=1.0,
            evaluators=stubs,
            review_required=True,
            review_reasons=reasons,
            radar=radar,
            timings_ms=timings,
        )


def _missing_required_keys(context: ReasoningContext) -> list[str]:
    return [
        spec.key
        for spec in context.fact_specs.values()
        if spec.required and spec.key not in context.structured_facts
    ]


_STANDARD_HEADS = frozenset({"formal", "policy", "empirical", "causal", "utility"})


def _all_standard_heads(names: list[str], registry: dict) -> bool:
    from prismthinker.evaluators.causal import CausalEvaluator
    from prismthinker.evaluators.empirical import EmpiricalEvaluator
    from prismthinker.evaluators.formal import FormalEvaluator
    from prismthinker.evaluators.policy import PolicyEvaluator
    from prismthinker.evaluators.utility import UtilityEvaluator

    types = {
        "formal": FormalEvaluator,
        "policy": PolicyEvaluator,
        "empirical": EmpiricalEvaluator,
        "causal": CausalEvaluator,
        "utility": UtilityEvaluator,
    }
    for name in names:
        expected = types.get(name)
        if expected is None or name not in registry or not isinstance(registry[name], expected):
            return False
    return True


def _sanitize_citations(
    results: dict[str, EvaluatorResult],
    context: ReasoningContext,
    hypothesis: Hypothesis,
) -> dict[str, EvaluatorResult]:
    evidence_ids = {item.id for item in context.evidence}
    fact_keys = set(context.structured_facts) | set(context.fact_specs)
    rule_ids = {rule.id for rule in context.policy_rules}
    constraint_ids = {item.id for item in context.constraints}
    edge_ids = (
        {edge.edge_id for edge in context.causal_graph.edges} if context.causal_graph else set()
    )

    def allowed(citation: Citation) -> bool:
        if citation.kind is CitationKind.EVIDENCE:
            return citation.ref in evidence_ids
        if citation.kind is CitationKind.FACT:
            return citation.ref in fact_keys
        if citation.kind is CitationKind.RULE:
            return citation.ref in rule_ids
        if citation.kind is CitationKind.CONSTRAINT:
            return citation.ref in constraint_ids
        if citation.kind is CitationKind.GRAPH_EDGE:
            return citation.ref in edge_ids
        if citation.kind is CitationKind.HYPOTHESIS:
            return citation.ref == hypothesis.id
        return False

    out: dict[str, EvaluatorResult] = {}
    for name, result in results.items():
        claims = [
            claim.model_copy(update={"citations": [c for c in claim.citations if allowed(c)]})
            for claim in result.claims
        ]
        out[name] = result.model_copy(update={"claims": claims})
    return out


def _restrict_evidence_ids(
    results: dict[str, EvaluatorResult],
    context: ReasoningContext,
) -> dict[str, EvaluatorResult]:
    known = {item.id for item in context.evidence}
    out: dict[str, EvaluatorResult] = {}
    for name, result in results.items():
        out[name] = result.model_copy(
            update={
                "supporting_evidence_ids": [i for i in result.supporting_evidence_ids if i in known],
                "contradicting_evidence_ids": [
                    i for i in result.contradicting_evidence_ids if i in known
                ],
            }
        )
    return out


def _undetermined(name: str, code: str) -> EvaluatorResult:
    backend = {
        "formal": BackendKind.SOLVER,
        "policy": BackendKind.RULES,
        "empirical": BackendKind.STATS,
        "causal": BackendKind.GRAPH,
        "utility": BackendKind.RULES,
    }.get(name, BackendKind.RULES)
    return EvaluatorResult(
        evaluator=name,
        verdict=Verdict.UNDETERMINED,
        confidence=0.0,
        reason_codes=[code],
        backend=backend,
    )


def _sanitize_isolated_crash(payload: object) -> str:
    text = str(payload).replace("\n", " ").strip()
    if "Traceback" in text:
        text = text.split("Traceback", 1)[0].strip() or "RuntimeError: isolated worker crashed"
    if len(text) > MAX_CRASH_MESSAGE:
        return text[: MAX_CRASH_MESSAGE - 3] + "..."
    return text


def _radar(
    results,
    crit,
    review_required,
    probes,
    evidence_conflicts,
    extra_questions,
    uncertainty=0.0,
    contradiction=0.0,
):
    axes = []
    for name in HEAD_ORDER:
        if name not in results:
            continue
        res = results[name]
        pol = verdict_polarity(res.verdict)
        axes.append(
            RadarAxis(
                evaluator=name,
                verdict=res.verdict,
                confidence=res.confidence,
                polarity=0.0 if pol is None else pol,
                hard_veto=res.hard_veto,
            )
        )
    unresolved = extra_questions[:]
    for res in results.values():
        unresolved.extend(res.unresolved_questions)
    hints: list[str] = []
    resolving = [p.resolving_condition for p in probes if p.resolving]
    if resolving:
        hints.extend(resolving[:3])
    else:
        ranked = sorted(probes, key=lambda p: p.delta_before - p.delta_after, reverse=True)
        hints.extend(p.resolving_condition for p in ranked[:3])
    return EpistemicRadarPayload(
        contradiction=contradiction,
        uncertainty=uncertainty,
        axes=axes,
        critical_pairs=[c.pair for c in crit],
        review_required=review_required,
        unresolved_questions=unresolved,
        counterfactual_hints=hints,
        evidence_conflict_count=len(evidence_conflicts),
    )
