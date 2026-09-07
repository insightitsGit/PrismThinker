"""Bench-only in-process index. Production ANN is VectorPrism."""

from __future__ import annotations

from typing import Mapping, Sequence

from prismthinker.adapters.documents import RetrievedDocument, from_documents
from prismthinker.core.schemas import Hypothesis, ReasoningContext

from bench.chunks import ChunkSpec, chunk_document
from bench.encode import cosine, embed, hybrid_rank


class EvidenceIndex:
    def __init__(self, spec: ChunkSpec | None = None) -> None:
        self.spec = spec or ChunkSpec()
        self._rows: list[tuple[RetrievedDocument, list[float]]] = []

    def __len__(self) -> int:
        return len(self._rows)

    def add_text(
        self,
        text: str,
        *,
        source: str,
        doc_id: str | None = None,
        source_trust: Mapping[str, float] | None = None,
    ) -> int:
        chunks = chunk_document(
            text,
            source=source,
            doc_id=doc_id,
            source_trust=source_trust,
            spec=self.spec,
        )
        return self.add_documents(chunks)

    def add_documents(self, documents: Sequence[RetrievedDocument]) -> int:
        added = 0
        for doc in documents:
            self._rows.append((doc, embed(_blob(doc))))
            added += 1
        return added

    def search(self, query: str, top_k: int = 8) -> list[RetrievedDocument]:
        if not self._rows:
            return []
        query_vec = embed(query)
        ranked: list[tuple[float, RetrievedDocument]] = []
        for doc, vector in self._rows:
            score = hybrid_rank(query, _blob(doc), cosine(query_vec, vector))
            ranked.append((score, doc))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [doc.model_copy(update={"score": score}) for score, doc in ranked[: max(1, top_k)]]

    def retrieve_context(
        self,
        query: str,
        *,
        extra: ReasoningContext,
        hypothesis: Hypothesis | None = None,
        top_k: int = 8,
    ) -> ReasoningContext:
        hits = self.search(query, top_k=top_k)
        return from_documents(
            query,
            hits,
            hypothesis=hypothesis if hypothesis is not None else extra.hypothesis,
            extra=extra,
        )


def _blob(doc: RetrievedDocument) -> str:
    return f"{doc.id} {doc.source} {doc.text}"
