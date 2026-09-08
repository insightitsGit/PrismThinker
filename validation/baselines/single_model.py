from typing import Protocol
from time import perf_counter
from validation.schemas.case import CaseInput, Verdict
from validation.schemas.result import Result, Usage, Status


def call_provider(provider, case):
    """Preserve individual exceptions so an incomplete panel is auditable."""
    started = perf_counter()
    try:
        result = provider.evaluate(case)
        result = Result.model_validate_json(result.model_dump_json())
        if result.case_id != case.case_id:
            raise ValueError("provider returned mismatched case ID")
    except Exception as exc:
        result = Result(case_id=case.case_id, system=type(provider).__name__,
                      status=Status.TIMEOUT if isinstance(exc, TimeoutError) else Status.ERROR,
                      error=f"{type(exc).__name__}: {exc}")
    result.latency_ms = (perf_counter()-started)*1000
    return result
from validation.prismthinker_eval.action_policy import action_for


class Model(Protocol):
    """Providers return raw output and complete usage, including failed calls."""
    def evaluate(self, case: CaseInput) -> Result: ...


class SingleModel:
    name = "single_model_mock"

    def __init__(self, provider: Model):
        self.provider = provider

    def evaluate(self, case):
        result = call_provider(self.provider, case)
        return result.model_copy(update={"system": self.name})


class FixtureModel:
    """Immutable predeclared responses keyed by ID, never reads labels."""
    def __init__(self, responses, index=0, seed=42):
        self.responses, self.index, self.seed = responses, index, seed

    def evaluate(self, case):
        sample = self.responses[case.case_id][self.index]
        usage = Usage(model_ids=[f"mock:fixture-{self.index}"], calls=1,
                      input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
                      temperature=0.0, seed=self.seed)
        try:
            verdict = Verdict(sample["verdict"])
            return Result(case_id=case.case_id, system=f"fixture-{self.index}", verdict=verdict,
                          confidence=sample["confidence"], reasoning=sample["reasoning"],
                          action=action_for(verdict, case), usage=usage, raw={"response": sample})
        except (ValueError, KeyError, TypeError) as exc:
            return Result(case_id=case.case_id, system=f"fixture-{self.index}", status=Status.ERROR,
                          usage=usage, raw={"response": sample}, error=f"{type(exc).__name__}: {exc}")
