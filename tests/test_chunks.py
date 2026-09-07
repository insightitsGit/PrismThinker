from __future__ import annotations

from bench.chunks import (
    ChunkSpec,
    chunk_document,
    extract_numeric_claims,
    trust_for_source,
)
from prismthinker.adapters.documents import from_documents
from prismthinker.core.engine import PrismThinker
from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    ReasoningContext,
    Verdict,
)


def test_extract_numeric_claims_named_and_generic() -> None:
    text = (
        "Privacy control: cache_ttl of 30 seconds. p99 latency 180ms. "
        "p-value 0.04. error_rate = 0.02."
    )
    claims = extract_numeric_claims(text)
    assert claims["cache_ttl"] == 30.0
    assert claims["p99_latency_ms"] == 180.0
    assert claims["pvalue"] == 0.04
    assert claims["error_rate"] == 0.02


def test_trust_comes_from_source_not_cosine() -> None:
    assert trust_for_source("policy.privacy") == 0.95
    assert trust_for_source("prom.checkout") == 0.70
    assert trust_for_source("custom.db", {"custom.db": 0.81}) == 0.81


def test_chunk_document_emits_typed_payloads() -> None:
    text = (
        "Checkout cache_ttl of 60 seconds while contains_pii is true.\n\n"
        "Approved pattern: reduce cache_ttl to 10 seconds for PII. p99 90ms."
    )
    chunks = chunk_document(text, source="policy.privacy", spec=ChunkSpec(max_chars=200, overlap=20))
    assert len(chunks) >= 2
    assert all(doc.score == 0.0 for doc in chunks)
    assert all(doc.metadata["trust"] == 0.95 for doc in chunks)
    assert any("cache_ttl" in doc.metadata.get("numeric_claims", {}) for doc in chunks)


def test_chunked_evidence_reaches_empirical_head() -> None:
    chunks = chunk_document(
        "Live scrape: cache_ttl of 60. Operator fact is the point estimate.",
        source="prom.checkout",
    )
    ctx = from_documents(
        "keep cache_ttl at 60",
        chunks,
        extra=ReasoningContext(
            query="keep cache_ttl at 60",
            hypothesis=Hypothesis(
                id="h1",
                statement="keep ttl 60",
                action=CandidateAction(
                    id="a1",
                    kind=ActionKind.PARAMETER_CHANGE,
                    name="keep_cache_ttl",
                    payload={"cache_ttl": 60},
                ),
            ),
            structured_facts={"cache_ttl": FactValue(key="cache_ttl", value=60)},
            fact_specs={"cache_ttl": FactSpec(key="cache_ttl", fact_type=FactType.INT)},
        ),
    )
    assert ctx.evidence[0].numeric_claims["cache_ttl"] == 60.0
    assert ctx.evidence[0].trust == 0.70
    graph = PrismThinker().evaluate(ctx)
    assert graph.evaluators["empirical"].verdict is not Verdict.UNDETERMINED
