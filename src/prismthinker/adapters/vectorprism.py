from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

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


class VectorPrismDocument(BaseModel):
    id: str
    text: str
    source: str
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retrieved_at: Optional[datetime] = None


def from_vectorprism(
    query: str,
    documents: List[VectorPrismDocument],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    evidence: list[EvidenceItem] = []
    for doc in documents:
        trust_raw = doc.metadata.get("trust", doc.score)
        try:
            trust = max(0.0, min(1.0, float(trust_raw)))
        except (TypeError, ValueError):
            trust = max(0.0, min(1.0, doc.score))
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
                },
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


def _lift_structured(documents: List[VectorPrismDocument]) -> dict[str, Any]:
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


class VectorPrismRetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=64)
    collection: str = "prismthinker"
    filters: Dict[str, Any] = Field(default_factory=dict)


class VectorPrismRetrieveResponse(BaseModel):
    query: str
    documents: List[VectorPrismDocument]
    backend: str
    collection: str
    took_ms: float


class VectorPrismIndexRequest(BaseModel):
    documents: List[VectorPrismDocument]
    collection: str = "prismthinker"


class VectorPrismIndexResponse(BaseModel):
    indexed: int
    collection: str
    backend: str
