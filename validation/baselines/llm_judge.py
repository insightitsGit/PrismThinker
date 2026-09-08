from typing import Protocol
from validation.schemas.case import CaseInput
from validation.schemas.result import Result, Status
from validation.baselines.single_model import call_provider


class Judge(Protocol):
    def judge(self, case: CaseInput, candidates: list[Result]) -> Result: ...


class LLMJudge:
    """Live extension point: pinned provider, candidate calls plus judge usage.

    Not enabled by the default mock experiment. No pretend LLM judge scores.
    Provider failures should be returned as Result, preserving raw text/usage.
    """
    name = "llm_judge"

    def __init__(self, providers, judge: Judge):
        self.providers, self.judge = providers, judge

    def evaluate(self, case):
        from validation.baselines.majority_vote import MajorityVote
        candidates = [call_provider(p, case) for p in self.providers]
        try:
            result = self.judge.judge(case, candidates)
            result = Result.model_validate_json(result.model_dump_json())
            if result.case_id != case.case_id:
                raise ValueError("judge returned mismatched case ID")
        except Exception as exc:
            result = Result(case_id=case.case_id, system=self.name,
                status=Status.TIMEOUT if isinstance(exc, TimeoutError) else Status.ERROR,
                error=f"{type(exc).__name__}: {exc}")
        all_results = candidates + [result]
        usage = result.usage.model_copy(update={
            "calls": MajorityVote.total(all_results, "calls"),
            "model_ids": [m for r in all_results for m in r.usage.model_ids],
            **{field: MajorityVote.total(all_results, field) for field in
               ("input_tokens", "output_tokens", "estimated_cost_usd")}})
        return result.model_copy(update={"system": self.name, "usage": usage,
            "raw": {"candidates": [r.model_dump(mode="json") for r in candidates],
                    "judge": result.model_dump(mode="json")}})
