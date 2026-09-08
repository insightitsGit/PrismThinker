"""Shared-gate ablation: deterministic checks without multi-head voting or Delta.

This shares implementation with PrismThinker and is not an independent oracle.
"""
from time import perf_counter
from prismthinker.core.eligibility import assess_eligibility
from prismthinker.core.engine import materialize_hypothesis
from validation.schemas.result import Action, Result, Usage
from validation.schemas.case import Verdict


class EligibilityBaseline:
    name = "eligibility_only"

    def evaluate(self, case):
        started = perf_counter()
        context = case.reasoning_context()
        gate, signals, shadow, _ = assess_eligibility(context, materialize_hypothesis(context))
        if gate.directive is not None:
            action = Action(gate.directive.value.upper())
        elif any(c.status == "pass" for c in gate.checks):
            hypothesis = materialize_hypothesis(context)
            action = Action.EXECUTE if hypothesis.action and hypothesis.action.kind.value != "assertion" else Action.ANSWER
        else:
            action = Action.GATHER
        verdict = {Action.EXECUTE: Verdict.APPROVE, Action.ANSWER: Verdict.APPROVE,
                   Action.REFUSE: Verdict.REJECT, Action.ESCALATE: Verdict.CAUTION,
                   Action.GATHER: Verdict.UNDETERMINED}[action]
        return Result(case_id=case.case_id, system=self.name, action=action, verdict=verdict,
            confidence=0.0 if action in {Action.GATHER, Action.ESCALATE} else 1.0,
            conflict=signals.material_evidence_conflict or signals.policy_authority_conflict,
            latency_ms=(perf_counter()-started)*1000,
            reasoning="Shared deterministic eligibility gate; no voting or Delta; confidence is not calibrated.",
            usage=Usage(calls=0, input_tokens=0, output_tokens=0, estimated_cost_usd=0.0),
            raw={"eligibility":gate.model_dump(mode="json"), "conflict_signals":signals.model_dump(mode="json"),
                 "aligned_delta":shadow.model_dump(mode="json")})
