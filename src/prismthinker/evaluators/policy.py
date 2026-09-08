from __future__ import annotations

from prismthinker.classifier.features import POLICY_DOMAINS
from prismthinker.core.predicates import evaluate_predicate
from prismthinker.core.schemas import (
    AssumptionAtom,
    BackendKind,
    Citation,
    CitationKind,
    Claim,
    DeonticModality,
    EvaluatorCapability,
    EvaluatorResult,
    Hypothesis,
    IndependenceClass,
    ReasoningContext,
    RuleSeverity,
    Verdict,
)
from prismthinker.evaluators.base import Evaluator
from prismthinker.reason_codes import (
    REASON_MISSING_POLICY_RULES,
    REASON_POLICY_INCOMPLETE,
    REASON_UNBOUND_PATH,
    REASON_UNSTRUCTURED_RULE_IGNORED,
)

CAPABILITY = EvaluatorCapability(
    name="policy",
    backend=BackendKind.RULES,
    independence_class=IndependenceClass.POLICY_DEONTIC,
    may_hard_veto=True,
)


class PolicyEvaluator(Evaluator):
    capability = CAPABILITY

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        # Intentionally never treats context.constraints as deontic.
        rules = context.policy_rules
        domain = (context.domain or "").lower()
        extra_codes = [REASON_UNSTRUCTURED_RULE_IGNORED] if context.rules else []
        if not rules:
            if domain not in POLICY_DOMAINS:
                return EvaluatorResult(
                    evaluator="policy",
                    verdict=Verdict.UNDETERMINED,
                    confidence=0.0,
                    unresolved_questions=["no PolicyRule objects provided"],
                    reason_codes=[REASON_MISSING_POLICY_RULES, *extra_codes],
                    backend=BackendKind.RULES,
                )
            return EvaluatorResult(
                evaluator="policy",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                unresolved_questions=["policy domain overlay without PolicyRule objects"],
                reason_codes=[REASON_MISSING_POLICY_RULES, *extra_codes],
                backend=BackendKind.RULES,
            )

        claims: list[Claim] = []
        premises: list[str] = []
        questions: list[str] = []
        codes: list[str] = list(extra_codes)
        assumptions: list[AssumptionAtom] = []
        veto = False
        block = False
        caution = False
        permission_only = False

        for rule in rules:
            result = evaluate_predicate(rule.predicate, context.structured_facts, hypothesis.action)
            premises.append(rule.id)
            premises.extend(result.cited_fact_keys)
            if result.unbound:
                codes.append(REASON_POLICY_INCOMPLETE)
                codes.append(REASON_UNBOUND_PATH)
                questions.append(f"unbound path in rule {rule.id}")
                continue
            if result.error:
                codes.append(REASON_POLICY_INCOMPLETE)
                questions.append(f"rule {rule.id} predicate error: {result.error}")
                continue

            matched = bool(result.value)
            assumptions.append(
                AssumptionAtom(
                    id=f"policy-a-{rule.id}",
                    predicate=rule.predicate,
                    polarity=matched,
                )
            )
            if rule.modality is DeonticModality.PROHIBITION and matched:
                claims.append(
                    Claim(
                        id=f"policy-{rule.id}",
                        evaluator="policy",
                        statement=f"prohibition {rule.id} matches",
                        polarity=-1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.RULE, ref=rule.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
                if rule.severity is RuleSeverity.HARD_VETO:
                    veto = True
                    block = True
                    break
                if rule.severity is RuleSeverity.BLOCK:
                    block = True
                else:
                    caution = True
            elif rule.modality is DeonticModality.OBLIGATION and not matched:
                claims.append(
                    Claim(
                        id=f"policy-{rule.id}",
                        evaluator="policy",
                        statement=f"obligation {rule.id} is unmet",
                        polarity=-1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.RULE, ref=rule.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
                if rule.severity is RuleSeverity.HARD_VETO:
                    veto = True
                    block = True
                    break
                if rule.severity is RuleSeverity.BLOCK:
                    block = True
                else:
                    caution = True
            elif rule.modality is DeonticModality.PERMISSION and matched:
                permission_only = True
                claims.append(
                    Claim(
                        id=f"policy-{rule.id}",
                        evaluator="policy",
                        statement=f"permission {rule.id} matches",
                        polarity=1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.RULE, ref=rule.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )

        if veto or block:
            return EvaluatorResult(
                evaluator="policy",
                verdict=Verdict.REJECT,
                confidence=1.0,
                claims=claims,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                unresolved_questions=questions,
                hard_veto=veto,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.RULES,
            )
        if caution:
            if not claims:
                claims.append(
                    Claim(
                        id="policy-caution",
                        evaluator="policy",
                        statement="policy caution",
                        polarity=0.0,
                        confidence=0.7,
                        citations=[Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
            else:
                for claim in claims:
                    claim.polarity = 0.0
            return EvaluatorResult(
                evaluator="policy",
                verdict=Verdict.CAUTION,
                confidence=0.7,
                claims=claims,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                unresolved_questions=questions,
                hard_veto=False,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.RULES,
            )
        # A skipped rule is unknown, not a proof that no prohibition applies.
        # Preserve proven rejection/caution above; never approve incomplete checks.
        if REASON_POLICY_INCOMPLETE in codes:
            return EvaluatorResult(
                evaluator="policy",
                verdict=Verdict.UNDETERMINED,
                confidence=0.0,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                unresolved_questions=questions,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.RULES,
            )
        if permission_only or rules:
            if not claims:
                claims.append(
                    Claim(
                        id="policy-ok",
                        evaluator="policy",
                        statement="no prohibition matched",
                        polarity=1.0,
                        confidence=1.0,
                        citations=[Citation(kind=CitationKind.HYPOTHESIS, ref=hypothesis.id)],
                        hypothesis_id=hypothesis.id,
                    )
                )
            return EvaluatorResult(
                evaluator="policy",
                verdict=Verdict.APPROVE,
                confidence=1.0,
                claims=claims,
                premise_ids=list(dict.fromkeys(premises)),
                assumptions=assumptions,
                unresolved_questions=questions,
                hard_veto=False,
                reason_codes=list(dict.fromkeys(codes)),
                backend=BackendKind.RULES,
            )
        return EvaluatorResult(
            evaluator="policy",
            verdict=Verdict.UNDETERMINED,
            confidence=0.0,
            unresolved_questions=questions,
            assumptions=assumptions,
            reason_codes=list(dict.fromkeys(codes + [REASON_MISSING_POLICY_RULES])),
            backend=BackendKind.RULES,
        )
