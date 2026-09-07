from __future__ import annotations

import uuid

from prismthinker.adapters.chorusgraph import (
    ChorusGraphJournalEntry,
    ChorusGraphOrchestrateRequest,
    ChorusGraphOrchestrateResponse,
    honor_envelope,
)
from prismthinker.adapters.vectorprism import (
    VectorPrismDocument,
    VectorPrismRetrieveRequest,
    VectorPrismRetrieveResponse,
)
from bench.store import MemoryStore, RetrievalStore


class LocalVectorPrism:
    def __init__(self, store: RetrievalStore | None = None) -> None:
        self.store = store or MemoryStore()

    def index(self, documents: list[VectorPrismDocument], collection: str = "prismthinker") -> int:
        return self.store.index(documents, collection)

    def retrieve(self, request: VectorPrismRetrieveRequest) -> VectorPrismRetrieveResponse:
        documents, took_ms = self.store.search(request.query, request.top_k, request.collection)
        return VectorPrismRetrieveResponse(
            query=request.query,
            documents=documents,
            backend=self.store.backend,
            collection=request.collection,
            took_ms=took_ms,
        )


class LocalChorusGraph:
    def __init__(self) -> None:
        self.entries: list[ChorusGraphJournalEntry] = []

    def orchestrate(self, request: ChorusGraphOrchestrateRequest) -> ChorusGraphOrchestrateResponse:
        response, entry = honor_envelope(request, str(uuid.uuid4()))
        self.entries.append(entry)
        return response
