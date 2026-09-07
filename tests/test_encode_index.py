from __future__ import annotations

from bench.encode import DIM, cosine, embed
from bench.index import EvidenceIndex
from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    Hypothesis,
    ReasoningContext,
)


def test_embed_is_unit_and_self_similar() -> None:
    vec = embed("cache_ttl 30 seconds privacy")
    assert len(vec) == DIM
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-9
    assert cosine(vec, vec) > 0.99
    assert cosine(vec, embed("unrelated astronomy nebula")) < cosine(
        vec, embed("privacy cache ttl seconds")
    )


def test_evidence_index_chunks_embeds_and_retrieves() -> None:
    index = EvidenceIndex()
    index.add_text(
        "Privacy control: checkout cache_ttl of 30 seconds when contains_pii is true.",
        source="policy.privacy",
    )
    index.add_text(
        "SRE runbook: p99 latency 900ms on checkout after a deploy.",
        source="prom.checkout",
    )
    hits = index.search("reduce cache_ttl for checkout PII", top_k=2)
    assert hits
    assert hits[0].source.startswith("policy")
    assert "cache_ttl" in hits[0].metadata.get("numeric_claims", {})
    assert hits[0].metadata["trust"] == 0.95
    assert hits[0].score >= hits[1].score


def test_retrieve_context_keeps_seed_hypothesis() -> None:
    index = EvidenceIndex()
    index.add_text("cache_ttl of 10 seconds is the approved PII pattern.", source="policy.privacy")
    extra = ReasoningContext(
        query="",
        hypothesis=Hypothesis(
            id="h1",
            statement="keep short ttl",
            action=CandidateAction(
                id="a1",
                kind=ActionKind.PARAMETER_CHANGE,
                name="keep_ttl",
                payload={"cache_ttl": 10},
            ),
        ),
        domain="privacy",
    )
    ctx = index.retrieve_context("is a 10 second PII cache_ttl allowed", extra=extra)
    assert ctx.hypothesis is not None
    assert ctx.hypothesis.id == "h1"
    assert ctx.evidence
    assert ctx.evidence[0].numeric_claims.get("cache_ttl") == 10.0
