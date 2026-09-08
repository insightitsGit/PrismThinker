from __future__ import annotations

from prismthinker.classifier.ast_safe import probe_expression
from prismthinker.core.predicates import evaluate_predicate
from prismthinker.core.schemas import (
    AssumptionAtom,
    BackendKind,
    Citation,
    CitationKind,
    Claim,
    ConstraintApplication,
    ConstraintStatus,
    EvaluatorCapability,
    EvaluatorResult,
    FactSpec,
    FactType,
    Hypothesis,
    IndependenceClass,
    ReasoningContext,
    Verdict,
)
from prismthinker.evaluators.base import Evaluator
from prismthinker.reason_codes import REASON_DIVISION_BY_ZERO, REASON_UNBOUND_PATH, REASON_CONSTRAINT_INCOMPLETE

CAPABILITY = EvaluatorCapability(
    name="formal",
    backend=BackendKind.SOLVER,
    independence_class=IndependenceClass.FORMAL_SYMBOLIC,
    may_hard_veto=False,
)


def _type_ok(spec: FactSpec, value: object) -> bool:
    if spec.fact_type is FactType.BOOL:
        return isinstance(value, bool)
    if spec.fact_type is FactType.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if spec.fact_type is FactType.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if spec.fact_type is FactType.DURATION_MS:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if spec.fact_type is FactType.ENUM:
        return str(value) in spec.enum_values
    if spec.fact_type is FactType.STRING:
        return isinstance(value, str)
    return True


def _range_ok(spec: FactSpec, value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return True
    if spec.minimum is not None and value < spec.minimum:
        return False
    if spec.maximum is not None and value > spec.maximum:
        return False
    return True


class FormalEvaluator(Evaluator):
    capability = CAPABILITY

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        facts = context.structured_facts
        specs = context.fact_specs
        constraints = context.constraints
        action = hypothesis.action

        claims: list[Claim] = []
        applied: list[ConstraintApplication] = []
        premises: list[str] = []
        questions: list[str] = []
        codes: list[str] = []
        assumptions: list[AssumptionAtom] = []
        rejected = False
        unbound = False
        optional_missing = False

        if probe_expression(context.query).division_by_zero:
            codes.append(REASON_DIVISION_BY_ZERO)
            rejected = True

        for key, spec in specs.items():
            if key not in facts:
                if spec.required:
                    unbound = True
                    questions.append(f"missing required fact {key}")
                else:
                    optional_missing = True
                continue
            premises.append(key)
            value = facts[key].value
            valid = _type_ok(spec, value) and _range_ok(spec, value)
            assumptions.append(
                AssumptionAtom(
                    id=f"formal-typed-{key}",
                    predicate=f"typed(fact.{key})",
                    polarity=valid,
                )
            )
            if not valid:
                rejected = True
                claims.append(
                    Claim(
                        id=f"formal-type-{key}",
                        evaluator="formal",
                        statement=f"fact {key} violates FactSpec",
                        polarity=-1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.FACT, ref=key)],
                        hypothesis_id=hypothesis.id,
                    )
                )

        for key, fact in facts.items():
            if key in specs:
                continue
            premises.append(key)
            assumptions.append(
                AssumptionAtom(
                    id=f"formal-opaque-{key}",
                    predicate=f"opaque(fact.{key})",
                    polarity=True,
                    confidence=0.6,
                )
            )
            _ = fact

        for constraint in constraints:
            result = evaluate_predicate(constraint.predicate, facts, action)
            premises.extend(result.cited_fact_keys)
            if result.unbound:
                unbound = True
                codes.append(REASON_UNBOUND_PATH)
                questions.append(f"unbound path in constraint {constraint.id}")
                applied.append(
                    ConstraintApplication(
                        constraint_id=constraint.id,
                        status=ConstraintStatus.UNCHECKED,
                        cited_fact_keys=list(result.cited_fact_keys),
                    )
                )
                continue
            if result.error:
                unbound = True
                codes.append(REASON_CONSTRAINT_INCOMPLETE)
                questions.append(f"constraint {constraint.id} predicate error: {result.error}")
                applied.append(ConstraintApplication(
                    constraint_id=constraint.id, status=ConstraintStatus.UNCHECKED,
                    cited_fact_keys=list(result.cited_fact_keys)))
                continue
            satisfied = bool(result.value)
            assumptions.append(
                AssumptionAtom(
                    id=f"formal-a-{constraint.id}",
                    predicate=constraint.predicate,
                    polarity=satisfied,
                )
            )
            if result.error or result.value is False:
                rejected = True
                applied.append(
                    ConstraintApplication(
                        constraint_id=constraint.id,
                        status=ConstraintStatus.VIOLATED,
                        cited_fact_keys=list(result.cited_fact_keys),
                    )
                )
                claims.append(
                    Claim(
                        id=f"formal-c-{constraint.id}",
                        evaluator="formal",
                        statement=f"constraint {constraint.id} is not satisfied",
                        polarity=-1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.CONSTRAINT, ref=constraint.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
                continue
            applied.append(
                ConstraintApplication(
                    constraint_id=constraint.id,
                    status=ConstraintStatus.SATISFIED,
                    cited_fact_keys=list(result.cited_fact_keys),
                )
            )

        if unbound and not rejected:
            return EvaluatorResult(
                evaluator="formal",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                claims=claims,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                constraints_applied=applied,
                unresolved_questions=questions,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.SOLVER,
            )

        if rejected:
            if not claims:
                claims.append(
                    Claim(
                        id="formal-reject",
                        evaluator="formal",
                        statement="structurally invalid",
                        polarity=-1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
            return EvaluatorResult(
                evaluator="formal",
                verdict=Verdict.REJECT,
                confidence=1.0,
                claims=claims,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                constraints_applied=applied,
                unresolved_questions=questions,
                hard_veto=False,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.SOLVER,
            )

        confidence = 0.6 if optional_missing else 1.0
        claims.append(
            Claim(
                id="formal-ok",
                evaluator="formal",
                statement="state is structurally valid",
                polarity=1.0,
                confidence=confidence,
                citations=[Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)],
                hypothesis_id=hypothesis.id,
            )
        )
        return EvaluatorResult(
            evaluator="formal",
            verdict=Verdict.APPROVE,
            confidence=confidence,
            claims=claims,
            premise_ids=list(dict.fromkeys(premises)),
            assumptions=assumptions,
            constraints_applied=applied,
            unresolved_questions=questions,
            hard_veto=False,
            reason_codes=list(dict.fromkeys(codes)),
            backend=BackendKind.SOLVER,
        )
