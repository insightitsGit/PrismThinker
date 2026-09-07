from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from prismthinker.adapters.documents import (
    IndexRequest,
    IndexResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from bench.store import MemoryStore, QdrantStore, RetrievalStore

COLLECTION_DEFAULT = "prismthinker"
app = FastAPI(title="mock-retriever", version="1.1.0")
_store: RetrievalStore | None = None


def get_store() -> RetrievalStore:
    global _store
    if _store is not None:
        return _store
    url = os.environ.get("QDRANT_URL", "").strip()
    _store = QdrantStore(url) if url else MemoryStore()
    return _store


@app.get("/health")
def health() -> dict[str, Any]:
    store = get_store()
    return {"ok": True, "service": "mock_retriever", "backend": store.backend}


@app.post("/v1/index", response_model=IndexResponse)
def index_documents(body: IndexRequest) -> IndexResponse:
    store = get_store()
    count = store.index(body.documents, body.collection)
    return IndexResponse(indexed=count, collection=body.collection, backend=store.backend)


@app.post("/v1/retrieve", response_model=RetrieveResponse)
def retrieve(body: RetrieveRequest) -> RetrieveResponse:
    store = get_store()
    documents, took_ms = store.search(body.query, body.top_k, body.collection)
    return RetrieveResponse(
        query=body.query,
        documents=documents,
        backend=store.backend,
        collection=body.collection,
        took_ms=took_ms,
    )


@app.exception_handler(Exception)
async def _errors(_request, exc: Exception) -> JSONResponse:
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("RETRIEVER_PORT", os.environ.get("VECTORPRISM_PORT", "8081")))
    uvicorn.run("bench.services.mock_retriever:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
