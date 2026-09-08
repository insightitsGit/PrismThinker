from __future__ import annotations

from prismthinker import PrismThinker, __version__
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.config import DEFAULT_CONFIG_HASH, EngineConfig, config_hash
from prismthinker.core.schemas import ChorusGraphDirective, ReasoningDisposition, Verdict
from tests.conftest import cache_ttl_context


def test_package_version() -> None:
    assert __version__ == "1.2.0"


def test_worked_example_cache_ttl() -> None:
    graph = PrismThinker().evaluate(cache_ttl_context())
    assert graph.disposition is ReasoningDisposition.HARD_VETO
    assert graph.recommended_verdict is Verdict.REJECT
    assert graph.evaluators["policy"].verdict is Verdict.REJECT
    assert graph.evaluators["policy"].hard_veto is True
    assert graph.evaluators["formal"].verdict is Verdict.APPROVE
    assert graph.evaluators["formal"].hard_veto is False
    assert graph.evaluators["utility"].verdict is Verdict.APPROVE
    assert graph.contradiction_score > 0.40
    assert any(p.parameter_changed == "cache_ttl" and p.resolving for p in graph.counterfactuals)
    envelope = to_chorusgraph(graph, allowed_tools=["apply_ttl"])
    assert envelope.directive is ChorusGraphDirective.REFUSE
    assert envelope.allowed_tools == []
    assert graph.radar.axes
    assert graph.evaluators["formal"].assumptions
    assert graph.evaluators["policy"].assumptions
    assert graph.evaluators["utility"].assumptions
    assert graph.config_hash == DEFAULT_CONFIG_HASH


def test_config_hash_stable() -> None:
    assert config_hash(EngineConfig()) == DEFAULT_CONFIG_HASH
    assert config_hash(EngineConfig()) == config_hash(EngineConfig())
    other = EngineConfig()
    other.selector.fill_order = ["utility", "formal", "policy", "empirical", "causal"]
    assert config_hash(other) != DEFAULT_CONFIG_HASH


def test_determinism() -> None:
    thinker = PrismThinker()
    ctx = cache_ttl_context()
    a = thinker.evaluate(ctx)
    b = thinker.evaluate(ctx)
    assert a.disposition == b.disposition
    assert a.recommended_verdict == b.recommended_verdict
    assert a.contradiction_score == b.contradiction_score
    assert a.uncertainty_score == b.uncertainty_score
    assert {k: v.verdict for k, v in a.evaluators.items()} == {
        k: v.verdict for k, v in b.evaluators.items()
    }


def test_byte_stable_non_llm_fields() -> None:
    thinker = PrismThinker()
    ctx = cache_ttl_context()
    a = thinker.evaluate(ctx)
    b = thinker.evaluate(ctx)
    assert a.config_hash == b.config_hash == DEFAULT_CONFIG_HASH
    stable_a = {
        "disposition": a.disposition.value,
        "recommended_verdict": None if a.recommended_verdict is None else a.recommended_verdict.value,
        "delta": a.contradiction_score,
        "uncertainty": a.uncertainty_score,
        "verdicts": {name: result.verdict.value for name, result in a.evaluators.items()},
    }
    stable_b = {
        "disposition": b.disposition.value,
        "recommended_verdict": None if b.recommended_verdict is None else b.recommended_verdict.value,
        "delta": b.contradiction_score,
        "uncertainty": b.uncertainty_score,
        "verdicts": {name: result.verdict.value for name, result in b.evaluators.items()},
    }
    assert stable_a == stable_b
