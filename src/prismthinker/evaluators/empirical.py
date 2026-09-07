from __future__ import annotations

from statistics import mean, pstdev

from prismthinker.config import EngineConfig
from prismthinker.core.evidence import detect_evidence_conflicts
from prismthinker.classifier.features import EMPIRICAL_LEXEMES
from prismthinker.core.schemas import (
    AssumptionAtom,
    BackendKind,
    Citation,
    CitationKind,
    Claim,
    EvaluatorCapability,
    EvaluatorResult,
    Hypothesis,
    IndependenceClass,
    ReasoningContext,
    Verdict,
)
from prismthinker.evaluators.base import Evaluator

CAPABILITY = EvaluatorCapability(
    name="empirical",
    backend=BackendKind.STATS,
    independence_class=IndependenceClass.EMPIRICAL_STATS,
    may_hard_veto=False,
)

HIGH_TRUST = 0.60
PVALUE_KEYS = frozenset({"pvalue", "p_value", "p-value"})


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _trust_weighted(samples: list[tuple[float, float]]) -> float:
    weight = sum(max(trust, 1e-6) for _value, trust in samples)
    return sum(value * max(trust, 1e-6) for value, trust in samples) / weight


def _direction_for(key: str, context: ReasoningContext) -> str:
    if context.objective is not None:
        for term in context.objective.terms:
            if term.fact_key == key:
                return term.direction
    if key.lower() in PVALUE_KEYS:
        return "minimize"
    return "hit"


def _compare(observed: float, expected: float, direction: str, tol: float) -> str:
    if direction == "minimize":
        if observed <= expected + tol:
            return "meet"
        if observed <= expected + 3 * tol:
            return "near"
        return "miss"
    if direction == "maximize":
        if observed >= expected - tol:
            return "meet"
        if observed >= expected - 3 * tol:
            return "near"
        return "miss"
    err = abs(observed - expected)
    if err <= tol:
        return "meet"
    if err <= 3 * tol:
        return "near"
    return "miss"


class EmpiricalEvaluator(Evaluator):
    capability = CAPABILITY

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        premises: list[str] = []
        support: list[str] = []
        fact_values: dict[str, float] = {}
        evidence_samples: dict[str, list[tuple[float, float]]] = {}

        for key, fact in context.structured_facts.items():
            if _is_number(fact.value):
                fact_values[key] = float(fact.value)
                premises.append(key)

        known_ids = {ev.id for ev in context.evidence}
        for ev in context.evidence:
            for key, value in ev.numeric_claims.items():
                evidence_samples.setdefault(key, []).append((float(value), ev.trust))
                if ev.id in known_ids:
                    support.append(ev.id)

        payload = hypothesis.action.payload if hypothesis.action else {}
        targets: dict[str, float] = {}
        for key, value in payload.items():
            if _is_number(value) and (key in fact_values or key in evidence_samples):
                targets[key] = float(value)
        if context.objective is not None:
            for term in context.objective.terms:
                if term.target is not None and (
                    term.fact_key in fact_values or term.fact_key in evidence_samples
                ):
                    targets[term.fact_key] = float(term.target)

        if not fact_values and not evidence_samples:
            return EvaluatorResult(
                evaluator="empirical",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                unresolved_questions=["no numeric observations"],
                backend=BackendKind.STATS,
            )

        query_is_distribution = any(lex in context.query.lower() for lex in EMPIRICAL_LEXEMES)
        if not targets:
            return EvaluatorResult(
                evaluator="empirical",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                premise_ids=list(dict.fromkeys(premises)),
                supporting_evidence_ids=list(dict.fromkeys(support)),
                unresolved_questions=["no numeric threshold on hypothesis or objective"],
                backend=BackendKind.STATS,
            )

        conflicts = detect_evidence_conflicts(context, self.config)
        severe_keys: set[str] = set()
        for conflict in conflicts:
            if conflict.severity < 0.7:
                continue
            left = next((e for e in context.evidence if e.id == conflict.left_id), None)
            right = next((e for e in context.evidence if e.id == conflict.right_id), None)
            if left and right:
                severe_keys.update(set(left.numeric_claims) & set(right.numeric_claims))

        for key in targets:
            samples = [value for value, _trust in evidence_samples.get(key, [])]
            if key in fact_values:
                samples.append(fact_values[key])
            evidence_hits = len(evidence_samples.get(key, []))
            if query_is_distribution and len(samples) < 3:
                return EvaluatorResult(
                    evaluator="empirical",
                    verdict=Verdict.UNDETERMINED,
                    confidence=0.0,
                    premise_ids=list(dict.fromkeys(premises)),
                    supporting_evidence_ids=list(dict.fromkeys(support)),
                    unresolved_questions=[f"distribution claim on {key} needs at least 3 observations"],
                    backend=BackendKind.STATS,
                )
            if (
                not query_is_distribution
                and key not in fact_values
                and evidence_hits >= 2
                and len(samples) < 3
            ):
                return EvaluatorResult(
                    evaluator="empirical",
                    verdict=Verdict.UNDETERMINED,
                    confidence=0.0,
                    premise_ids=list(dict.fromkeys(premises)),
                    supporting_evidence_ids=list(dict.fromkeys(support)),
                    unresolved_questions=[f"distribution claim on {key} needs at least 3 observations"],
                    backend=BackendKind.STATS,
                )

        straddling = False
        reject = False
        caution = False
        claims: list[Claim] = []
        used_values: list[float] = []

        for key, expected in targets.items():
            ev_pairs = evidence_samples.get(key, [])
            if key in fact_values:
                observed = fact_values[key]
            elif ev_pairs:
                observed = _trust_weighted(ev_pairs)
            else:
                continue
            used_values.append(observed)
            spec = context.fact_specs.get(key)
            step = spec.step if spec is not None else None
            tol = step if step is not None else max(abs(expected) * 0.05, 1e-9)
            direction = _direction_for(key, context)
            ev_values = [value for value, _trust in ev_pairs]
            high_trust = [value for value, trust in ev_pairs if trust >= HIGH_TRUST]
            if key in severe_keys:
                pool = high_trust or ev_values
                if pool and (
                    (observed - expected) * (min(pool) - expected) < 0
                    or (observed - expected) * (max(pool) - expected) < 0
                ):
                    if high_trust and (
                        (min(high_trust) - expected) * (max(high_trust) - expected) < 0
                    ):
                        straddling = True
                    else:
                        caution = True
                else:
                    caution = True
            outcome = _compare(observed, expected, direction, tol)
            if outcome == "meet":
                claims.append(
                    Claim(
                        id=f"empirical-{key}",
                        evaluator="empirical",
                        statement=f"{key} meets threshold {expected}",
                        polarity=1.0,
                        confidence=0.55,
                        citations=[Citation(kind=CitationKind.FACT, ref=key)],
                        hypothesis_id=hypothesis.id,
                    )
                )
            elif outcome == "near":
                caution = True
                claims.append(
                    Claim(
                        id=f"empirical-{key}",
                        evaluator="empirical",
                        statement=f"{key} near threshold {expected}",
                        polarity=0.0,
                        confidence=0.4,
                        citations=[Citation(kind=CitationKind.FACT, ref=key)],
                        hypothesis_id=hypothesis.id,
                    )
                )
            else:
                reject = True
                claims.append(
                    Claim(
                        id=f"empirical-{key}",
                        evaluator="empirical",
                        statement=f"{key} misses threshold {expected}",
                        polarity=-1.0,
                        confidence=0.55,
                        citations=[Citation(kind=CitationKind.FACT, ref=key)],
                        hypothesis_id=hypothesis.id,
                    )
                )

        if straddling:
            return EvaluatorResult(
                evaluator="empirical",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                claims=claims,
                supporting_evidence_ids=list(dict.fromkeys(support)),
                premise_ids=list(dict.fromkeys(premises)),
                unresolved_questions=["severe evidence conflict straddles threshold"],
                backend=BackendKind.STATS,
            )

        cv = 0.0
        ev_all = [value for pairs in evidence_samples.values() for value, _trust in pairs]
        largest = ev_all or used_values
        if len(largest) >= 3:
            mu = mean(largest)
            if mu != 0:
                cv = abs(pstdev(largest) / mu)
            confidence = 1.0 - min(1.0, cv)
        elif severe_keys:
            confidence = 0.3
        else:
            confidence = 0.55

        if reject:
            verdict = Verdict.REJECT
        elif caution:
            verdict = Verdict.CAUTION
        else:
            verdict = Verdict.APPROVE

        assumptions = [
            AssumptionAtom(
                id=f"empirical-obs-{key}",
                predicate=f"observed({key})",
                polarity=key not in severe_keys,
            )
            for key in targets
        ]
        return EvaluatorResult(
            evaluator="empirical",
            verdict=verdict,
            confidence=confidence,
            claims=claims,
            supporting_evidence_ids=list(dict.fromkeys(support)),
            premise_ids=list(dict.fromkeys(premises)),
            assumptions=assumptions,
            backend=BackendKind.STATS,
        )
