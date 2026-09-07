from __future__ import annotations

from prismthinker import PrismThinker
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.adapters.documents import RetrievedDocument, from_documents, from_langchain, from_llamaindex
from prismthinker.adapters.vectorprism import VectorPrismDocument, from_vectorprism
from prismthinker.config import EngineConfig
from prismthinker.core.evidence import detect_evidence_conflicts
from prismthinker.core.schemas import (
    ChorusGraphDirective,
    EvidenceConflictType,
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


def test_from_documents_lifts_structured_bindings() -> None:
    ctx = from_documents(
        "query",
        [
            RetrievedDocument(
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


def test_from_documents_maps_evidence_rank_as_trust_fallback() -> None:
    ctx = from_documents(
        "query",
        [
            RetrievedDocument(
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


def test_metadata_trust_beats_retrieval_score() -> None:
    ctx = from_documents(
        "query",
        [
            RetrievedDocument(
                id="d1",
                text="hello",
                source="idx",
                score=0.99,
                metadata={"trust": 0.2},
            )
        ],
    )
    assert ctx.evidence[0].trust == 0.2


def test_from_langchain_duck_types_page_content() -> None:
    class LCDoc:
        def __init__(self) -> None:
            self.page_content = "PII TTL must stay under 30s"
            self.metadata = {"source": "policy.privacy", "trust": 0.9}
            self.id = "lc-1"

    ctx = from_langchain("query", [LCDoc()])
    assert ctx.evidence[0].id == "lc-1"
    assert ctx.evidence[0].content.startswith("PII")
    assert ctx.evidence[0].source == "policy.privacy"
    assert ctx.evidence[0].trust == 0.9


def test_from_llamaindex_duck_types_node_with_score() -> None:
    class Node:
        def __init__(self) -> None:
            self.text = "incident review"
            self.metadata = {"source": "sre.wiki"}
            self.id_ = "li-1"

    class NodeWithScore:
        def __init__(self) -> None:
            self.node = Node()
            self.score = 0.4

    ctx = from_llamaindex("query", [NodeWithScore()])
    assert ctx.evidence[0].id == "li-1"
    assert ctx.evidence[0].trust == 0.4
    assert ctx.evidence[0].source == "sre.wiki"


def test_vectorprism_names_are_aliases() -> None:
    assert VectorPrismDocument is RetrievedDocument
    ctx = from_vectorprism(
        "query",
        [VectorPrismDocument(id="d1", text="hello", source="idx", score=0.5)],
    )
    assert ctx.evidence[0].id == "d1"


def test_from_vectorprism_maps_trust_numeric_claims_and_negates_id() -> None:
    ctx = from_vectorprism(
        "did the retrieval invert a claim",
        [
            VectorPrismDocument(
                id="a",
                text="latency is 10ms",
                source="vectorprism",
                score=0.91,
                metadata={"numeric_claims": {"latency_ms": 10}},
            ),
            VectorPrismDocument(
                id="b",
                text="latency is not 10ms",
                source="vectorprism",
                score=0.40,
                metadata={
                    "trust": 0.22,
                    "numeric_claims": {"latency_ms": 40},
                    "negates_id": "a",
                },
            ),
            VectorPrismDocument(
                id="c",
                text="third observation also inverts a",
                source="vectorprism",
                score=0.3,
                metadata={"negates_ids": ["a"]},
            ),
        ],
    )
    by_id = {item.id: item for item in ctx.evidence}
    assert by_id["a"].content == "latency is 10ms"
    assert by_id["a"].trust == 0.91
    assert by_id["a"].numeric_claims["latency_ms"] == 10.0
    assert by_id["b"].trust == 0.22
    assert by_id["b"].numeric_claims["latency_ms"] == 40.0
    assert by_id["b"].metadata["negates_id"] == "a"
    assert by_id["c"].metadata["negates_ids"] == ["a"]
    conflicts = detect_evidence_conflicts(ctx, EngineConfig())
    negation = {
        frozenset({c.left_id, c.right_id})
        for c in conflicts
        if c.conflict_type is EvidenceConflictType.EXPLICIT_NEGATION
    }
    assert frozenset({"a", "b"}) in negation
    assert frozenset({"a", "c"}) in negation


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
