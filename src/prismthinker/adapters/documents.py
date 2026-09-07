"""Retriever-agnostic ingress. `evaluate()` never imports this module.

`trust` comes from `metadata.trust` when present. Retrieval rank / cosine
(`score`) is a fallback only — topical relevance is not authority.
Lifting `policy_rule` / `causal_graph` from chunk metadata is an optional
convenience for tests. Production rules belong in a policy registry passed
via `extra=` or the caller, not in ANN chunks.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pydantic import BaseModel, Field

from prismthinker.core.schemas import (
    CausalEdge,
    CausalGraph,
    ConstraintSpec,
    EvidenceItem,
    FactSpec,
    FactValue,
    Hypothesis,
    PolicyRule,
    ReasoningContext,
)


class RetrievedDocument(BaseModel):
    """Generic retrieved blob. Not tied to any vector database."""

    id: str
    text: str
    source: str
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retrieved_at: Optional[datetime] = None


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=64)
    collection: str = "prismthinker"
    filters: Dict[str, Any] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    query: str
    documents: List[RetrievedDocument]
    backend: str
    collection: str
    took_ms: float


class IndexRequest(BaseModel):
    documents: List[RetrievedDocument]
    collection: str = "prismthinker"


class IndexResponse(BaseModel):
    indexed: int
    collection: str
    backend: str


def from_documents(
    query: str,
    documents: Sequence[RetrievedDocument],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    evidence: list[EvidenceItem] = []
    for doc in documents:
        trust = _trust_for(doc)
        numeric: dict[str, float] = {}
        raw_numeric = doc.metadata.get("numeric_claims")
        if isinstance(raw_numeric, dict):
            for key, value in raw_numeric.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric[str(key)] = float(value)
        freshness_raw = doc.metadata.get("freshness_hours")
        freshness: float | None
        try:
            freshness = float(freshness_raw) if freshness_raw is not None else None
        except (TypeError, ValueError):
            freshness = None
        evidence.append(
            EvidenceItem(
                id=doc.id,
                content=doc.text,
                source=doc.source,
                retrieved_at=doc.retrieved_at,
                trust=trust,
                freshness_hours=freshness,
                provenance_hash=hashlib.sha256(
                    f"{doc.id}{doc.source}{doc.text}".encode("utf-8")
                ).hexdigest(),
                numeric_claims=numeric,
                metadata={
                    k: v
                    for k, v in doc.metadata.items()
                    if k
                    not in {
                        "trust",
                        "numeric_claims",
                        "freshness_hours",
                        "facts",
                        "policy_rule",
                        "constraint",
                        "causal_graph",
                    }
                }
                | _negation_fields(doc.metadata),
            )
        )

    lifted = _lift_structured(documents)
    if extra is not None:
        merged = extra.model_copy(deep=True)
        structured = dict(facts if facts is not None else extra.structured_facts)
        for key, value in lifted["structured_facts"].items():
            structured.setdefault(key, value)
        specs = dict(fact_specs if fact_specs is not None else extra.fact_specs)
        for key, spec in lifted["fact_specs"].items():
            specs.setdefault(key, spec)
        rules = list(extra.policy_rules) or list(lifted["policy_rules"])
        constraints = list(extra.constraints) or list(lifted["constraints"])
        graph = extra.causal_graph or lifted["causal_graph"]
        return merged.model_copy(
            update={
                "query": query,
                "hypothesis": hypothesis if hypothesis is not None else extra.hypothesis,
                "evidence": evidence,
                "structured_facts": structured,
                "fact_specs": specs,
                "policy_rules": rules,
                "constraints": constraints,
                "causal_graph": graph,
            }
        )
    return ReasoningContext(
        query=query,
        hypothesis=hypothesis,
        evidence=evidence,
        structured_facts=facts or lifted["structured_facts"],
        fact_specs=fact_specs or lifted["fact_specs"],
        policy_rules=lifted["policy_rules"],
        constraints=lifted["constraints"],
        causal_graph=lifted["causal_graph"],
    )


def from_langchain(
    query: str,
    documents: Iterable[Any],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    """Map LangChain `Document` objects (duck-typed). No LangChain dependency."""
    return from_documents(
        query,
        [langchain_document(item) for item in documents],
        hypothesis=hypothesis,
        facts=facts,
        fact_specs=fact_specs,
        extra=extra,
    )


def from_llamaindex(
    query: str,
    documents: Iterable[Any],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    """Map LlamaIndex nodes / `NodeWithScore` (duck-typed). No LlamaIndex dependency."""
    return from_documents(
        query,
        [llamaindex_document(item) for item in documents],
        hypothesis=hypothesis,
        facts=facts,
        fact_specs=fact_specs,
        extra=extra,
    )


def langchain_document(item: Any) -> RetrievedDocument:
    if isinstance(item, RetrievedDocument):
        return item
    page = getattr(item, "page_content", None)
    if not isinstance(page, str):
        raise TypeError("LangChain document must expose str page_content")
    metadata = _as_dict(getattr(item, "metadata", None))
    doc_id = _first_str(
        getattr(item, "id", None),
        metadata.get("id"),
        metadata.get("doc_id"),
    ) or hashlib.sha256(page.encode("utf-8")).hexdigest()[:16]
    source = _first_str(metadata.get("source"), metadata.get("file_path")) or "langchain"
    score = _as_float(getattr(item, "score", None), metadata.get("score"), default=0.0)
    return RetrievedDocument(
        id=str(doc_id),
        text=page,
        source=str(source),
        score=score,
        metadata=metadata,
    )


def llamaindex_document(item: Any) -> RetrievedDocument:
    if isinstance(item, RetrievedDocument):
        return item
    score = _as_float(getattr(item, "score", None), default=0.0)
    node = getattr(item, "node", item)
    text = getattr(node, "text", None)
    if not isinstance(text, str):
        getter = getattr(node, "get_content", None)
        text = getter() if callable(getter) else None
    if not isinstance(text, str):
        raise TypeError("LlamaIndex node must expose text or get_content()")
    metadata = _as_dict(getattr(node, "metadata", None))
    if not metadata:
        metadata = _as_dict(getattr(item, "metadata", None))
    doc_id = _first_str(
        getattr(node, "id_", None),
        getattr(node, "node_id", None),
        getattr(node, "doc_id", None),
        getattr(item, "id_", None),
        metadata.get("id"),
    ) or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    source = _first_str(
        metadata.get("source"),
        metadata.get("file_path"),
        getattr(node, "source", None),
    ) or "llamaindex"
    if getattr(item, "score", None) is None:
        score = _as_float(metadata.get("score"), default=0.0)
    return RetrievedDocument(
        id=str(doc_id),
        text=text,
        source=str(source),
        score=score,
        metadata=metadata,
    )


def _negation_fields(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Keep VectorPrism inversion flags for the evidence-conflict pass."""
    out: dict[str, Any] = {}
    if "negates_id" in metadata:
        out["negates_id"] = metadata["negates_id"]
    if "negates_ids" in metadata:
        out["negates_ids"] = metadata["negates_ids"]
    return out


def _trust_for(doc: RetrievedDocument) -> float:
    if "trust" in doc.metadata:
        try:
            return max(0.0, min(1.0, float(doc.metadata["trust"])))
        except (TypeError, ValueError):
            pass
    return max(0.0, min(1.0, float(doc.score)))


def _lift_structured(documents: Sequence[RetrievedDocument]) -> dict[str, Any]:
    facts: Dict[str, FactValue] = {}
    specs: Dict[str, FactSpec] = {}
    rules: list[PolicyRule] = []
    constraints: list[ConstraintSpec] = []
    nodes: list[str] = []
    edges: list[CausalEdge] = []
    seen_rules: set[str] = set()
    seen_constraints: set[str] = set()
    seen_edges: set[str] = set()
    for doc in documents:
        raw_facts = doc.metadata.get("facts")
        if isinstance(raw_facts, dict):
            for key, value in raw_facts.items():
                facts.setdefault(str(key), FactValue(key=str(key), value=value))
        raw_rule = doc.metadata.get("policy_rule")
        if isinstance(raw_rule, dict):
            rule = PolicyRule.model_validate(raw_rule)
            if rule.id not in seen_rules:
                rules.append(rule)
                seen_rules.add(rule.id)
        raw_constraint = doc.metadata.get("constraint")
        if isinstance(raw_constraint, dict):
            constraint = ConstraintSpec.model_validate(raw_constraint)
            if constraint.id not in seen_constraints:
                constraints.append(constraint)
                seen_constraints.add(constraint.id)
        raw_graph = doc.metadata.get("causal_graph")
        if isinstance(raw_graph, dict):
            graph = CausalGraph.model_validate(raw_graph)
            for node in graph.nodes:
                if node not in nodes:
                    nodes.append(node)
            for edge in graph.edges:
                if edge.edge_id not in seen_edges:
                    edges.append(edge)
                    seen_edges.add(edge.edge_id)
    return {
        "structured_facts": facts,
        "fact_specs": specs,
        "policy_rules": rules,
        "constraints": constraints,
        "causal_graph": CausalGraph(nodes=nodes, edges=edges) if edges else None,
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_float(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
