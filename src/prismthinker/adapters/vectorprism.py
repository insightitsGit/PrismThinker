"""Compatibility aliases. Prefer `prismthinker.adapters.documents`."""

from __future__ import annotations

from prismthinker.adapters.documents import (
    IndexRequest,
    IndexResponse,
    RetrievedDocument,
    RetrieveRequest,
    RetrieveResponse,
    from_documents,
)

VectorPrismDocument = RetrievedDocument
VectorPrismRetrieveRequest = RetrieveRequest
VectorPrismRetrieveResponse = RetrieveResponse
VectorPrismIndexRequest = IndexRequest
VectorPrismIndexResponse = IndexResponse
from_vectorprism = from_documents

__all__ = [
    "VectorPrismDocument",
    "VectorPrismIndexRequest",
    "VectorPrismIndexResponse",
    "VectorPrismRetrieveRequest",
    "VectorPrismRetrieveResponse",
    "from_vectorprism",
]
