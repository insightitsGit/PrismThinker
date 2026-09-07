from __future__ import annotations

from prismthinker import PrismThinker, ReasoningContext
from prismthinker.classifier.ast_safe import probe_expression


def test_simple_arithmetic_fast_path() -> None:
    assert probe_expression("2 + 2").eligible
    assert probe_expression("2 + 2").value == 4
    assert probe_expression("(12 * 8) / 4").eligible
    assert probe_expression("(12 * 8) / 4").value == 24


def test_unsafe_and_mixed_rejected() -> None:
    assert probe_expression("os.system('ls')").eligible is False
    assert probe_expression("__import__('os')").eligible is False
    assert probe_expression("2 % 3").eligible is False
    assert probe_expression("2 + 2 and delete PII").eligible is False
    assert probe_expression("is 2+2 legal to cache?").eligible is False


def test_division_by_zero_is_ast_not_substring() -> None:
    attempt = probe_expression("1 / 0")
    assert attempt.eligible is False
    assert attempt.division_by_zero is True
    from prismthinker.core.schemas import Hypothesis
    from prismthinker.evaluators.formal import FormalEvaluator
    from prismthinker.core.schemas import Verdict

    out = FormalEvaluator().evaluate(
        ReasoningContext(query="1 / 0"),
        Hypothesis(id="h", statement="1 / 0 is well-defined"),
    )
    assert out.verdict is Verdict.REJECT
    assert "REASON_DIVISION_BY_ZERO" in out.reason_codes


def test_engine_fast_path_envelope() -> None:
    graph = PrismThinker().evaluate(ReasoningContext(query="(12 * 8) / 4"))
    assert graph.fast_path is not None
    assert graph.selected_evaluators == ["axiomatic"]
    assert graph.contradiction_score == 0.0
    assert graph.uncertainty_score == 0.0
