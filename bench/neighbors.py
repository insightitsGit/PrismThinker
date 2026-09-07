from __future__ import annotations

import uuid

from prismthinker.adapters.chorusgraph import (
    ChorusGraphJournalEntry,
    ChorusGraphOrchestrateRequest,
    ChorusGraphOrchestrateResponse,
    honor_envelope,
)
from prismthinker.adapters.documents import (
    RetrievedDocument,
    RetrieveRequest,
    RetrieveResponse,
)
from bench.store import MemoryStore, RetrievalStore


class LocalRetriever:
    def __init__(self, store: RetrievalStore | None = None) -> None:
        self.store = store or MemoryStore()

    def index(self, documents: list[RetrievedDocument], collection: str = "prismthinker") -> int:
        return self.store.index(documents, collection)

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        documents, took_ms = self.store.search(request.query, request.top_k, request.collection)
        return RetrieveResponse(
            query=request.query,
            documents=documents,
            backend=self.store.backend,
            collection=request.collection,
            took_ms=took_ms,
        )


LocalVectorPrism = LocalRetriever


class LocalChorusGraph:
    def __init__(self) -> None:
        self.entries: list[ChorusGraphJournalEntry] = []

    def orchestrate(self, request: ChorusGraphOrchestrateRequest) -> ChorusGraphOrchestrateResponse:
        response, entry = honor_envelope(request, str(uuid.uuid4()))
        self.entries.append(entry)
        return response
