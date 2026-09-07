from __future__ import annotations

from prismthinker import (
    ActionKind,
    CandidateAction,
    EvidenceItem,
    Hypothesis,
    PolicyRule,
    PrismThinker,
    ReasoningContext,
    ReasoningDisposition,
    RuleSeverity,
)
from prismthinker.adapters.documents import from_langchain
from prismthinker.adapters.rag import allow_generation


class _LangChainHit:
    def __init__(self, page_content: str, source: str, score: float, doc_id: str) -> None:
        self.page_content = page_content
        self.metadata = {"source": source, "score": score}
        self.id = doc_id


def _refund_hypothesis(*, amount: float) -> Hypothesis:
    return Hypothesis(
        id="hyp_1",
        statement="Approve automated refund for disputed transaction.",
        action=CandidateAction(
            id="act_refund",
            kind=ActionKind.TOOL_INVOCATION,
            name="issue_refund",
            payload={"amount": amount},
        ),
    )


def _refund_rule() -> PolicyRule:
    return PolicyRule(
        id="rule_refund_cap",
        modality="prohibition",
        predicate="action.payload.amount > 500",
        severity=RuleSeverity.HARD_VETO,
        text="Automated refunds cannot exceed $500.",
    )


def test_public_plugin_surface_imports() -> None:
    from prismthinker import DeonticModality, EvidenceItem as Item

    assert DeonticModality.PROHIBITION.value == "prohibition"
    item = Item(id="d1", content="chunk", source="pinecone")
    assert item.trust == 0.5


def test_standard_rag_manual_evidence_blocks_over_cap_refund() -> None:
    query = "Should we auto-refund this disputed $750 charge?"
    retrieved_docs = [
        _LangChainHit("Customer requested an automated refund.", "wiki.refunds", 0.82, "doc_0"),
        _LangChainHit("Chargeback already opened on the card.", "crm.ticket", 0.71, "doc_1"),
    ]
    evidence_list = [
        EvidenceItem(
            id=f"doc_{i}",
            content=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            trust=float(doc.metadata.get("trust", doc.metadata.get("score", 0.5))),
        )
        for i, doc in enumerate(retrieved_docs)
    ]
    context = ReasoningContext(
        query=query,
        hypothesis=_refund_hypothesis(amount=750),
        evidence=evidence_list,
        policy_rules=[_refund_rule()],
    )
    graph = PrismThinker().evaluate(context)
    assert graph.disposition is ReasoningDisposition.HARD_VETO
    assert graph.disposition == "hard_veto"
    assert graph.evaluators["policy"].hard_veto is True
    assert graph.recommended_rationale
    assert allow_generation(graph) is False


def test_standard_rag_from_langchain_under_cap_does_not_veto() -> None:
    hits = [
        _LangChainHit("Refund policy cap is $500 for automation.", "policy.refunds", 0.9, "lc-1"),
        _LangChainHit("This ticket is $80.", "crm.ticket", 0.6, "lc-2"),
    ]
    extra = ReasoningContext(
        query="approve $80 automated refund",
        hypothesis=_refund_hypothesis(amount=80),
        policy_rules=[_refund_rule()],
    )
    ctx = from_langchain(extra.query, hits, extra=extra)
    assert ctx.evidence[0].content.startswith("Refund policy")
    assert ctx.evidence[0].trust == 0.9
    graph = PrismThinker().evaluate(ctx)
    assert graph.disposition is not ReasoningDisposition.HARD_VETO
    assert graph.evaluators["policy"].hard_veto is False


def test_rag_gate_blocks_conflict_and_insufficient() -> None:
    graph = PrismThinker().evaluate(ReasoningContext(query="hello there general case"))
    graph.disposition = ReasoningDisposition.CONSENSUS
    assert allow_generation(graph) is True
    graph.disposition = ReasoningDisposition.QUALIFIED_CONSENSUS
    assert allow_generation(graph) is True
    graph.disposition = ReasoningDisposition.HARD_VETO
    assert allow_generation(graph) is False
    graph.disposition = ReasoningDisposition.CONFLICT
    assert allow_generation(graph) is False
    graph.disposition = ReasoningDisposition.INSUFFICIENT_EVIDENCE
    assert allow_generation(graph) is False
