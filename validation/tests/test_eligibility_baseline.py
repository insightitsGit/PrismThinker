from types import SimpleNamespace
from validation.baselines.eligibility import EligibilityBaseline
from tests.conftest import cache_ttl_context


def test_shared_gate_baseline_refuses_without_evaluator_voting():
    case = SimpleNamespace(case_id="baseline", reasoning_context=cache_ttl_context)
    result = EligibilityBaseline().evaluate(case)
    assert result.action.value == "REFUSE"
    assert result.usage.calls == 0
    assert result.raw["eligibility"]["checks"]
