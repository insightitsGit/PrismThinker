from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from fastapi import FastAPI

from prismthinker.adapters.chorusgraph import (
    ChorusGraphJournalEntry,
    ChorusGraphOrchestrateRequest,
    ChorusGraphOrchestrateResponse,
    honor_envelope,
)

app = FastAPI(title="chorusgraph-lite", version="1.1.0")
_lock = threading.Lock()
_journal: list[ChorusGraphJournalEntry] = []


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "chorusgraph", "journal": len(_journal)}


@app.post("/v1/orchestrate", response_model=ChorusGraphOrchestrateResponse)
def orchestrate(body: ChorusGraphOrchestrateRequest) -> ChorusGraphOrchestrateResponse:
    response, entry = honor_envelope(body, str(uuid.uuid4()))
    with _lock:
        _journal.append(entry)
    return response


@app.get("/v1/journal", response_model=list[ChorusGraphJournalEntry])
def journal() -> list[ChorusGraphJournalEntry]:
    with _lock:
        return list(_journal)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("CHORUSGRAPH_PORT", "8082"))
    uvicorn.run("bench.services.chorusgraph:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
