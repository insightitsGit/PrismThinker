"""Standard RAG plug-in helpers. `evaluate()` never imports this module.

PrismThinker does not retrieve. Map any retriever's hits into EvidenceItem /
from_langchain / from_documents, then gate generation on the DecisionGraph.
"""

from __future__ import annotations

from prismthinker.core.schemas import DecisionGraph, ReasoningDisposition

_PASS_TO_GENERATOR = frozenset(
    {
        ReasoningDisposition.CONSENSUS,
        ReasoningDisposition.QUALIFIED_CONSENSUS,
    }
)


def allow_generation(graph: DecisionGraph) -> bool:
    """Whether verified evidence may enter an LLM prompt.

    HARD_VETO, CONFLICT, and INSUFFICIENT_EVIDENCE all halt generation.
    Qualified consensus (Δ between qualified_tau and tau_base) may generate
    with the graph attached; it is not a silent pass.
    """
    return graph.disposition in _PASS_TO_GENERATOR
