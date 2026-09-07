from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from prismthinker.core.schemas import (
    ActionKind,
    ChorusGraphDirective,
    DecisionGraph,
    PresentationContext,
    ReasoningDisposition,
    Verdict,
)


class ChorusGraphEnvelope(BaseModel):
    directive: ChorusGraphDirective
    decision_graph: DecisionGraph
    allowed_tools: List[str]
    gather_fact_keys: List[str] = Field(default_factory=list)
    gather_questions: List[str] = Field(default_factory=list)


def to_chorusgraph(
    graph: DecisionGraph,
    *,
    allowed_tools: List[str] | None = None,
) -> ChorusGraphEnvelope:
    tools = list(allowed_tools or [])
    directive = _directive(graph)
    if directive in {
        ChorusGraphDirective.REFUSE,
        ChorusGraphDirective.ESCALATE,
        ChorusGraphDirective.GATHER,
        ChorusGraphDirective.ANSWER,
    }:
        tools = []
    if graph.review_required and directive is ChorusGraphDirective.EXECUTE:
        directive = ChorusGraphDirective.ESCALATE
        tools = []

    gather_qs: list[str] = []
    if directive is ChorusGraphDirective.GATHER:
        for result in graph.evaluators.values():
            gather_qs.extend(result.unresolved_questions)
        gather_qs.extend(graph.radar.unresolved_questions)
    gather_keys = _fact_keys_from_questions(gather_qs)

    return ChorusGraphEnvelope(
        directive=directive,
        decision_graph=graph,
        allowed_tools=tools,
        gather_fact_keys=list(dict.fromkeys(gather_keys)),
        gather_questions=list(dict.fromkeys(gather_qs)),
    )


def _fact_keys_from_questions(questions: List[str]) -> list[str]:
    keys: list[str] = []
    prefixes = ("missing required fact ", "missing fact ")
    for question in questions:
        lowered = question
        for prefix in prefixes:
            if lowered.startswith(prefix):
                token = lowered[len(prefix) :].split()[0]
                keys.append(token)
                break
        marker = "fact."
        idx = question.find(marker)
        if idx >= 0:
            tail = question[idx + len(marker) :]
            token = "".join(ch for ch in tail if ch.isalnum() or ch == "_")
            if token:
                keys.append(token)
    return list(dict.fromkeys(keys))


def _directive(graph: DecisionGraph) -> ChorusGraphDirective:
    if graph.disposition is ReasoningDisposition.HARD_VETO:
        return ChorusGraphDirective.REFUSE
    if graph.disposition is ReasoningDisposition.CONFLICT:
        return ChorusGraphDirective.ESCALATE
    if graph.disposition is ReasoningDisposition.INSUFFICIENT_EVIDENCE:
        return ChorusGraphDirective.GATHER
    if graph.disposition in {
        ReasoningDisposition.CONSENSUS,
        ReasoningDisposition.QUALIFIED_CONSENSUS,
    }:
        if graph.recommended_verdict is Verdict.REJECT:
            return ChorusGraphDirective.REFUSE
        if graph.recommended_verdict is Verdict.CAUTION:
            return ChorusGraphDirective.ESCALATE
        if graph.recommended_verdict is Verdict.APPROVE:
            has_action = (
                graph.hypothesis.action is not None
                and graph.hypothesis.action.kind is not ActionKind.ASSERTION
            )
            return ChorusGraphDirective.EXECUTE if has_action else ChorusGraphDirective.ANSWER
    return ChorusGraphDirective.ESCALATE


class ChorusGraphOrchestrateRequest(BaseModel):
    """Wire payload ChorusGraph accepts after PrismThinker evaluation."""

    envelope: ChorusGraphEnvelope
    requested_tools: List[str] = Field(default_factory=list)
    presentation: PresentationContext | None = None


class ChorusGraphJournalEntry(BaseModel):
    journal_id: str
    accepted: bool
    directive: ChorusGraphDirective
    executed_tools: List[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    gather_fact_keys: List[str] = Field(default_factory=list)
    query: str
    disposition: str
    run_id: str


class ChorusGraphOrchestrateResponse(BaseModel):
    accepted: bool
    directive: ChorusGraphDirective
    executed_tools: List[str]
    blocked_reason: str | None = None
    journal_id: str
    gather_fact_keys: List[str] = Field(default_factory=list)


def honor_envelope(
    request: ChorusGraphOrchestrateRequest,
    journal_id: str,
) -> tuple[ChorusGraphOrchestrateResponse, ChorusGraphJournalEntry]:
    """Apply the egress contract: tools run only on EXECUTE."""
    envelope = request.envelope
    directive = envelope.directive
    blocked: str | None = None
    executed: list[str] = []
    if directive is ChorusGraphDirective.EXECUTE:
        allow = list(envelope.allowed_tools)
        requested = list(request.requested_tools) if request.requested_tools else allow
        executed = [name for name in requested if name in allow]
    elif request.requested_tools:
        blocked = f"{directive.value} forbids tool execution"
    response = ChorusGraphOrchestrateResponse(
        accepted=True,
        directive=directive,
        executed_tools=executed,
        blocked_reason=blocked,
        journal_id=journal_id,
        gather_fact_keys=list(envelope.gather_fact_keys),
    )
    entry = ChorusGraphJournalEntry(
        journal_id=journal_id,
        accepted=True,
        directive=directive,
        executed_tools=executed,
        blocked_reason=blocked,
        gather_fact_keys=list(envelope.gather_fact_keys),
        query=envelope.decision_graph.query,
        disposition=envelope.decision_graph.disposition.value,
        run_id=envelope.decision_graph.run_id,
    )
    return response, entry
