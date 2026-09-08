from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EpistemicRegime(str, Enum):
    CLOSED_FORMAL = "closed_formal"
    EMPIRICAL = "empirical"
    POLICY_NORMATIVE = "policy_normative"
    PRAGMATIC_SYSTEMS = "pragmatic_systems"
    OPEN_DIALECTIC = "open_dialectic"


class Verdict(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CAUTION = "caution"
    UNDETERMINED = "undetermined"


class ReasoningDisposition(str, Enum):
    CONSENSUS = "consensus"
    QUALIFIED_CONSENSUS = "qualified_consensus"
    CONFLICT = "conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    HARD_VETO = "hard_veto"


class ActionKind(str, Enum):
    BINARY_DECISION = "binary_decision"
    PARAMETER_CHANGE = "parameter_change"
    TOOL_INVOCATION = "tool_invocation"
    ASSERTION = "assertion"


class CitationKind(str, Enum):
    EVIDENCE = "evidence"
    FACT = "fact"
    RULE = "rule"
    CONSTRAINT = "constraint"
    GRAPH_EDGE = "graph_edge"
    HYPOTHESIS = "hypothesis"


class ConstraintStatus(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_APPLICABLE = "not_applicable"
    UNCHECKED = "unchecked"


class DeonticModality(str, Enum):
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"


class RuleSeverity(str, Enum):
    HARD_VETO = "hard_veto"
    BLOCK = "block"
    CAUTION = "caution"


class FactType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    DURATION_MS = "duration_ms"
    ENUM = "enum"
    STRING = "string"


class BackendKind(str, Enum):
    RULES = "rules"
    SOLVER = "solver"
    STATS = "stats"
    GRAPH = "graph"
    LLM = "llm"


class IndependenceClass(str, Enum):
    FORMAL_SYMBOLIC = "formal_symbolic"
    EMPIRICAL_STATS = "empirical_stats"
    CAUSAL_GRAPH = "causal_graph"
    POLICY_DEONTIC = "policy_deontic"
    UTILITY_OBJECTIVE = "utility_objective"


class ChorusGraphDirective(str, Enum):
    EXECUTE = "execute"
    ANSWER = "answer"
    REFUSE = "refuse"
    ESCALATE = "escalate"
    GATHER = "gather"


class EvidenceConflictType(str, Enum):
    NUMERIC_MISMATCH = "numeric_mismatch"
    TEMPORAL = "temporal"
    SOURCE_TRUST = "source_trust"
    EXPLICIT_NEGATION = "explicit_negation"
    STALE = "stale"


class Citation(BaseModel):
    kind: CitationKind
    ref: str


class AssumptionAtom(BaseModel):
    id: str
    predicate: str
    polarity: bool
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ConstraintSpec(BaseModel):
    id: str
    predicate: str
    text: str = ""


class ConstraintApplication(BaseModel):
    constraint_id: str
    status: ConstraintStatus
    cited_fact_keys: List[str] = Field(default_factory=list)


class FactSpec(BaseModel):
    key: str
    fact_type: FactType
    required: bool = False
    mutable: bool = False
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    enum_values: List[str] = Field(default_factory=list)
    unit: Optional[str] = None
    description: str = ""


class FactValue(BaseModel):
    key: str
    value: Any
    unit: Optional[str] = None
    observed_at: Optional[datetime] = None


class CandidateAction(BaseModel):
    id: str
    kind: ActionKind
    name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class Hypothesis(BaseModel):
    id: str
    statement: str
    action: Optional[CandidateAction] = None


class EvidenceItem(BaseModel):
    id: str
    content: str
    source: str
    retrieved_at: Optional[datetime] = None
    trust: float = Field(ge=0.0, le=1.0, default=0.5)
    freshness_hours: Optional[float] = None
    provenance_hash: Optional[str] = None
    numeric_claims: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvidenceConflict(BaseModel):
    left_id: str
    right_id: str
    conflict_type: EvidenceConflictType
    severity: float = Field(ge=0.0, le=1.0)
    reason_codes: List[str] = Field(default_factory=list)
    detail: str = ""


class PolicyRule(BaseModel):
    id: str
    modality: DeonticModality
    predicate: str
    severity: RuleSeverity
    jurisdiction: Optional[str] = None
    text: str = ""
    authority: Literal["trusted", "unknown"] = "trusted"
    action_name: Optional[str] = None
    applies_when: Optional[str] = None
    conflict_group: Optional[str] = None


class AlignedClaim(BaseModel):
    """Caller-normalized claims; no text extraction or inferred authority."""
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    proposition: str = Field(min_length=1)
    time_scope: str = Field(min_length=1)
    source: str = Field(min_length=1)
    value: Union[str, bool, int, float]
    kind: Literal["evidence", "authority"] = "evidence"
    authority: Literal["trusted", "unknown"] = "trusted"
    status: Literal["active", "superseded", "unknown"] = "active"
    action_name: Optional[str] = None
    citations: List[str] = Field(default_factory=list)
    fact_keys: List[str] = Field(default_factory=list)


class EligibilityCheck(BaseModel):
    id: str
    kind: Literal["policy", "constraint", "fact", "evidence", "authority"]
    status: Literal["pass", "block", "missing", "unknown", "review", "not_applicable"]
    authority: str = "trusted"
    detail: str
    cited_fact_keys: List[str] = Field(default_factory=list)


class EligibilityAssessment(BaseModel):
    behavior_version: Literal["eligibility-v1"] = "eligibility-v1"
    directive: Optional[ChorusGraphDirective] = None
    checks: List[EligibilityCheck] = Field(default_factory=list)


class ConflictSignals(BaseModel):
    material_evidence_conflict: bool = False
    policy_authority_conflict: bool = False
    evaluator_disagreement: bool = False
    decision_tie: bool = False
    aligned_conflict_pairs: List[List[str]] = Field(default_factory=list)


class AlignedDelta(BaseModel):
    version: Literal["aligned-shadow-v1"] = "aligned-shadow-v1"
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    comparable_pairs: int = 0
    contradictory_pairs: int = 0
    excluded_claims: int = 0
    sufficient_evidence: bool = False


class CausalEdge(BaseModel):
    source: str
    target: str
    signed: Optional[Literal[-1, 0, 1]] = None
    edge_id: str


class CausalGraph(BaseModel):
    nodes: List[str]
    edges: List[CausalEdge]


class ObjectiveTerm(BaseModel):
    fact_key: str
    weight: float
    direction: Literal["minimize", "maximize", "hit"]
    target: Optional[float] = None
    sla_breach_is_reject: bool = False


class ObjectiveSpec(BaseModel):
    id: str
    terms: List[ObjectiveTerm]
    reject_below: Optional[float] = None
    caution_below: Optional[float] = None


class ReasoningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hypothesis: Optional[Hypothesis] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)
    aligned_claims: List[AlignedClaim] = Field(default_factory=list)
    structured_facts: Dict[str, FactValue] = Field(default_factory=dict)
    fact_specs: Dict[str, FactSpec] = Field(default_factory=dict)
    policy_rules: List[PolicyRule] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)  # display-only; never evaluated
    constraints: List[ConstraintSpec] = Field(default_factory=list)
    causal_graph: Optional[CausalGraph] = None
    objective: Optional[ObjectiveSpec] = None
    domain: Optional[str] = None
    force_regime: Optional[EpistemicRegime] = None
    force_evaluators: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_aligned_ids(self):
        ids = [claim.id for claim in self.aligned_claims]
        if len(ids) != len(set(ids)):
            raise ValueError("aligned claim IDs must be unique")
        return self


class PresentationContext(BaseModel):
    """Downstream only. NEVER accepted by PrismThinker.evaluate()."""

    user_id: Optional[str] = None
    persona_weights: Dict[str, float] = Field(default_factory=dict)
    history_refs: List[str] = Field(default_factory=list)


class Claim(BaseModel):
    id: str
    evaluator: str
    statement: str
    polarity: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: List[Citation] = Field(default_factory=list)
    hypothesis_id: str


class EvaluatorCapability(BaseModel):
    name: str
    backend: BackendKind
    independence_class: IndependenceClass
    may_hard_veto: bool
    timeout_ms: int = 250


class EvaluatorError(BaseModel):
    evaluator: str
    error_type: Literal["timeout", "crash", "invalid_output", "unauthorized_veto"]
    message: str  # single-line "{ExcType}: {exc}"; never a traceback or filesystem dump


class EvaluatorResult(BaseModel):
    evaluator: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    claims: List[Claim] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    premise_ids: List[str] = Field(default_factory=list)
    assumptions: List[AssumptionAtom] = Field(default_factory=list)
    constraints_applied: List[ConstraintApplication] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    hard_veto: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    backend: BackendKind
    latency_ms: float = 0.0


class ConflictComponent(BaseModel):
    conclusion_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    premise_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    constraint_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    assumption_conflict: float = Field(ge=0.0, le=1.0, default=0.0)


class EvaluatorPair(BaseModel):
    """Frozen after construct. Lexicographic order is applied in mode='before'."""

    model_config = ConfigDict(frozen=True)

    left: str
    right: str

    @model_validator(mode="before")
    @classmethod
    def sort_lexicographical(cls, data: Any) -> Any:
        if isinstance(data, cls):
            payload = {"left": data.left, "right": data.right}
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            return data
        left, right = payload.get("left"), payload.get("right")
        if left == right:
            raise ValueError("pair must contain two distinct evaluators")
        if left and right and left > right:
            payload["left"], payload["right"] = right, left
        return payload


class PairwiseDisagreement(BaseModel):
    pair: EvaluatorPair
    delta: float = Field(ge=0.0, le=1.0)
    components: ConflictComponent
    reason_codes: List[str] = Field(default_factory=list)


class CounterfactualProbe(BaseModel):
    parameter_changed: str
    value_before: Any
    value_after: Any
    delta_before: float
    delta_after: float
    resolving: bool
    resolving_condition: str
    flips: List[str] = Field(default_factory=list)


class FastPathResult(BaseModel):
    expression: str
    value: Any
    value_type: str


class ClassifierTrace(BaseModel):
    regime: EpistemicRegime
    fast_path: bool
    feature_scores: Dict[str, float]
    reason_codes: List[str] = Field(default_factory=list)
    override_applied: bool = False


class RadarAxis(BaseModel):
    evaluator: str
    verdict: Verdict
    confidence: float
    polarity: float
    hard_veto: bool


class EpistemicRadarPayload(BaseModel):
    contradiction: float
    uncertainty: float
    axes: List[RadarAxis]
    critical_pairs: List[EvaluatorPair]
    review_required: bool
    unresolved_questions: List[str]
    counterfactual_hints: List[str]
    evidence_conflict_count: int


class DecisionGraph(BaseModel):
    schema_version: Literal["1.1.0", "1.2.0"] = "1.2.0"
    run_id: str
    created_at: datetime
    config_hash: str
    query: str
    hypothesis: Hypothesis
    regime: EpistemicRegime
    selected_evaluators: List[str]
    classifier: ClassifierTrace
    recommended_verdict: Optional[Verdict]
    recommended_rationale: str
    disposition: ReasoningDisposition
    confidence: float = Field(ge=0.0, le=1.0)
    contradiction_score: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    evaluators: Dict[str, EvaluatorResult]
    evidence_conflicts: List[EvidenceConflict] = Field(default_factory=list)
    critical_conflicts: List[PairwiseDisagreement] = Field(default_factory=list)
    shared_assumptions: List[AssumptionAtom] = Field(default_factory=list)
    conflicting_assumptions: List[AssumptionAtom] = Field(default_factory=list)
    counterfactuals: List[CounterfactualProbe] = Field(default_factory=list)
    review_required: bool
    review_reasons: List[str] = Field(default_factory=list)
    radar: EpistemicRadarPayload
    fast_path: Optional[FastPathResult] = None
    errors: List[EvaluatorError] = Field(default_factory=list)
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    eligibility: Optional[EligibilityAssessment] = None
    conflict_signals: ConflictSignals = Field(default_factory=ConflictSignals)
    aligned_delta: AlignedDelta = Field(default_factory=AlignedDelta)


def verdict_polarity(verdict: Verdict) -> Optional[float]:
    if verdict is Verdict.APPROVE:
        return 1.0
    if verdict is Verdict.CAUTION:
        return 0.0
    if verdict is Verdict.REJECT:
        return -1.0
    return None


def polarity_matches_verdict(polarity: float, verdict: Verdict) -> bool:
    if verdict is Verdict.APPROVE:
        return polarity >= 0.34
    if verdict is Verdict.CAUTION:
        return -0.33 <= polarity <= 0.33
    if verdict is Verdict.REJECT:
        return polarity <= -0.34
    return True
