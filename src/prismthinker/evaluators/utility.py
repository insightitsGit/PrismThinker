from __future__ import annotations

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
from prismthinker.reason_codes import REASON_MISSING_OBJECTIVE, REASON_UNBOUND_PATH

CAPABILITY = EvaluatorCapability(
    name="utility",
    backend=BackendKind.RULES,
    independence_class=IndependenceClass.UTILITY_OBJECTIVE,
    may_hard_veto=False,
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class UtilityEvaluator(Evaluator):
    capability = CAPABILITY

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        objective = context.objective
        if objective is None:
            return EvaluatorResult(
                evaluator="utility",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                unresolved_questions=["ObjectiveSpec is required"],
                reason_codes=[REASON_MISSING_OBJECTIVE],
                backend=BackendKind.RULES,
            )

        scores: list[tuple[float, float]] = []
        premises: list[str] = []
        sla_reject = False
        questions: list[str] = []

        for term in objective.terms:
            fact = context.structured_facts.get(term.fact_key)
            if fact is None or not _is_number(fact.value):
                questions.append(f"missing fact {term.fact_key}")
                return EvaluatorResult(
                    evaluator="utility",
                    verdict=Verdict.UNDETERMINED,
                    confidence=0.0,
                    unresolved_questions=questions,
                    reason_codes=[REASON_UNBOUND_PATH, REASON_MISSING_OBJECTIVE],
                    backend=BackendKind.RULES,
                )
            x = float(fact.value)
            premises.append(term.fact_key)
            spec = context.fact_specs.get(term.fact_key)
            lo = spec.minimum if spec and spec.minimum is not None else 0.0
            if spec and spec.maximum is not None:
                hi = spec.maximum
            elif term.target is not None:
                hi = max(abs(term.target) * 2.0, abs(x), 1.0)
            else:
                hi = max(abs(x) * 2.0, 1.0)
            span = hi - lo if hi != lo else 1.0
            if term.direction == "maximize":
                norm = (x - lo) / span
            elif term.direction == "minimize":
                norm = 1.0 - (x - lo) / span
            else:
                target = term.target if term.target is not None else x
                norm = 1.0 - abs(x - target) / span
            norm = max(0.0, min(1.0, norm))
            scores.append((term.weight, norm))
            if term.sla_breach_is_reject and term.target is not None:
                if term.direction == "minimize" and x > term.target:
                    sla_reject = True
                if term.direction == "maximize" and x < term.target:
                    sla_reject = True
                if term.direction == "hit" and abs(x - term.target) > span * 0.1:
                    sla_reject = True

        weight_sum = sum(abs(w) for w, _ in scores) or 1.0
        utility = sum(w * n for w, n in scores) / weight_sum

        if sla_reject or (objective.reject_below is not None and utility < objective.reject_below):
            verdict = Verdict.REJECT
            polarity = -1.0
        elif objective.caution_below is not None and utility < objective.caution_below:
            verdict = Verdict.CAUTION
            polarity = 0.0
        else:
            verdict = Verdict.APPROVE
            polarity = 1.0

        assumptions = [
            AssumptionAtom(
                id=f"utility-{term.fact_key}",
                predicate=f"objective({term.fact_key},{term.direction})",
                polarity=True,
            )
            for term in objective.terms
        ]
        return EvaluatorResult(
            evaluator="utility",
            verdict=verdict,
            confidence=0.8,
            claims=[
                Claim(
                    id="utility-score",
                    evaluator="utility",
                    statement=f"objective score {utility:.4f}",
                    polarity=polarity,
                    confidence=0.8,
                    citations=[Citation(kind=CitationKind.FACT, ref=premises[0])],
                    hypothesis_id=hypothesis.id,
                )
            ],
            premise_ids=list(dict.fromkeys(premises)),
            assumptions=assumptions,
            hard_veto=False,
            backend=BackendKind.RULES,
        )
