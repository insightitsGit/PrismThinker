"""VectorPrism sensory ingress.

Maps VectorPrism document payloads into PrismThinker `ReasoningContext`.
This is the only supported join between the two products. `evaluate()` never
imports VectorPrism, torch, or an ANN client.

Mapping:
- text → EvidenceItem.content
- metadata.trust if present, else clip(score) → EvidenceItem.trust (topical fallback)
- metadata.numeric_claims → EvidenceItem.numeric_claims
- metadata.negates_id / negates_ids → evidence conflict pass (EXPLICIT_NEGATION)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from prismthinker.adapters.documents import (
    IndexRequest,
    IndexResponse,
    RetrievedDocument,
    RetrieveRequest,
    RetrieveResponse,
    from_documents,
)
from prismthinker.core.schemas import FactSpec, FactValue, Hypothesis, ReasoningContext

VectorPrismDocument = RetrievedDocument
VectorPrismRetrieveRequest = RetrieveRequest
VectorPrismRetrieveResponse = RetrieveResponse
VectorPrismIndexRequest = IndexRequest
VectorPrismIndexResponse = IndexResponse


def from_vectorprism(
    query: str,
    documents: Sequence[RetrievedDocument],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    return from_documents(
        query,
        documents,
        hypothesis=hypothesis,
        facts=facts,
        fact_specs=fact_specs,
        extra=extra,
    )


__all__ = [
    "VectorPrismDocument",
    "VectorPrismIndexRequest",
    "VectorPrismIndexResponse",
    "VectorPrismRetrieveRequest",
    "VectorPrismRetrieveResponse",
    "from_vectorprism",
]
