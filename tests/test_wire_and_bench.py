from __future__ import annotations

from prismthinker import PresentationContext, PrismThinker
from prismthinker.adapters.chorusgraph import (
    ChorusGraphOrchestrateRequest,
    honor_envelope,
    to_chorusgraph,
)
from prismthinker.adapters.documents import RetrievedDocument, RetrieveRequest, from_documents
from prismthinker.core.schemas import ChorusGraphDirective
from bench.corpus import corpus_documents
from bench.neighbors import LocalChorusGraph, LocalRetriever
from bench.runner import bench_config, run_scenario, score_case
from bench.scenarios import all_scenarios, scenario_by_id
from tests.conftest import cache_ttl_context


def test_from_documents_maps_freshness_and_numeric() -> None:
    docs = [
        RetrievedDocument(
            id="d1",
            text="stale scrape",
            source="prom.checkout",
            score=0.4,
            metadata={"trust": 0.4, "freshness_hours": 288, "numeric_claims": {"p99_latency_ms": 110}},
        )
    ]
    ctx = from_documents("q", docs)
    assert ctx.evidence[0].freshness_hours == 288.0
    assert ctx.evidence[0].numeric_claims["p99_latency_ms"] == 110.0
    assert "numeric_claims" not in ctx.evidence[0].metadata


def test_honor_envelope_refuses_tools() -> None:
    graph = PrismThinker(bench_config()).evaluate(cache_ttl_context())
    envelope = to_chorusgraph(graph, allowed_tools=["apply_ttl"])
    assert envelope.directive is ChorusGraphDirective.REFUSE
    request = ChorusGraphOrchestrateRequest(
        envelope=envelope,
        requested_tools=["apply_ttl"],
        presentation=PresentationContext(user_id="operator"),
    )
    response, entry = honor_envelope(request, "j1")
    assert response.executed_tools == []
    assert response.blocked_reason is not None
    assert entry.directive is ChorusGraphDirective.REFUSE


def test_local_hybrid_retrieval_hits_privacy_docs() -> None:
    store = LocalRetriever()
    store.index(corpus_documents())
    response = store.retrieve(
        RetrieveRequest(
            query="Reduce cache_ttl stay at 60s for checkout PII retention and GDPR.",
            top_k=8,
        )
    )
    ids = {doc.id for doc in response.documents}
    assert "priv.retention.policy" in ids or "priv.ttl.60.incident" in ids
    assert response.backend == "memory"


def test_contract_scenarios_hold_on_local_wire() -> None:
    retriever = LocalRetriever()
    retriever.index(corpus_documents())
    orchestrator = LocalChorusGraph()
    thinker = PrismThinker(bench_config())
    contracts = [item for item in all_scenarios() if item.gold.contract]
    assert len(contracts) >= 8
    for scenario in contracts:
        row = run_scenario(scenario, thinker, retriever, orchestrator)
        assert row["contract_passed"], (scenario.id, row["checks"], row["disposition"], row["directive"])


def test_scenario_families_cover_the_lattice_and_neighbors() -> None:
    families = {family for item in all_scenarios() for family in item.gold.families}
    required = {
        "fast_path",
        "hard_veto",
        "conflict",
        "gather",
        "execute",
        "answer",
        "retrieval_contamination",
        "closed_context",
        "qualified",
        "evidence",
        "causal",
        "empirical",
        "formal",
        "privacy",
        "healthcare",
        "finance",
        "security",
        "legal",
        "sre",
        "science",
    }
    missing = required - families
    assert not missing
    assert len(all_scenarios()) >= 24
    assert "privacy_pii_cache_hard_veto" in scenario_by_id()


def test_score_case_flags_retrieval_miss() -> None:
    scenario = scenario_by_id()["privacy_pii_cache_hard_veto"]
    graph = PrismThinker(bench_config()).evaluate(scenario.seed.model_copy(update={"query": scenario.query}))
    envelope = to_chorusgraph(graph, allowed_tools=list(scenario.tools))
    checks = score_case(scenario, graph, envelope.directive.value, [], ["unrelated"])
    assert checks["retrieval"] is False
