"""Bench-only passage windows. Production rhetorical cuts belong to VectorPrism."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, Mapping

from pydantic import BaseModel, Field

from prismthinker.adapters.documents import RetrievedDocument

_WS = re.compile(r"\s+")
_PARAGRAPH = re.compile(r"\n\s*\n")

_NAMED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cache_ttl", re.compile(r"\bcache[_\s-]?ttl\b[^0-9]{0,24}(\d+(?:\.\d+)?)", re.I)),
    ("p99_latency_ms", re.compile(r"\bp99(?:[_\s-]?latency)?\b[^0-9]{0,24}(\d+(?:\.\d+)?)\s*ms\b", re.I)),
    ("p99_latency_ms", re.compile(r"\bp99\b[^0-9]{0,16}(\d+(?:\.\d+)?)", re.I)),
    ("pvalue", re.compile(r"\bp(?:-|\s*)value\b[^0-9]{0,12}(0?\.\d+|\d+(?:\.\d+)?)", re.I)),
    ("notional_usd", re.compile(r"\bnotional\b[^0-9]{0,16}(\d+(?:\.\d+)?)", re.I)),
    ("freshness_hours", re.compile(r"\b(\d+(?:\.\d+)?)\s*hours?\s+(?:old|stale|ago)\b", re.I)),
)

_GENERIC = re.compile(
    r"\b([a-z][a-z0-9_]{1,40})\s*(?:=|:|of)\s*(-?\d+(?:\.\d+)?)\b",
    re.I,
)
_GENERIC_SKIP = frozenset(
    {"a", "an", "the", "is", "was", "of", "in", "on", "to", "for", "and", "or", "ms", "s", "id", "v", "n", "k", "top"}
)


class ChunkSpec(BaseModel):
    max_chars: int = Field(default=900, ge=120, le=8000)
    overlap: int = Field(default=80, ge=0, le=400)
    min_chars: int = Field(default=40, ge=1, le=400)


def extract_numeric_claims(text: str) -> Dict[str, float]:
    claims: Dict[str, float] = {}
    for key, pattern in _NAMED:
        match = pattern.search(text)
        if match:
            claims[key] = float(match.group(1))
    for match in _GENERIC.finditer(text):
        key = match.group(1).lower()
        if key in _GENERIC_SKIP or key in claims:
            continue
        if key in {"ttl", "cachettl"}:
            claims.setdefault("cache_ttl", float(match.group(2)))
            continue
        claims[key] = float(match.group(2))
    return claims


def trust_for_source(source: str, table: Mapping[str, float] | None = None) -> float:
    mapping = dict(table or {})
    if source in mapping:
        return _clip(mapping[source])
    lowered = source.lower()
    for prefix, value in mapping.items():
        if prefix.endswith(".") and lowered.startswith(prefix.lower()):
            return _clip(value)
    if lowered.startswith("policy.") or lowered.startswith("legal."):
        return 0.95
    if lowered.startswith("prom.") or lowered.startswith("metrics."):
        return 0.70
    if lowered.startswith("wiki.") or lowered.startswith("comment"):
        return 0.55
    return 0.50


def chunk_document(
    text: str,
    *,
    source: str,
    doc_id: str | None = None,
    trust: float | None = None,
    source_trust: Mapping[str, float] | None = None,
    spec: ChunkSpec | None = None,
    extra_metadata: Mapping[str, object] | None = None,
) -> list[RetrievedDocument]:
    windows = list(_windows(text, spec or ChunkSpec()))
    if not windows:
        return []
    resolved_trust = _clip(trust) if trust is not None else trust_for_source(source, source_trust)
    prefix = doc_id or _slug(source)
    extra = dict(extra_metadata or {})
    out: list[RetrievedDocument] = []
    for index, passage in enumerate(windows):
        claims = extract_numeric_claims(passage)
        digest = hashlib.sha256(f"{source}\n{passage}".encode("utf-8")).hexdigest()[:12]
        metadata: dict[str, object] = {
            "trust": resolved_trust,
            "chunk_index": index,
            "parent_id": prefix,
            **extra,
        }
        if claims:
            metadata["numeric_claims"] = claims
        out.append(
            RetrievedDocument(
                id=f"{prefix}.{index}.{digest}",
                text=passage,
                source=source,
                score=0.0,
                metadata=metadata,
            )
        )
    return out


def chunk_corpus(
    documents: Iterable[tuple[str, str]],
    *,
    source_trust: Mapping[str, float] | None = None,
    spec: ChunkSpec | None = None,
) -> list[RetrievedDocument]:
    chunks: list[RetrievedDocument] = []
    for source, text in documents:
        chunks.extend(chunk_document(text, source=source, source_trust=source_trust, spec=spec))
    return chunks


def _windows(text: str, spec: ChunkSpec) -> list[str]:
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in _PARAGRAPH.split(cleaned) if p.strip()] or [cleaned]
    passages: list[str] = []
    for part in parts:
        if len(part) <= spec.max_chars:
            if len(part) >= spec.min_chars:
                passages.append(_squash(part))
            continue
        start = 0
        while start < len(part):
            end = min(len(part), start + spec.max_chars)
            window = part[start:end].strip()
            if len(window) >= spec.min_chars:
                passages.append(_squash(window))
            if end >= len(part):
                break
            start = max(end - spec.overlap, start + 1)
    return passages


def _squash(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _slug(source: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", source.lower()).strip(".") or "doc"


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
