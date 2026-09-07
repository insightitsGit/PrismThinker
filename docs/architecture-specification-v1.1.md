# PrismThinker Architecture v1.1 FROZEN

**Package:** `prismthinker`  
**Schema version:** `1.1.0`  
**Status:** FROZEN  
**Supersedes:** [v1.0](./architecture-specification-v1.0.md)

This document is the implementation contract. Do not add features, heads, or schema fields under the v1.1 name. A later version is allowed only when implementation or benchmarks falsify a rule here.

**System Role:** Model-agnostic, disagreement-aware epistemic reasoning coprocessor.

**Core Purpose:** Evaluates one canonical hypothesis and identical evidence across methodologically independent reasoning heads, isolates structural disagreements into an explainable contradiction matrix, extracts conflicting assumption atoms, and identifies budgeted counterfactual resolution paths without forcing artificial consensus.

v1.1 does not change the product thesis. It closes the v1.0 holes that made the measurement layer unimplementable: shared proposition, evaluator methods, contradiction formulas, disposition lattice, typed facts, classifier coverage, neighbor contracts, and operational failure rules.

---

## 0. Changelog from v1.0

| Area | v1.0 | v1.1 |
|---|---|---|
| Proposition | Free-text claims + untyped `candidate_action` | Single typed `Hypothesis` every head scores |
| Evaluator methods | Output-only | Backend protocol + per-head algorithm |
| Independence | Implied by “separate heads” | Distinct `independence_class`; prompts are not independence |
| \(\Delta_{ij}\) components | Named, undefined | Closed-form formulas; `premise` and `constraint` now have source fields |
| Uncertainty | Unbounded \(U\) | Saturated \(U \in [0,1]\) with coverage terms |
| Disposition | Emitted, not derived | Priority lattice; `recommended_verdict` is nullable |
| `HUMAN_REVIEW` | Peer disposition | Routing flag, not an epistemic outcome |
| Hard veto | Any head, free boolean | Capability-gated; `policy` only. `formal` never vetoes |
| Classifier | AST math only | Two-stage: safe AST + feature regime scorer + override |
| Selector | Incomplete maps, 2-head starvation | Versioned table, min cardinality 3, domain overlays |
| Facts | `Dict[str, Any]` | `FactSpec` + values; probes only on mutable typed facts |
| Evidence | No inter-source pass | Evidence-conflict phase before heads run |
| Citations | Evidence IDs only | Evidence / fact / rule / constraint / graph-edge / hypothesis |
| Fast-path | Bypasses `DecisionGraph` | Same envelope, empty matrix, optional `fast_path` |
| Neighbors | Named only | Optional ingress DTO + egress envelope; VectorPrism/ChorusGraph are **examples**, not runtime deps |
| Ops | Fast-path latency only | Parallel pool, timeouts, partial failure, config hash |
| Experimental latent | In tree, unbound | Runtime-excluded; no import from `engine.py` |

### 0.1 Freeze corrections (still schema `1.1.0`)

Applied before lock, from review. Not a v1.2.

1. **Head input partition.** `formal` never reads `PolicyRule` and never emits `hard_veto`. `policy` is the only deontic / veto head. The same prohibition MUST NOT be counted as two independent methods.
2. **`CitationKind.HYPOTHESIS`.** Fast-path `axiomatic` cites `hypothesis.id`. No special-case citation path.
3. **Calibration status.** Weights and τ values are engineering priors, not empirically optimal constants.
4. **`EvaluatorPair`** sorts in a `mode="before"` validator. No in-place mutation of a constructed model.
5. **Predicate parser** is recursive descent or a restricted `ast.parse` visitor. Regex parsing is forbidden.
6. **Pool isolation.** Heads share read-only context. No scratchpad writes onto `ReasoningContext` or `Hypothesis`.
7. **Neighbor names are reference implementations.** The macro stack MAY compose ChorusGraph → VectorPrism → PrismThinker → ChorusGraph. The package boundary MUST stay decoupled: `engine.py` MUST NOT import `vectorprism`, `chorusgraph`, torch, or an ANN client. `from_vectorprism()` is the typed VectorPrism join (text, trust, `numeric_claims`, `negates_id`). `to_chorusgraph()` is the typed ChorusGraph join (`HARD_VETO`/`CONFLICT`/`INSUFFICIENT_EVIDENCE` → tools `[]`). Chunking, dense embedding, and ANN indexing are VectorPrism (or another retriever), never `core/`. Tool execution is ChorusGraph (or another orchestrator), never `core/`.
8. **Pool copies and crash messages.** Each worker — `ThreadPoolExecutor` **or** an isolated process — receives a deep copy / serialized copy of `ReasoningContext` and `Hypothesis`. `EvaluatorError.message` is a single-line `"{ExcType}: {exc}"`; full tracebacks are logged on `prismthinker`, never placed on the graph.
9. **Polarity-mismatched claims are dropped.** `drop_mismatched_claims()` removes claims whose polarity is outside the head `verdict` band before \(\Delta\) runs, and tags the head `REASON_POLARITY_MISMATCH`. Matching claims are kept. The original result object is not mutated.
10. **Effective \(\tau\).** `tau_base` / `qualified_tau` remain engineering priors. When `EngineConfig.dynamic_tau=True` (default), the runtime derives deterministic \(\tau_{\text{eff}}\) / \(\tau_{\text{qualified,eff}}\) from run-local conditions (§15.2). `dynamic_tau=False` restores the raw prior. The flags `dynamic_tau`, `isolate_heads`, and `stop_on_first_resolving` are hashed into `config_hash`.
11. **Preferred production pool.** Standard heads run in isolated worker processes when `isolate_heads=True` (default). `ThreadPoolExecutor` remains supported when `isolate_heads=False` and for custom evaluators that cannot be pickled. Both modes preserve the same `EvaluatorResult` / `DecisionGraph` contract.

---

## 1. System Context & Component Topology

`prismthinker` is a standalone evaluation library. It does **not** require a retriever or an orchestrator at runtime.

In the **macro application stack** the three products compose. At the **package boundary** they stay decoupled. [VectorPrism](https://github.com/insightitsGit/VectorPrism) finds evidence. PrismThinker tests the logic. [ChorusGraph](https://github.com/insightitsGit/ChorusGraph) runs the workflow. Joins are adapters only (`from_vectorprism()`, `to_chorusgraph()`). Callers MAY instead build a `ReasoningContext` from SQL, a policy registry, or a test fixture, and MAY honor the egress envelope in LangGraph, CrewAI, or a custom runtime.

A `HARD_VETO` is a refuse, not a suggestion. `evaluate()` MUST NOT retrieve, index, or call tools.

```
[ User request / autonomous task ]
        │
        ▼
ChorusGraph                 orchestration & candidate tool calls
        │
        ▼
VectorPrism                 rhetorical/causal chunks, PSM 1024d
        │  from_vectorprism()     # adapter; not imported by engine.py
        ▼
PrismThinker.evaluate       ReasoningContext → DecisionGraph
        │  to_chorusgraph()       # adapter; not imported by engine.py
        ▼
ChorusGraph                 EXECUTE | ANSWER | REFUSE | ESCALATE | GATHER
                            REFUSE / ESCALATE / GATHER ⇒ allowed_tools = []
```

Internal evaluate() topology:

```
                    [ optional ingress adapter ]
                    [ e.g. RetrievedDocument / any store ]
                                    │
                                    ▼
                     ReasoningContext + Hypothesis
                                    │
                                    ▼
                     ┌──────────────────────────────────────┐
                     │  Epistemic Regime Classifier         │
                     │  (AST probe + feature scorer)        │
                     └──────────────────┬───────────────────┘
                                        │
                        Fast-path eligible?
                     ┌──────────────────┴───────────────────┐
                     ▼ YES                                  ▼ NO
        ┌─────────────────────────┐            ┌────────────────────────┐
        │ Axiomatic Fast-Path     │            │ Evidence Conflict Pass │
        │ (AST whitelist walker)  │            └───────────┬────────────┘
        └────────────┬────────────┘                        ▼
                     │                         ┌────────────────────────┐
                     │                         │ Dynamic Selector       │
                     │                         │ (regime + domain + min)│
                     │                         └───────────┬────────────┘
                     │                                     ▼
                     │                         ┌────────────────────────┐
                     │                         │ Evaluator Pool (N≥3)   │
                     │                         │ Parallel, isolated     │
                     │                         └───────────┬────────────┘
                     │                                     ▼
                     │                         ┌────────────────────────┐
                     │                         │ Δ_ij Engine            │
                     │                         └───────────┬────────────┘
                     │                                     ▼
                     │                         ┌────────────────────────┐
                     │                         │ Counterfactual Engine  │
                     │                         │ (budgeted, typed)      │
                     │                         └───────────┬────────────┘
                     │                                     ▼
                     │                         ┌────────────────────────┐
                     │                         │ Disposition Lattice    │
                     └─────────────────────────┤ + Radar assembly       │
                                               └───────────┬────────────┘
                                                           ▼
                                              DecisionGraph (schema 1.1.0)
                                                           │
                                                           ▼
                                              [ optional egress adapter ]
                                              [ e.g. orchestrator / ChorusGraph ]
                                                           │
                                              EXECUTE | ANSWER | REFUSE
                                              ESCALATE | GATHER
```

Every path, including fast-path, emits a `DecisionGraph`. Downstream never special-cases a raw scalar.

---

## 2. Architectural Invariants

These are testable. A build that violates any of them is incorrect, even if tests of \(\Delta\) pass.

1. **Preference Isolation.** `ReasoningContext` has no user, persona, history, or preference fields. The engine entrypoint accepts only `ReasoningContext`. Presentation weights live in `PresentationContext`, which adapters MUST NOT pass into the pool, contradiction engine, or counterfactual engine. Enforced by type and by a unit test that inspects model fields.

2. **Traceable Claims.** Every `Claim` MUST contain at least one `Citation` of kind `evidence`, `fact`, `rule`, `constraint`, `graph_edge`, or `hypothesis`. Uncited claims are kept for audit and receive `confidence *= UNCITED_PENALTY` (`0.5`) plus `REASON_UNCITED_CLAIM`.

3. **Paraconsistent Preservation.** The engine never averages conflicting verdicts into a compromise. Under `CONFLICT`, `recommended_verdict` is `null`. Both states remain in `evaluators`.

4. **Methodological Independence.** Two heads are independent only if they have distinct `independence_class` values and distinct backend kinds **or** distinct non-LLM algorithms. Two LLM system prompts do **not** count as two classes. The registry MUST reject a selected set that violates this. Evaluating the same `PolicyRule` in both `formal` and `policy` is a double-count and is forbidden (see invariant 10).

5. **Uniform Envelope.** Fast-path and dialectic produce the same `DecisionGraph` schema.

6. **Authorized Veto Only.** `hard_veto=True` is honored only when `EvaluatorCapability.may_hard_veto` is true **and** the head verdict is `reject`. The only default veto-capable head is `policy`. `formal`, `utility`, `empirical`, `causal`, and every LLM backend MUST have `may_hard_veto=False`.

7. **No Silent Head Loss.** A timed-out or crashed required head becomes `undetermined` with an `EvaluatorError`. It is never omitted from `evaluators`.

8. **Config Reproducibility.** Weights, \(\tau\), selector tables, and probe budgets are versioned configuration. `DecisionGraph.config_hash` is SHA-256 of the canonical JSON of the active `EngineConfig`.

9. **Latent Track Isolation.** `experimental.latent` MUST NOT be imported by `engine.py` or any production module in v1.1.

10. **Head Input Partition.** `formal` asks: *is this logically / structurally valid?* `policy` asks: *is this permitted?*  
    - `formal` consumes `ConstraintSpec`, `FactSpec`, and hypothesis / action structure. It MUST NOT read `context.policy_rules` and MUST NOT interpret `DeonticModality`, `RuleSeverity`, jurisdiction, or `HARD_VETO`.  
    - `policy` consumes `PolicyRule` for its verdict. It MAY bind `fact.*` and `action.*` paths. It MUST NOT treat `ConstraintSpec` as a deontic rule and MUST NOT emit `hard_veto` from a constraint.  
    - They MAY share a predicate *parser*. They MUST NOT share a decision procedure.

---

## 3. Directory Layout

```text
prismthinker/
├── pyproject.toml
├── README.md
├── src/
│   └── prismthinker/
│       ├── __init__.py
│       ├── config.py                 # EngineConfig, hashes, defaults
│       ├── reason_codes.py           # Closed reason-code taxonomy
│       ├── classifier/
│       │   ├── __init__.py
│       │   ├── ast_safe.py           # Whitelisted AST walker + arithmetic
│       │   ├── features.py           # Regime feature extractor
│       │   └── router.py             # Two-stage regime router
│       ├── core/
│       │   ├── __init__.py
│       │   ├── schemas.py            # All Pydantic contracts
│       │   ├── evidence.py           # Inter-evidence conflict pass
│       │   ├── selector.py           # Registry, cardinality, overlays
│       │   ├── contradiction.py      # Closed-form Δ_ij
│       │   ├── uncertainty.py        # Saturated U
│       │   ├── disposition.py        # Priority lattice
│       │   ├── counterfactual.py     # Typed, budgeted probes
│       │   ├── predicates.py         # Shared predicate parser only (not a decision head)
│       │   └── engine.py             # Orchestration entrypoint
│       ├── evaluators/
│       │   ├── __init__.py
│       │   ├── base.py               # Evaluator + backend protocol
│       │   ├── formal.py             # Structural / invariant satisfiability (no PolicyRule)
│       │   ├── empirical.py          # Observation / threshold scorer
│       │   ├── causal.py             # Graph reachability + intervention
│       │   ├── policy.py             # Structured deontic gates
│       │   └── utility.py            # Typed objective / SLA scorer
│       ├── adapters/                 # optional; never imported by engine.py
│       │   ├── __init__.py
│       │   ├── documents.py          # RetrievedDocument + from_documents / langchain / llamaindex
│       │   ├── vectorprism.py        # from_vectorprism() typed join (text, trust, claims, negates_id)
│       │   ├── rag.py                # allow_generation() for standard RAG LLM gating
│       │   ├── chorusgraph.py        # Egress envelope (reference orchestrator)
│       │   └── clients.py            # optional HTTP; not on evaluate()
│       └── experimental/
│           └── latent/               # Research only; not imported at runtime
│               ├── __init__.py
│               ├── projections.py
│               └── steering.py
├── bench/                            # not on the evaluate() path
│   ├── chunks.py                     # hashed-ngram stand-in windows (not VectorPrism PSM)
│   ├── encode.py                     # 384-d hasher; production encoding is VectorPrism 1024d
│   └── index.py                      # in-process EvidenceIndex for local tests only
└── tests/
    ├── conftest.py
    ├── test_invariants.py
    ├── test_classifier.py
    ├── test_ast_safe.py
    ├── test_evaluators.py
    ├── test_evidence.py
    ├── test_contradiction.py
    ├── test_uncertainty.py
    ├── test_disposition.py
    ├── test_counterfactual.py
    ├── test_adapters.py
    └── test_end_to_end.py
```

---

## 4. Data Contracts

All models live in `core/schemas.py` unless noted. Extra fields are forbidden on `ReasoningContext` (`model_config = extra="forbid"`) so preference data cannot be smuggled in.

JSON values in payloads are `str | int | float | bool | None | list | dict` of the same. No objects without a schema.

### 4.1 Enumerations

```python
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
    # HUMAN_REVIEW removed as a disposition. See review_required.

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
    HYPOTHESIS = "hypothesis"   # query / assertion / fast-path expression via hypothesis.id

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
    LLM = "llm"          # optional, isolated, never veto-capable

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
```

### 4.2 Citations, atoms, facts

```python
class Citation(BaseModel):
    kind: CitationKind
    ref: str

class AssumptionAtom(BaseModel):
    id: str
    predicate: str          # normalized, e.g. "network_partition_ms <= 500"
    polarity: bool          # True = assumed to hold
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
    mutable: bool = False   # only mutable facts may be probed
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
```

`structured_facts` in context is a map of `key -> FactValue`. A parallel `fact_specs` map defines types and probe legality. A value whose key has no spec is accepted as immutable `STRING` and is **not** probeable.

### 4.3 Hypothesis and action

Every run scores exactly one hypothesis. Heads do not invent a private decision target.

```python
class CandidateAction(BaseModel):
    id: str
    kind: ActionKind
    name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""

class Hypothesis(BaseModel):
    id: str
    statement: str                 # canonical proposition all heads score
    action: Optional[CandidateAction] = None
    # APPROVE means "the action should proceed" or "the assertion holds"
```

If the caller supplies evidence and a query but no hypothesis, the engine constructs:

- `kind=ASSERTION` when there is no action
- `statement=query`
- `id="hyp:" + sha256(query)[:16]`

This is explicit construction, not silent reinterpretation. The constructed hypothesis is stored on the graph.

### 4.4 Evidence

```python
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
```

`numeric_claims` is the only way unstructured prose participates in numeric conflict and empirical scoring. Adapters MAY extract numbers; heads MUST NOT parse arbitrary prose for math.

### 4.5 Policy, causal graph, utility

```python
class PolicyRule(BaseModel):
    id: str
    modality: DeonticModality
    predicate: str          # matcher over action.name, action.payload, facts
    severity: RuleSeverity
    jurisdiction: Optional[str] = None
    text: str = ""

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
    reject_below: Optional[float] = None   # utility score threshold
    caution_below: Optional[float] = None
```

v1.0 `rules: List[str]` is accepted only as display text. Evaluation uses `policy_rules`. A string rule with no `PolicyRule` counterpart is inert and emits `REASON_UNSTRUCTURED_RULE_IGNORED`.

### 4.6 Context (engine input)

```python
class ReasoningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hypothesis: Optional[Hypothesis] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)
    structured_facts: Dict[str, FactValue] = Field(default_factory=dict)
    fact_specs: Dict[str, FactSpec] = Field(default_factory=dict)
    policy_rules: List[PolicyRule] = Field(default_factory=list)
    constraints: List[ConstraintSpec] = Field(default_factory=list)
    causal_graph: Optional[CausalGraph] = None
    objective: Optional[ObjectiveSpec] = None
    domain: Optional[str] = None
    force_regime: Optional[EpistemicRegime] = None
    force_evaluators: List[str] = Field(default_factory=list)

class PresentationContext(BaseModel):
    """Downstream only. NEVER accepted by PrismThinker.evaluate()."""
    user_id: Optional[str] = None
    persona_weights: Dict[str, float] = Field(default_factory=dict)
    history_refs: List[str] = Field(default_factory=list)
```

### 4.7 Evaluator I/O

```python
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
    message: str  # single-line "{ExcType}: {exc}"; never traceback.format_exc()

class EvaluatorResult(BaseModel):
    evaluator: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    claims: List[Claim] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    premise_ids: List[str] = Field(default_factory=list)          # fact keys + rule ids used as given
    assumptions: List[AssumptionAtom] = Field(default_factory=list)
    constraints_applied: List[ConstraintApplication] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    hard_veto: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    backend: BackendKind
    latency_ms: float = 0.0
```

`verdict` is the only conclusion field. Claim `polarity` MUST be consistent with `verdict` within `0.5`:

| Verdict | Required polarity band |
|---|---|
| approve | \(+0.34\) to \(+1.0\) |
| caution | \(-0.33\) to \(+0.33\) |
| reject | \(-1.0\) to \(-0.34\) |
| undetermined | claims optional; if present, polarity ignored for \(\Delta\) |

Inconsistent claims are **dropped from `EvaluatorResult.claims`** (and therefore from \(\Delta\)) and the head is tagged `REASON_POLARITY_MISMATCH`. Matching claims remain. `undetermined` heads do not drop claims on polarity.

### 4.8 Contradiction, probes, radar, graph

```python
class ConflictComponent(BaseModel):
    conclusion_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    premise_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    constraint_conflict: float = Field(ge=0.0, le=1.0, default=0.0)
    assumption_conflict: float = Field(ge=0.0, le=1.0, default=0.0)

class EvaluatorPair(BaseModel):
    model_config = ConfigDict(frozen=True)
    left: str
    right: str

    @model_validator(mode="before")
    @classmethod
    def sort_lexicographical(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            left, right = payload.get("left"), payload.get("right")
            if left == right:
                raise ValueError("pair must contain two distinct evaluators")
            if left and right and left > right:
                payload["left"], payload["right"] = right, left
            return payload
        return data

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
    delta_after: float              # actually re-evaluated, not predicted
    resolving: bool
    resolving_condition: str
    flips: List[str] = Field(default_factory=list)  # evaluator names whose verdict changed

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
    schema_version: Literal["1.1.0"] = "1.1.0"
    run_id: str
    created_at: datetime
    config_hash: str
    query: str
    hypothesis: Hypothesis
    regime: EpistemicRegime
    selected_evaluators: List[str]
    classifier: ClassifierTrace
    recommended_verdict: Optional[Verdict]
    recommended_rationale: str          # lattice rule id, never a blended essay
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
```

`confidence` on the graph is the unweighted mean of **determined** head confidences. It is not a blend of verdicts.

---

## 5. Neighbor Contracts

Neighbors are **optional**. `PrismThinker.evaluate(ReasoningContext)` is complete without them. HTTP clients live in `adapters/` and MUST NOT be imported from `engine.py`.

Two operating modes, same `evaluate()` contract:

1. **Sovereign Prism stack.** ChorusGraph → VectorPrism → `from_vectorprism()` → PrismThinker → `to_chorusgraph()` → ChorusGraph. VectorPrism rejects cosine funny neighbors; PrismThinker tests logic; ChorusGraph honors the envelope.
2. **Universal RAG plug-in.** Any retriever (LangChain, LlamaIndex, Pinecone, Weaviate, Qdrant, Chroma, pgvector, SQL, fixture) dumps documents. The caller maps them to `EvidenceItem`s (or `from_langchain` / `from_llamaindex` / `from_documents`), types the `Hypothesis` / `PolicyRule`s, and gates LLM generation on the `DecisionGraph`. PrismThinker does not care how the text was retrieved.

### 5.1 Ingress adapter (e.g. document store / VectorPrism / standard RAG)

Canonical types: `RetrievedDocument`, `from_documents()`. LangChain / LlamaIndex helpers are duck-typed and add no extra package dependency. `from_vectorprism()` is the VectorPrism join: it calls `from_documents()` and is the only supported mapping from VectorPrism payloads into `ReasoningContext`. `VectorPrismDocument` is an alias of `RetrievedDocument`.

```python
class RetrievedDocument(BaseModel):
    id: str
    text: str
    source: str
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retrieved_at: Optional[datetime] = None

def from_documents(
    query: str,
    documents: List[RetrievedDocument],
    *,
    hypothesis: Optional[Hypothesis] = None,
    facts: Optional[Dict[str, FactValue]] = None,
    fact_specs: Optional[Dict[str, FactSpec]] = None,
    extra: Optional[ReasoningContext] = None,
) -> ReasoningContext:
    ...
```

Mapping rules:

- `EvidenceItem.id = document.id`
- `content = text`
- `trust = metadata.trust` when well-typed; otherwise `clip(score, 0, 1)` as a **fallback only**. Retrieval rank / cosine similarity is topical relevance, not truth or authority.
- `provenance_hash = sha256(id + source + text)`
- `numeric_claims` copied from `metadata.numeric_claims` if well-typed; otherwise empty. Evaluators consume these numbers; they MUST NOT parse free-form prose for the same values.
- `metadata.negates_id` / `metadata.negates_ids` are preserved on `EvidenceItem.metadata` so the evidence-conflict pass can emit `EXPLICIT_NEGATION` before heads run.
- Retrieval rank/score MUST NOT enter evaluators as a preference signal.
- Lifting `policy_rule` / `causal_graph` from chunk metadata is optional convenience. Production `PolicyRule` and `CausalGraph` belong in a policy registry / system config passed by the caller, not in ANN chunks.
- The **caller** (or orchestrating agent) types the `Hypothesis`. A retriever finds text; it does not know what action is being decided.
- **VectorPrism (or another retriever) owns chunk / encode / ANN.** PrismThinker does not cut documents, generate dense embeddings, or maintain indices. Local hashed n-gram retrieve lives in `bench/` as a stand-in. Bare token windows with no claims starve empirical/policy and correctly `GATHER`. `engine.py` MUST NOT import encode, index, chunks, VectorPrism, torch, or an ANN client.

### 5.2 Egress directive (e.g. orchestrator / ChorusGraph)

```python
class ChorusGraphEnvelope(BaseModel):
    directive: ChorusGraphDirective
    decision_graph: DecisionGraph
    allowed_tools: List[str]
    gather_fact_keys: List[str] = Field(default_factory=list)
    gather_questions: List[str] = Field(default_factory=list)
```

| Disposition / flags | Directive | `allowed_tools` |
|---|---|---|
| `HARD_VETO` | `REFUSE` | `[]` always |
| `CONFLICT` | `ESCALATE` | `[]` |
| `INSUFFICIENT_EVIDENCE` | `GATHER` | `[]` |
| `CONSENSUS` / `QUALIFIED_CONSENSUS` + action + `APPROVE` | `EXECUTE` | caller-supplied allowlist, unchanged |
| `CONSENSUS` / `QUALIFIED_CONSENSUS` + assertion + `APPROVE` | `ANSWER` | `[]` |
| `CONSENSUS` / `QUALIFIED_CONSENSUS` + `REJECT` | `REFUSE` | `[]` |
| `CONSENSUS` / `QUALIFIED_CONSENSUS` + `CAUTION` | `ESCALATE` | `[]` |
| `review_required` and directive would be `EXECUTE` | promoted to `ESCALATE` | `[]` |

`to_chorusgraph()` is the only supported mapping from a `DecisionGraph` into a ChorusGraph directive envelope. The orchestrator (reference: ChorusGraph, or any runtime that consumes this envelope) MUST NOT generate tool calls on `REFUSE`, `ESCALATE`, or `GATHER`. `HARD_VETO` → `REFUSE`. `CONFLICT` (\(\Delta_{\max} > \tau\), default \(\tau_{\text{base}}=0.40\)) → `ESCALATE`. Both strip `allowed_tools` to `[]`. That is how PrismThinker protects ChorusGraph without importing it.

---

## 6. Phase 1 — Regime Classification & Fast-Path

Classification is **not** an LLM in v1.1. It is a deterministic two-stage function.

### 6.1 Stage A — AST probe

`classifier/ast_safe.py` walks the query with a whitelist `ast.NodeVisitor`. It never calls `eval()` or `exec()`.

**Allowed nodes:** `Expression`, `Constant` (int/float only), `BinOp`, `UnaryOp`, `Add`, `Sub`, `Mult`, `Div`, `FloorDiv`, `Pow`, `UAdd`, `USub`, `Load`, `Expr`.

**Forbidden (reject fast-path):** `Call`, `Attribute`, `Name`, `Subscript`, `List`, `Dict`, `Mod`, `BitAnd`, `BitOr`, `MatMult`, `Await`, comprehensions, f-strings, any dunder.

**Eligibility:** after stripping whitespace, the entire query parses as one allowed expression **and** contains no leftover prose. Mixed strings such as `"is 2+2 legal to cache?"` fail Stage A.

**Non-standard math** (`mod`, quaternion, bases other than 10, named functions) fails Stage A and continues to Stage B. They do **not** auto-route to `OPEN_DIALECTIC` unless Stage B is also inconclusive.

**Evaluation:** a literal walker computes the value in < 1 ms. Division by zero → not fast-path, regime `CLOSED_FORMAL` still possible via Stage B, head `formal` returns `reject` with `REASON_DIVISION_BY_ZERO` if the hypothesis is that the expression is well-defined.

**Fast-path `DecisionGraph`:**

- `regime = CLOSED_FORMAL`
- `selected_evaluators = ["axiomatic"]`
- `evaluators["axiomatic"]` = approve, confidence 1.0, claim citations `[Citation(kind=HYPOTHESIS, ref=hypothesis.id)]`
- `contradiction_score = 0.0`
- `uncertainty_score = 0.0`
- `disposition = CONSENSUS`
- `recommended_verdict = APPROVE`
- `fast_path = FastPathResult(...)`
- `review_required = False`

`axiomatic` is a synthetic head. It is not in the dialectic registry and does not participate in independence checks.

### 6.2 Stage B — Feature regime scorer

If Stage A fails, compute scores in \([0,1]\) for the four non-fast regimes. Each feature is a deterministic predicate. Weights below are defaults in `EngineConfig.classifier`.

| Feature | EMPIRICAL | POLICY | PRAGMATIC | OPEN (residual) |
|---|---|---|---|---|
| ≥1 numeric `FactValue` or `numeric_claims` | +0.35 |  | +0.10 |  |
| `causal_graph` present | +0.25 |  | +0.15 |  |
| `objective` or SLA-like fact keys (`latency`, `cost`, `qps`, `ttl`) |  |  | +0.40 |  |
| ≥1 `PolicyRule` or constraint with `hard_veto`/`prohibition` |  | +0.45 |  |  |
| Domain overlay in `{legal, security, privacy, healthcare, finance}` |  | +0.25 |  |  |
| Lexemes: `p-value`, `distribution`, `posterior`, `sample` | +0.20 |  |  |  |
| Lexemes: `allow`, `deny`, `gdpr`, `retention`, `pii`, `must not` |  | +0.20 |  |  |
| Lexemes: `sla`, `p99`, `cache`, `throughput`, `budget` |  |  | +0.20 |  |
| ≥2 of {rules, graph, objective, numeric facts} present |  |  |  | +0.30 |
| Query length > 240 chars and ≥2 feature families fire |  |  |  | +0.20 |

Scores are clipped to \([0,1]\).

**Decision:**

1. `force_regime` set → that regime, `override_applied=True`.
2. Else let \(s_1 \ge s_2\) be the top two scores.  
   - If \(s_1 < 0.35\) **or** \(s_1 - s_2 < 0.10\) → `OPEN_DIALECTIC`.  
   - Else → argmax regime.
3. `CLOSED_FORMAL` from Stage B only when the query is math-shaped but failed the whitelist (e.g. `2 + x`). Then the pool runs with `formal` required; there is no axiomatic short-circuit.

---

## 7. Phase 2 — Dynamic Evaluator Selection

### 7.1 Versioned table (`selector.v1_1`)

| Regime | Required | Default optional | Hard minimum |
|---|---|---|---|
| `CLOSED_FORMAL` (fast-path) | `axiomatic` | — | 1 (synthetic) |
| `CLOSED_FORMAL` (pool) | `formal` | `empirical` | 3 after fill |
| `EMPIRICAL` | `empirical`, `causal` | `formal` | 3 |
| `POLICY_NORMATIVE` | `policy`, `formal` | `utility`, `empirical` | 3 |
| `PRAGMATIC_SYSTEMS` | `utility`, `causal`, `empirical` | `policy` | 3 |
| `OPEN_DIALECTIC` | all five | — | 5 |

**Fill rule:** if `required ∪ optional ∪ force_evaluators` has fewer than `min_heads`, add unused registry heads in this order: `formal`, `policy`, `empirical`, `causal`, `utility`, until the minimum is met or the registry is exhausted.

**Domain overlays** (additive, never remove a required head):

| Domain | Force-include |
|---|---|
| `legal`, `security`, `privacy`, `healthcare`, `finance` | `policy` |
| `sre`, `infra`, `performance` | `utility`, `empirical` |
| `science`, `telemetry` | `empirical`, `causal` |

`force_evaluators` is unioned after overlays. Independence is re-checked. If the forced set violates independence (e.g. two LLM heads), the engine fails closed: `INSUFFICIENT_EVIDENCE`, `REASON_SELECTOR_INDEPENDENCE`, `review_required=True`.

### 7.2 Why v1.0 maps changed

- Policy decisions often depend on measured harm → `empirical` is optional-by-default, not forbidden.
- Empirical claims need invariants → `formal` is the first fill head.
- Two-head regimes made \(\Delta_{\max}\) a single pair. Minimum 3 is mandatory for dialectic.

---

## 8. Phase 3 — Evaluator Backend Protocol

### 8.1 Contract

```python
class Evaluator(ABC):
    capability: EvaluatorCapability

    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        """Pure. No I/O except an optional pinned LLM backend behind a cache."""
```

Rules for every implementation:

1. Receive `ReasoningContext` and `Hypothesis` as read-only. Treat both as immutable. Heads MUST NOT assign attributes, mutate lists/dicts on the shared objects, or store scratchpad state on them. Local variables only. Required because the pool runs concurrently (isolated processes by default; `ThreadPoolExecutor` when `isolate_heads=False`).
2. Score `hypothesis` only. Do not invent a second action.
3. If required inputs are missing, return `undetermined`, confidence `0.0`, and concrete `unresolved_questions`. Do not guess.
4. LLM backends are opt-in via `EngineConfig.llm.enabled`. Temperature `0`, pinned `model_id`, cache key `sha256(model_id + schema_version + canonical(context, hypothesis, evaluator))`. LLM output is schema-validated; invalid JSON → `undetermined` + `REASON_LLM_INVALID`. LLM MAY NOT set `hard_veto`.
5. Default v1.1 heads are **non-LLM**.
6. Honor the head input partition (invariant 10). `formal` MUST NOT access `context.policy_rules`.

### 8.2 Shared predicate parser (`core/predicates.py`)

`formal` and `policy` share **only** this parser. It is not an evaluator.

Implementation MUST be a recursive-descent parser **or** a restricted `ast.parse` visitor (`ast.parse(expr, mode="eval")` + whitelist). Regex parsing is forbidden. No `eval()` / `exec()`. Nested `and` / `or` / `not` MUST evaluate deterministically.

Predicate grammar (v1.1):

```text
expr     := or_expr
or_expr  := and_expr ("or" and_expr)*
and_expr := cmp ("and" cmp)*
cmp      := path OP value | "not" cmp | "(" expr ")"
OP       := "==" | "!=" | "<" | "<=" | ">" | ">=" | "in"
path     := "fact.<key>" | "action.name" | "action.payload.<key>"
value    := number | bool | string | enum-list
```

### 8.3 `formal` — `BackendKind.SOLVER` / structural satisfiability

**Independence class:** `formal_symbolic`.  
**May veto:** no.  
**Question:** *Is this logically / structurally valid?*

**Consumes:** `ConstraintSpec`, `FactSpec`, `structured_facts`, `hypothesis.action`.  
**MUST NOT consume:** `policy_rules`, `DeonticModality`, `RuleSeverity`, jurisdiction, `HARD_VETO`. There is no linkage field from a constraint to a policy rule; do not add one.

Algorithm:

1. Type-check every present fact against its `FactSpec` (type, range, enum membership).
2. Bind and evaluate each `ConstraintSpec.predicate` with the shared parser.
3. Unbound required path on a constraint → `undetermined`, ask for that fact key.
4. Any type/range failure or false constraint → `reject`, `hard_veto=False`.
5. All checked invariants hold → `approve`.
6. No constraints and all present facts well-typed → `approve` (the state is structurally valid).
7. `formal` verdicts are `approve` | `reject` | `undetermined` only. No deontic `caution`.

Confidence: `1.0` if every referenced path bound; else `0.6` if optional paths missing; `0.0` if undetermined.

This is **not** a general SMT solver in v1.1. A later version may add an optional SMT backend behind the same capability. Do not stub SMT.

Adding, removing, or changing `policy_rules` MUST NOT change a `formal` result when facts, specs, constraints, and hypothesis are held fixed. That is a required test.

### 8.4 `empirical` — `BackendKind.STATS`

**Independence class:** `empirical_stats`.  
**May veto:** no.

**Method:** score numeric observations against hypothesis-relevant thresholds.

1. Collect numbers from `structured_facts` with numeric types and from `evidence.numeric_claims`.
2. If fewer than `min_observations` (default 1 for a single threshold fact, 3 for a distribution claim) → `undetermined`.
3. If two evidence items conflict on the same numeric key with severity ≥ `0.7` (from the evidence pass) → `caution` or `undetermined` if they straddle the decision threshold.
4. Threshold tests: if a fact key referenced by the hypothesis payload or objective target exists, compute whether the observation meets it. Approve / reject / caution from the signed error.
5. Confidence: `1 - min(1, cv)` when ≥3 samples exist (`cv` = coefficient of variation); otherwise `0.55` for a single clean observation, `0.3` if any severe evidence conflict touches the key.

No prose NLP. No invented posteriors. If you cannot see a number, you do not emit a posterior.

### 8.5 `causal` — `BackendKind.GRAPH`

**Independence class:** `causal_graph`.  
**May veto:** no.

**Method:** graph queries, not narrative causality.

1. No `causal_graph` → `undetermined` + `REASON_MISSING_CAUSAL_GRAPH`.
2. Identify treatment and outcome nodes from `hypothesis.action.payload` keys (`treatment`, `outcome`) or from `ObjectiveSpec.terms[].fact_key` as outcomes and `action.payload` keys as treatments.
3. `reachable(treatment, outcome)` on the directed graph.
4. If the hypothesis claims an effect and no path exists → `reject` (not a veto).
5. If a path exists and an intervention node is listed in `payload.do` / fact key `do.<node>`, treat incoming edges to that node as cut (do-calculus delete-incoming). Re-check reachability.
6. Signed edges: if all paths have a negative product of signs and the hypothesis claims a positive effect → `reject`.
7. Missing treatment/outcome binding → `undetermined`.

Confidence: `0.85` if bindings explicit; `0.5` if inferred from objective keys; `0.0` if undetermined.

### 8.6 `policy` — `BackendKind.RULES`

**Independence class:** `policy_deontic`.  
**May veto:** yes.  
**Question:** *Is this permitted?*

**Consumes:** `PolicyRule` (modality, severity, jurisdiction, predicate) plus fact/action bindings.  
**MUST NOT consume:** `ConstraintSpec` as a deontic source. Constraints never produce `hard_veto`.

**Method:** deontic match against `PolicyRule` list.

1. Empty `policy_rules` and domain not in the policy overlay set → `undetermined` + `REASON_MISSING_POLICY_RULES` (except when the head was only added by cardinality fill; then `undetermined`).
2. Evaluate each `PolicyRule.predicate` with the shared parser (§8.2).
3. First matching `PROHIBITION` + `HARD_VETO` → `reject`, `hard_veto=True`.
4. Matching `PROHIBITION` + `BLOCK` → `reject`, no veto.
5. Matching `OBLIGATION` whose predicate is false → same as (3)/(4) by severity.
6. Matching `PERMISSION` only, no prohibition → `approve`.
7. Only `CAUTION` severity hits → `caution`.

`formal` and `policy` can disagree without contradiction in method: facts can be structurally valid (`formal` approve) and still prohibited (`policy` reject). That is a real \(\Delta\), not a double-counted rule.

### 8.7 `utility` — `BackendKind.RULES` (numeric objective)

**Independence class:** `utility_objective`.  
**May veto:** no.

**Method:**

1. No `ObjectiveSpec` → `undetermined` + `REASON_MISSING_OBJECTIVE`.
2. For each term, read `fact_key`. Missing required fact → `undetermined`.
3. Normalize each term to \([0,1]\) given `minimum`/`maximum` from `FactSpec` or the term target.
   - maximize: \((x - min) / (max - min)\)
   - minimize: \(1 -\) that
   - hit: \(1 - |x - target| / span\)
4. Score \(u = \sum w_k \tilde{x}_k / \sum |w_k|\).
5. `u < reject_below` → `reject`. `u < caution_below` → `caution`. Else `approve`.
6. `sla_breach_is_reject` and the raw value misses `target` in the wrong direction → `reject` (still not a veto).

Confidence: `0.8` if all terms bound; else `0.0` undetermined.

### 8.8 Shared claim emission

Each head emits 1..N `Claim` objects whose `hypothesis_id` matches the run hypothesis. Supporting / contradicting evidence IDs MUST be subsets of `context.evidence[*].id`. `premise_ids` are fact keys and rule ids actually read. Assumptions are `AssumptionAtom`s, never free strings.

---

## 9. Phase 3b — Evidence Conflict Pass

Runs after classification, before the pool, skipped on fast-path.

For every pair of evidence items:

1. **Numeric mismatch.** Shared keys in `numeric_claims` with relative difference \(> 0.10\) (or absolute \(>\) spec step if present) → `NUMERIC_MISMATCH`, severity `min(1, rel / 0.5)`.
2. **Stale.** `freshness_hours` or `retrieved_at` older than `EngineConfig.evidence.stale_hours` (default 168) vs a newer item on the same `source` family → `STALE`, severity `0.4`.
3. **Source trust.** Same `numeric_claims` key, `|trust_i - trust_j| ≥ 0.5` and numeric mismatch → additional `SOURCE_TRUST`, severity `0.5`.
4. **Explicit negation.** `metadata.negates_id == other.id` → `EXPLICIT_NEGATION`, severity `1.0`.

Conflicts with `severity ≥ 0.7` set `review_required` later and are injected into empirical confidence. They are **not** automatically evaluator conflicts. The graph stores them on `evidence_conflicts` so ChorusGraph can tell source war from head war.

---

## 10. Phase 4 — Contradiction Measurement

Let \(i, j\) be distinct selected heads. Skip a pair if either result is missing (must not happen) or both are `undetermined` (emit \(\Delta=0\), `REASON_PAIR_BOTH_UNDETERMINED`).

### 10.1 Verdict polarity

\[
\pi(\text{approve})=+1,\quad
\pi(\text{caution})=0,\quad
\pi(\text{reject})=-1
\]

`undetermined` has no polarity.

### 10.2 Jaccard distance

\[
J_d(A,B)=\begin{cases}
0 & A\cup B=\emptyset\\
1-\dfrac{|A\cap B|}{|A\cup B|} & \text{otherwise}
\end{cases}
\]

### 10.3 Components (all clipped to \([0,1]\))

**Conclusion.** If either verdict is `undetermined`: \(C_{\text{conclusion}}=0\), code `REASON_PAIR_UNDETERMINED_SKIPPED`.  
Else \(C_{\text{conclusion}}=\tfrac12\bigl|\pi_i-\pi_j\bigr|\).

**Constraint.** Let \(S\) be satisfied ids, \(V\) violated ids (ignore `not_applicable` / `unchecked`).

\[
\text{inv}=|(S_i\cap V_j)\cup(S_j\cap V_i)|,\quad
U=S_i\cup S_j\cup V_i\cup V_j
\]

\[
C_{\text{constraint}}=\begin{cases}
0 & U=\emptyset\\
\text{inv}/|U| & \text{otherwise}
\end{cases}
\]

**Evidence.** Support sets \(E^+\), contradict sets \(E^-\).

\[
\text{inv}_e=\bigl|(E^+_i\cap E^-_j)\cup(E^+_j\cap E^-_i)\bigr|
\]

\[
C_{\text{evidence}}=\operatorname{clip}\bigl(
0.6\cdot\tfrac{\text{inv}_e}{\max(1,|E^+_i\cup E^+_j\cup E^-_i\cup E^-_j|)}
+0.4\cdot J_d(E^+_i,E^+_j),\;0,1\bigr)
\]

**Assumption.** Group atoms by normalized `predicate`. For predicates present in both heads, conflict is \(1\) if polarities differ, else \(0\).

\[
C_{\text{assumption}}=\begin{cases}
0 & \text{no shared predicates}\\
\text{mean of per-predicate conflicts} & \text{otherwise}
\end{cases}
\]

Unshared atoms do not increase \(C_{\text{assumption}}\). They may increase \(U\) if attached to `unresolved_questions`.

**Premise.**

\[
C_{\text{premise}}=J_d(P_i,P_j)
\]

where \(P\) is `premise_ids`.

### 10.4 Aggregate

Default weights (must sum to 1.0), stored in `EngineConfig.contradiction.weights`:

\[
w=(w_c,w_k,w_e,w_a,w_p)=(0.35,0.25,0.15,0.15,0.10)
\]

\[
\Delta_{ij}=w_c C_{\text{conclusion}}+w_k C_{\text{constraint}}+w_e C_{\text{evidence}}+w_a C_{\text{assumption}}+w_p C_{\text{premise}}
\]

Regime overrides are allowed only via config, not code branches. Invalid weights (not summing to 1 ± 1e-9) refuse to boot.

\(\Delta_{\max}\) is the max over pairs that include at least one determined head. Pairs with both undetermined are excluded from the max (they are 0 anyway).

**Critical pair:** \(\Delta_{ij} \ge \tau_{\text{base}}\) (`0.40`). Those populate `critical_conflicts`.

**Gate:** \(\Delta_{\max} > \tau_{\text{base}}\) is a conflict signal. It does **not** by itself become `HARD_VETO`. Veto is capability-driven (Phase 6).

### 10.5 Shared vs conflicting assumptions

- Shared: same normalized predicate, same polarity, appears in ≥2 determined heads.
- Conflicting: same predicate, opposite polarity, appears in ≥2 heads.

---

## 11. Phase 4b — Uncertainty

Orthogonal to \(\Delta\). Never fold \(\Delta\) into \(U\).

Let \(H_d\) be heads with verdict ≠ `undetermined`.

\[
\bar{c}=\begin{cases}
0 & H_d=\emptyset\\
\operatorname{mean}\{\text{confidence}(h):h\in H_d\} & \text{otherwise}
\end{cases}
\]

\[
\text{coverage}=\frac{|\{\text{evidence ids cited by any head}\}|}{\max(1,N_{\text{evidence}})}
\]

\[
\text{missing}=\frac{\#\text{ required FactSpecs with no value}}{\max(1,\#\text{ required FactSpecs})}
\]

\[
\tilde{n}=\min\bigl(1,\;N_{\text{unresolved}}/N_{\max}\bigr),\quad N_{\max}=10
\]

\[
U=\operatorname{clip}\bigl(
0.50(1-\bar{c})
+0.20(1-\text{coverage})
+0.20\cdot\text{missing}
+0.10\cdot\tilde{n},\;0,1\bigr)
\]

If there is no evidence and no required facts, `coverage` is 1.0 so empty closed-form / rule-only contexts are not punished. Missing required facts still raise \(U\).

---

## 12. Phase 5 — Counterfactual Probes

Run only when \(\Delta_{\max} > \tau_{\text{eff}}\) and at least one `FactSpec.mutable` exists. Skip on fast-path. \(\tau_{\text{eff}}=\tau_{\text{base}}\) when `dynamic_tau=False`.

### 12.1 Budget (`EngineConfig.counterfactual`)

| Knob | Default |
|---|---|
| `max_probes` | 12 |
| `timeout_ms` | 200 |
| `max_params` | 4 (highest prior, see below) |
| `stop_on_first_resolving` | false |

A probe is **resolving** when re-evaluated \(\Delta_{\max} \le \tau_{\text{eff}}\) and no authorized hard veto remains, **or** when it removes an authorized hard veto without creating a new one. `EngineConfig.stop_on_first_resolving` (default `false`) stops the probe loop after the first resolving hit.

`delta_after` is the value from a real re-run of active heads on a copied context. There is no predictive surrogate in v1.1. The v1.0 field `predicted_delta_after` is deleted.

### 12.2 Legal mutations

A fact is probeable iff all of:

- `FactSpec.mutable is True`
- type is `BOOL`, `INT`, `FLOAT`, `DURATION_MS`, or `ENUM`
- current value is present and well-typed

Generation:

- `BOOL`: flip once.
- `ENUM`: each other value, until budget.
- Numeric: walk `{value ± k·step}` within `[minimum, maximum]`. If `step` is missing, use \(10\%\) of span or `1.0`. Stop a parameter after the first resolving hit for that parameter.

### 12.3 Parameter priority

Score each mutable key:

\[
\text{prior}(k)=\#\{\text{heads that listed }k\text{ in premise\_ids}\}
+\mathbf{1}[k\text{ appears in a conflicting assumption predicate}]
\]

Probe highest prior first.

### 12.4 Unstructured evidence

Prose is not mutated. If \(\Delta_{\max}\) is high and no mutable facts exist, emit one synthetic `CounterfactualProbe`:

- `parameter_changed = ""`
- `resolving = false`
- `resolving_condition = "no_mutable_facts"`
- reason code `REASON_COUNTERFACTUAL_NO_SCHEMA`

Plus `unresolved_questions` asking for the missing `FactSpec`s.

### 12.5 Isolation

Probe re-evaluations use a deep copy of context. They MUST NOT write back into the original facts. Only the chosen probes (≤ `max_probes`) are stored on the graph, resolving first, then by largest \(\Delta\) drop.

---

## 13. Phase 6 — Disposition Lattice

First matching rule wins. This is arbitration by **priority**, not by averaging.

`determined` = heads with verdict in `{approve, reject, caution}`.  
`authorized_veto` = a head with `hard_veto=True`, `capability.may_hard_veto=True`, verdict `reject`. Unauthorized vetoes are stripped, logged as `EvaluatorError(unauthorized_veto)`, and ignored.

| # | Condition | Disposition | `recommended_verdict` | `recommended_rationale` |
|---|---|---|---|---|
| 1 | ≥1 `authorized_veto` | `HARD_VETO` | `REJECT` | `lattice.hard_veto` |
| 2 | `|determined| < 2` **or** \(U \ge 0.60\) | `INSUFFICIENT_EVIDENCE` | `null` | `lattice.insufficient` |
| 3 | \(\Delta_{\max} > \tau_{\text{base}}\) | `CONFLICT` | `null` | `lattice.conflict` |
| 4 | Majority of `determined` exists **and** (\(\Delta_{\max} > 0.20\) **or** any `caution` **or** any dissenting determined head) | `QUALIFIED_CONSENSUS` | majority verdict | `lattice.qualified` |
| 5 | All `determined` share one verdict and \(\Delta_{\max} \le 0.20\) | `CONSENSUS` | that verdict | `lattice.consensus` |
| 6 | Tie in majority (e.g. 1/1/1) | `CONFLICT` | `null` | `lattice.tie` |

Majority is a **count of heads**, not confidence-weighted. Confidence-weighting is a form of averaging and is forbidden.

The numeric cells `0.40` and `0.20` in the table are the **priors** (`tau_base`, `qualified_tau`). Lattice comparisons at runtime use \(\tau_{\text{eff}}\) and \(\tau_{\text{qualified,eff}}\) from §15.2. When `dynamic_tau=False`, those equal the priors and the table is literal.

### 13.1 Review routing (not a disposition)

`review_required` is true if any of:

- disposition is `HARD_VETO`
- disposition is `CONFLICT`
- \(U \ge 0.60\)
- any `evidence_conflicts.severity ≥ 0.7`
- any head reason code in `REVIEW_TRIGGERS` (see §16)
- `QUALIFIED_CONSENSUS` and `policy` verdict is `caution` or `reject`

`review_reasons` lists the matching predicates. The Epistemic Radar is always populated. Frontends SHOULD surface the radar when `review_required` is true; they MAY still render it otherwise.

---

## 14. Engine Orchestration

`PrismThinker.evaluate(context: ReasoningContext) -> DecisionGraph`

1. Reject `PresentationContext` by type. Validate `extra="forbid"`.
2. Materialize `hypothesis` if missing (§4.3).
3. Classify (§6).
4. If fast-path: assemble graph and return.
5. Evidence conflict pass (§9).
6. Select heads (§7).
7. Run heads in parallel. **Preferred production path:** isolated worker processes for the default registry when `isolate_heads=True` (default). `ThreadPoolExecutor` is used when `isolate_heads=False` or a selected head cannot be isolated. Each worker receives a **deep copy** (threads) or a serialized copy (processes) of `ReasoningContext` and `Hypothesis`. Heads MUST NOT write to those objects. On timeout/crash, write `EvaluatorError` with a single-line `"{ExcType}: {exc}"` message (log the traceback on logger `prismthinker`; never put `traceback.format_exc()` on the graph) and a synthetic `undetermined` result. A hung isolated worker is terminated.
8. Strip unauthorized vetoes.
9. Apply uncited penalties.
10. Drop polarity-mismatched claims (`REASON_POLARITY_MISMATCH`).
11. Compute \(\Delta\) and \(U\). Derive \(\tau_{\text{eff}}\) (§15.2).
12. Maybe probe counterfactuals.
13. Apply disposition lattice using \(\tau_{\text{eff}}\).
14. Build radar, timings (`tau_effective`, `tau_base`), `config_hash`, `run_id` (UUIDv4).
15. Return `DecisionGraph`.

Public API is synchronous. Callers that need async wrap it. No streaming partial graph in v1.1.

---

## 15. Configuration

```python
class ContradictionWeights(BaseModel):
    conclusion: float = 0.35
    constraint: float = 0.25
    evidence: float = 0.15
    assumption: float = 0.15
    premise: float = 0.10

class EngineConfig(BaseModel):
    schema_version: Literal["1.1.0"] = "1.1.0"
    tau_base: float = 0.40
    qualified_tau: float = 0.20
    u_insufficient: float = 0.60
    uncited_penalty: float = 0.50
    contradiction: ContradictionWeights = ContradictionWeights()
    min_heads: int = 3
    stale_hours: float = 168.0
    head_timeout_ms: int = 250
    pool_budget_ms: int = 400
    counterfactual_timeout_ms: int = 200
    max_probes: int = 12
    max_probe_params: int = 4
    n_unresolved_cap: int = 10
    llm: LLMConfig = LLMConfig(enabled=False)
    isolate_heads: bool = True
    dynamic_tau: bool = True
    stop_on_first_resolving: bool = False
```

`config_hash` is SHA-256 of the canonical JSON of this object (sorted keys), including `dynamic_tau`, `isolate_heads`, and `stop_on_first_resolving`. Tests pin “same constructor → same hash,” not a frozen hex.

**Calibration status:** The default contradiction weights, \(\tau\) thresholds (`tau_base`, `qualified_tau`), uncertainty coefficients, and confidence constants are engineering priors for v1.1. They are not claimed to be empirically optimal or statistically calibrated. Production deployments MAY override them through versioned `EngineConfig`. Future benchmark results MAY produce domain-calibrated profiles without changing the `DecisionGraph` contract. Do not delay implementation to search for a universal \(\tau\).

### 15.2 Effective \(\tau\) (implementation amendment, still schema `1.1.0`)

\(\tau_{\text{base}}\) remains an engineering prior. The lattice and counterfactual “resolving” comparisons use \(\tau_{\text{eff}}\).

When `dynamic_tau=False`, \(\tau_{\text{eff}}=\tau_{\text{base}}\) and \(\tau_{\text{qualified,eff}}=\tau_{\text{qualified}}\).

When `dynamic_tau=True` (default), the runtime derives a deterministic \(\tau_{\text{eff}}\) from run-local conditions. The adaptation is versioned with this document, bounded, and included in `config_hash`. It is not learned.

Let \(D\) be the set of determined head verdicts. Let \(\text{polar}\) be true iff both `approve` and `reject` appear in \(D\). Let \(\text{severe}\) be true iff any evidence conflict has `severity ≥ 0.7`. Policy domains are `{legal, security, privacy, healthcare, finance}`.

Additive shifts (applied in this order; `polar` and the regime shift are mutually exclusive):

| Condition | Shift |
|---|---|
| `polar` | \(-0.06\) |
| else closed_formal | \(-0.05\) |
| else empirical | \(0\) |
| else policy_normative | \(-0.03\) |
| else pragmatic_systems | \(+0.03\) |
| else open_dialectic | \(+0.06\) |
| \(\lvert D\rvert \le 2\) | \(-0.04\) |
| \(\lvert D\rvert \ge 4\) and not `polar` | \(+0.03\) |
| `severe` and `polar` | \(-0.03\) |
| \(U \ge 0.35\) | \(-0.03\) |
| `domain` is a policy domain | \(-0.02\) |

\[
\tau_{\text{eff}}=\operatorname{clip}\bigl(\tau_{\text{base}}+\sum \text{shifts},\;0.22,\;0.58\bigr)
\]

\[
\tau_{\text{qualified,eff}}=\operatorname{clip}\bigl(\tau_{\text{qualified}}\cdot\tfrac{\tau_{\text{eff}}}{\tau_{\text{base}}},\;0.08,\;\max(0.08,\;\tau_{\text{eff}}-0.05)\bigr)
\]

An approve-vs-reject split **tightens** \(\tau\) (never widens it to hide a split). Values are recorded on `DecisionGraph.timings_ms` as `tau_effective` and `tau_base`. `dynamic_tau=False` is the A/B control against the raw prior.

### 15.3 Latency

| Path | Budget |
|---|---|
| Fast-path p99 | < 1 ms |
| Evaluator head | 250 ms hard timeout |
| Pool wall clock | 400 ms (parallel) |
| Counterfactuals | +200 ms, skipped if the pool already exhausted a caller-supplied deadline |

If a caller deadline is provided later via API, v1.1 still uses these defaults; a deadline field can be added without changing formulas.

---

## 16. Reason-Code Taxonomy

Closed set in `reason_codes.py`. Heads and engines MUST NOT emit free-string codes.

**Classifier:** `REASON_FAST_PATH`, `REASON_AST_REJECTED`, `REASON_REGIME_MARGIN`, `REASON_REGIME_LOW_SCORE`, `REASON_REGIME_OVERRIDE`, `REASON_NONSTANDARD_MATH`

**Selector:** `REASON_SELECTOR_FILL`, `REASON_SELECTOR_OVERLAY`, `REASON_SELECTOR_INDEPENDENCE`, `REASON_SELECTOR_FORCED`

**Evidence:** `REASON_EVIDENCE_NUMERIC_MISMATCH`, `REASON_EVIDENCE_STALE`, `REASON_EVIDENCE_TRUST`, `REASON_EVIDENCE_NEGATION`

**Evaluator:** `REASON_UNCITED_CLAIM`, `REASON_POLARITY_MISMATCH`, `REASON_UNAUTHORIZED_VETO`, `REASON_MISSING_POLICY_RULES`, `REASON_MISSING_CAUSAL_GRAPH`, `REASON_MISSING_OBJECTIVE`, `REASON_UNBOUND_PATH`, `REASON_UNSTRUCTURED_RULE_IGNORED`, `REASON_DIVISION_BY_ZERO`, `REASON_LLM_INVALID`, `REASON_TIMEOUT`, `REASON_CRASH`

**Contradiction:** `REASON_PAIR_BOTH_UNDETERMINED`, `REASON_PAIR_UNDETERMINED_SKIPPED`, `REASON_INVERTED_EVIDENCE`, `REASON_INVERTED_CONSTRAINT`, `REASON_ASSUMPTION_FLIP`

**Counterfactual:** `REASON_COUNTERFACTUAL_NO_SCHEMA`, `REASON_COUNTERFACTUAL_BUDGET`, `REASON_COUNTERFACTUAL_RESOLVED`

**Lattice:** `REASON_REVIEW_VETO`, `REASON_REVIEW_CONFLICT`, `REASON_REVIEW_UNCERTAINTY`, `REASON_REVIEW_EVIDENCE`, `REASON_REVIEW_POLICY_CAUTION`

`REVIEW_TRIGGERS = {REASON_UNAUTHORIZED_VETO, REASON_LLM_INVALID, REASON_SELECTOR_INDEPENDENCE}`

---

## 17. Epistemic Radar Contract

The frontend renders `DecisionGraph.radar` plus, when needed, `critical_conflicts` and `counterfactuals`.

Required visual mapping:

- Polar axis per selected head: radius = confidence, angle = fixed head order `(formal, policy, empirical, causal, utility)`, color = verdict (`approve` green, `reject` red, `caution` amber, `undetermined` gray).
- Crosshair: x = `uncertainty_score`, y = `contradiction_score`, both \([0,1]\).
- Critical pairs drawn as chords.
- If `review_required`, show `review_reasons` and the first three `counterfactual_hints` (`resolving_condition` of resolving probes, else top \(\Delta\) drops).

No extra backend payload is required for v1.1 UI.

---

## 18. Experimental Latent Track

`experimental/latent` remains in the tree for research (activation projections / steering). v1.1 defines **no** runtime bridge from `DecisionGraph` to steering vectors. Production packaging SHOULD exclude this extra from the default install extra (`pip install prismthinker` without `[latent]`).

A future spec may attach contradiction components to subspace clamps. That work is out of scope until it has its own contract.

---

## 19. Testing Requirements

These tests are part of the spec, not optional polish.

| Test | Must prove |
|---|---|
| `test_invariants.py` | `ReasoningContext` field names contain none of `{user, persona, history, preference}`; `evaluate` rejects `PresentationContext` |
| `test_invariants.py` | Conflict case: policy reject + utility approve → `recommended_verdict is None`, both results intact |
| `test_invariants.py` | Utility or formal `hard_veto=True` is stripped; only `policy` veto is authorized |
| `test_invariants.py` | Adding or removing `policy_rules` does not change `formal` verdict when facts, specs, constraints, and hypothesis are fixed |
| `test_invariants.py` | Fast-path axiomatic claim cites `CitationKind.HYPOTHESIS` |
| `test_ast_safe.py` | `2+2` / `(12*8)/4` fast-path; `os.system`, `__import__`, `mod`, `"2+2 and delete PII"` not fast-path |
| `test_classifier.py` | Policy lexemes + rules → `POLICY_NORMATIVE`; mixed families → `OPEN_DIALECTIC`; `force_regime` honored |
| `test_evaluators.py` | Each head: happy path, missing input → `undetermined`, no mutation of context |
| `test_evidence.py` | Numeric mismatch + explicit negation recorded before heads |
| `test_contradiction.py` | approve vs reject → \(C_{\text{conclusion}}=1\); inverted constraint → \(C_{\text{constraint}}=1\); weights sum check |
| `test_uncertainty.py` | \(U\le 1\) with 40 unresolved questions; empty-evidence rule-only context does not inflate coverage term |
| `test_disposition.py` | Table in §13, including majority tie → `CONFLICT` |
| `test_counterfactual.py` | Only mutable specs probed; original facts unchanged; `delta_after` from re-eval; budget cap |
| `test_adapters.py` | `HARD_VETO` → `REFUSE` + empty tools; review promotion of `EXECUTE` → `ESCALATE` |
| `test_end_to_end.py` | Worked example in §20 |

Property: for any two graphs with identical `config_hash` and canonical context, non-LLM paths are byte-stable on `disposition`, `recommended_verdict`, \(\Delta\), \(U\), and verdicts.

---

## 20. Worked Example

**Query:** “Reduce `cache_ttl` stay at 60s for checkout.”  
**Hypothesis:** approve action `keep_cache_ttl` with payload `{cache_ttl: 60}`.

**Facts:** `cache_ttl=60` (mutable, int, 1..300, step 10), `p99_latency_ms=180` (immutable), `contains_pii=true`.

**Rules:** prohibition `fact.contains_pii == true and fact.cache_ttl >= 30` severity `hard_veto` (PII cache retention).

**Objective:** minimize `p99_latency_ms`, `caution_below=0.5`, `reject_below=0.2`.

Expected (non-LLM) outline:

1. Stage A fails (prose). Stage B → `POLICY_NORMATIVE` or `OPEN_DIALECTIC` depending on scores; overlay `privacy` forces `policy`. Min heads 3 → `policy`, `formal`, `utility` (and fill `empirical` if needed).
2. `policy`: prohibition matches → `reject`, authorized veto.
3. `formal`: facts type-check and no `ConstraintSpec` is violated → `approve`. It does **not** read the PII `PolicyRule` and does **not** veto.
4. `utility`: low latency at ttl=60 → `approve`.
5. \(\Delta(\text{policy},\text{formal})\) and \(\Delta(\text{policy},\text{utility})\) are high via \(C_{\text{conclusion}}=1\). That disagreement is real: structurally valid and useful, but not permitted.
6. Lattice rule 1 → `HARD_VETO`, `recommended_verdict=REJECT`, formal and utility approvals **retained** on the graph.
7. Counterfactual: `cache_ttl=20` (and `10`) re-run; prohibition false; \(\Delta\) drops; probe marked resolving.
8. Egress: `REFUSE`, `allowed_tools=[]`, radar + resolving hint for HITL: “If `cache_ttl` decreases from 60 to 20, policy veto clears.”

This is the behavior v1.0 described in prose and v1.1 makes executable.

---

## 21. Implementation Notes (non-normative)

- Prefer `pydantic>=2` and Python 3.11+.
- Predicate parser: recursive descent or restricted `ast.parse` visitor only. Same whitelist philosophy as the math walker. No `eval`, no regex grammar.
- Parallelism: preferred production execution is isolated worker processes for standard heads (`isolate_heads=True`). `ThreadPoolExecutor` remains supported when `isolate_heads=False` and for custom evaluators that cannot be isolated. Both modes deep-copy / serialize context per head. Shared context is read-only; no per-thread writes onto the context object.
- Do not implement LLM heads to “finish” v1.1. The optional contract exists so they cannot appear later as veto oracles.
- Do not implement activation steering to satisfy directory layout completeness.
- Do not open a v1.2 architecture pass until implementation or benchmarks falsify this document.

---

## 22. What v1.1 still postpones (explicitly)

These are not gaps in the coprocessor contract. They are later products:

- Multi-hypothesis ranking in one call (v1.1 is one hypothesis per `evaluate`).
- General SMT / theorem proving beyond the predicate grammar.
- Learned \(\Delta\) weights.
- Streaming partial graphs.
- A runtime bridge from contradiction components to latent steering.
- Natural-language policy compilation. Policies enter as `PolicyRule` objects; an upstream compiler may exist outside this package.

If a later version adds any of these, it bumps `schema_version` and this document. v1.1 is frozen. More theoretical redesign before a living implementation is out of scope.
