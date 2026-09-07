from __future__ import annotations

from typing import Any, Sequence

from prismthinker.adapters.chorusgraph import (
    ChorusGraphJournalEntry,
    ChorusGraphOrchestrateRequest,
    ChorusGraphOrchestrateResponse,
)
from prismthinker.adapters.vectorprism import (
    VectorPrismDocument,
    VectorPrismIndexRequest,
    VectorPrismIndexResponse,
    VectorPrismRetrieveRequest,
    VectorPrismRetrieveResponse,
)


def _httpx():
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("httpx is required for neighbor HTTP clients; pip install 'prismthinker[bench]'") from exc
    return httpx


class VectorPrismClient:
    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        httpx = _httpx()
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._http.close()

    def health(self) -> dict[str, Any]:
        response = self._http.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def index(self, documents: Sequence[VectorPrismDocument], collection: str = "prismthinker") -> VectorPrismIndexResponse:
        payload = VectorPrismIndexRequest(documents=list(documents), collection=collection)
        response = self._http.post(
            f"{self.base_url}/v1/index",
            json=payload.model_dump(mode="json"),
        )
        response.raise_for_status()
        return VectorPrismIndexResponse.model_validate(response.json())

    def retrieve(self, request: VectorPrismRetrieveRequest) -> VectorPrismRetrieveResponse:
        response = self._http.post(
            f"{self.base_url}/v1/retrieve",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return VectorPrismRetrieveResponse.model_validate(response.json())


class ChorusGraphClient:
    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        httpx = _httpx()
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._http.close()

    def health(self) -> dict[str, Any]:
        response = self._http.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def orchestrate(self, request: ChorusGraphOrchestrateRequest) -> ChorusGraphOrchestrateResponse:
        response = self._http.post(
            f"{self.base_url}/v1/orchestrate",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return ChorusGraphOrchestrateResponse.model_validate(response.json())

    def journal(self) -> list[ChorusGraphJournalEntry]:
        response = self._http.get(f"{self.base_url}/v1/journal")
        response.raise_for_status()
        return [ChorusGraphJournalEntry.model_validate(item) for item in response.json()]
