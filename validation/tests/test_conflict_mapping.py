"""Public disposition must not disappear in the evaluation adapter."""
from types import SimpleNamespace

import pytest

from prismthinker.core.schemas import ReasoningDisposition, Verdict as CoreVerdict
from tests.conftest import cache_ttl_context
from prismthinker import PrismThinker
from validation.prismthinker_eval.adapter import PrismThinkerAdapter


@pytest.mark.parametrize("disposition,expected", [
    (ReasoningDisposition.CONFLICT, True),
    (ReasoningDisposition.CONSENSUS, False),
])
def test_adapter_preserves_disposition_without_critical_pairs(disposition, expected):
    graph = PrismThinker().evaluate(cache_ttl_context())
    graph = graph.model_copy(update={
        "disposition": disposition, "recommended_verdict": CoreVerdict.APPROVE,
        "critical_conflicts": [], "evidence_conflicts": [], "conflicting_assumptions": [],
        "review_required": False,
    })
    adapter = PrismThinkerAdapter()
    adapter.engine = SimpleNamespace(evaluate=lambda context: graph)
    case = SimpleNamespace(case_id="mapping-regression", reasoning_context=lambda: None)
    result = adapter.evaluate(case)
    assert result.conflict is expected
