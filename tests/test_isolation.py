from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.engine import materialize_hypothesis
from prismthinker.core.isolation import run_head_isolated, run_in_process, sleep_worker
from prismthinker.core.schemas import ReasoningContext, Verdict


def test_run_in_process_terminates_hung_worker() -> None:
    status, payload = run_in_process(sleep_worker, (30.0,), timeout_s=0.3)
    assert status == "timeout"
    assert payload is None


def test_isolated_standard_head_returns_result() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    status, result, message = run_head_isolated(
        "formal",
        context,
        hypothesis,
        EngineConfig(),
        15.0,
    )
    assert status == "ok"
    assert result is not None
    assert result.evaluator == "formal"
    assert result.verdict is not Verdict.UNDETERMINED or result.reason_codes
    assert message == ""
