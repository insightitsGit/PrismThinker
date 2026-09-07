from __future__ import annotations

from prismthinker import PrismThinker
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.adapters.vectorprism import VectorPrismDocument, from_vectorprism
from prismthinker.core.schemas import (
    ChorusGraphDirective,
    FactSpec,
    FactType,
    ReasoningContext,
    ReasoningDisposition,
    Verdict,
)
from prismthinker.reason_codes import REASON_SELECTOR_OVERLAY
from tests.conftest import cache_ttl_context


def test_hard_veto_refuses_with_empty_tools() -> None:
    graph = PrismThinker().evaluate(cache_ttl_context())
    assert graph.disposition is ReasoningDisposition.HARD_VETO
    envelope = to_chorusgraph(graph, allowed_tools=["delete_cache", "ship"])
    assert envelope.directive is ChorusGraphDirective.REFUSE
    assert envelope.allowed_tools == []


def test_review_promotes_execute_to_escalate() -> None:
    graph = PrismThinker().evaluate(cache_ttl_context())
    graph.disposition = ReasoningDisposition.CONSENSUS
    graph.recommended_verdict = Verdict.APPROVE
    graph.review_required = True
    envelope = to_chorusgraph(graph, allowed_tools=["ship"])
    assert envelope.directive is ChorusGraphDirective.ESCALATE
    assert envelope.allowed_tools == []


def test_vectorprism_lifts_structured_bindings() -> None:
    ctx = from_vectorprism(
        "query",
        [
            VectorPrismDocument(
                id="d-rule",
                text="policy",
                source="policy.privacy",
                metadata={
                    "policy_rule": {
                        "id": "pii-cache",
                        "modality": "prohibition",
                        "predicate": "fact.cache_ttl >= 30",
                        "severity": "hard_veto",
                    },
                    "causal_graph": {
                        "nodes": ["cache_ttl", "p99_latency_ms"],
                        "edges": [
                            {
                                "source": "cache_ttl",
                                "target": "p99_latency_ms",
                                "signed": -1,
                                "edge_id": "e1",
                            }
                        ],
                    },
                },
            )
        ],
    )
    assert ctx.policy_rules[0].id == "pii-cache"
    assert ctx.causal_graph is not None
    assert ctx.causal_graph.edges[0].edge_id == "e1"


def test_vectorprism_maps_evidence() -> None:
    ctx = from_vectorprism(
        "query",
        [
            VectorPrismDocument(
                id="d1",
                text="hello",
                source="idx",
                score=0.8,
                metadata={"numeric_claims": {"n": 3}},
            )
        ],
    )
    assert ctx.evidence[0].id == "d1"
    assert ctx.evidence[0].trust == 0.8
    assert ctx.evidence[0].numeric_claims["n"] == 3.0
    assert ctx.evidence[0].provenance_hash


def test_gather_fact_keys_from_missing_required() -> None:
    graph = PrismThinker().evaluate(
        ReasoningContext(
            query="hello there general case",
            fact_specs={
                "need_me": FactSpec(key="need_me", fact_type=FactType.INT, required=True)
            },
        )
    )
    envelope = to_chorusgraph(graph)
    assert envelope.directive is ChorusGraphDirective.GATHER
    assert "need_me" in envelope.gather_fact_keys


def test_selector_codes_reach_the_graph() -> None:
    graph = PrismThinker().evaluate(cache_ttl_context())
    assert REASON_SELECTOR_OVERLAY in graph.classifier.reason_codes
