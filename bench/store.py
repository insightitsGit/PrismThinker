from __future__ import annotations

import time
import uuid
from typing import Protocol

from prismthinker.adapters.vectorprism import VectorPrismDocument

from bench.encode import DIM, _TOKEN, cosine, embed


def _lexical(query: str, text: str) -> float:
    qtoks = set(_TOKEN.findall(query.lower()))
    dtoks = set(_TOKEN.findall(text.lower()))
    if not qtoks:
        return 0.0
    return len(qtoks & dtoks) / len(qtoks)


def _hybrid(query: str, doc: VectorPrismDocument, cosine_score: float) -> float:
    lexical = _lexical(query, f"{doc.id} {doc.source} {doc.text}")
    return max(0.0, min(1.0, 0.55 * cosine_score + 0.45 * lexical))


class RetrievalStore(Protocol):
    backend: str

    def index(self, documents: list[VectorPrismDocument], collection: str) -> int: ...

    def search(self, query: str, top_k: int, collection: str) -> tuple[list[VectorPrismDocument], float]: ...


class MemoryStore:
    backend = "memory"

    def __init__(self) -> None:
        self._docs: dict[str, list[tuple[VectorPrismDocument, list[float]]]] = {}

    def index(self, documents: list[VectorPrismDocument], collection: str) -> int:
        packed = [(doc, embed(f"{doc.id} {doc.source} {doc.text}")) for doc in documents]
        self._docs[collection] = packed
        return len(packed)

    def search(self, query: str, top_k: int, collection: str) -> tuple[list[VectorPrismDocument], float]:
        started = time.perf_counter()
        query_vec = embed(query)
        ranked: list[tuple[float, VectorPrismDocument]] = []
        for doc, vector in self._docs.get(collection, []):
            score = _hybrid(query, doc, cosine(query_vec, vector))
            ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hits = [
            item[1].model_copy(update={"score": item[0]})
            for item in ranked[:top_k]
        ]
        return hits, (time.perf_counter() - started) * 1000.0


class QdrantStore:
    backend = "qdrant"

    def __init__(self, url: str) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        self._client = QdrantClient(url=url, timeout=30)
        self._distance = Distance
        self._params = VectorParams
        self._ready: set[str] = set()

    def _ensure(self, collection: str) -> None:
        if collection in self._ready:
            return
        existing = {item.name for item in self._client.get_collections().collections}
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=self._params(size=DIM, distance=self._distance.COSINE),
            )
        self._ready.add(collection)

    def index(self, documents: list[VectorPrismDocument], collection: str) -> int:
        from qdrant_client.http.models import PointStruct

        self._ensure(collection)
        points = []
        for doc in documents:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, doc.id))
            payload = doc.model_dump(mode="json")
            payload["doc_id"] = doc.id
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embed(f"{doc.id} {doc.source} {doc.text}"),
                    payload=payload,
                )
            )
        self._client.upsert(collection_name=collection, points=points, wait=True)
        return len(points)

    def search(self, query: str, top_k: int, collection: str) -> tuple[list[VectorPrismDocument], float]:
        self._ensure(collection)
        started = time.perf_counter()
        fetch = max(top_k, 16)
        try:
            raw = self._client.query_points(
                collection_name=collection,
                query=embed(query),
                limit=fetch,
                with_payload=True,
            )
            hits = raw.points
        except Exception:
            hits = self._client.search(
                collection_name=collection,
                query_vector=embed(query),
                limit=fetch,
                with_payload=True,
            )
        documents: list[VectorPrismDocument] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            payload.pop("doc_id", None)
            payload["score"] = 0.0
            documents.append(VectorPrismDocument.model_validate(payload))
        reranked = [
            doc.model_copy(update={"score": _hybrid(query, doc, float(hit.score))})
            for doc, hit in zip(documents, hits)
        ]
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_k], (time.perf_counter() - started) * 1000.0
