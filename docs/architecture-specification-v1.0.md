# Architecture Specification: `prismthinker` v1.0

> **Superseded by [v1.1 FROZEN](./architecture-specification-v1.1.md).**  
> Keep this file as the historical snapshot. Implement against v1.1.

**Package:** `prismthinker`

**System Role:** Model-agnostic, disagreement-aware epistemic reasoning coprocessor.

**Core Purpose:** Evaluates identical evidence and candidate actions across multiple independent reasoning lenses, isolates structural disagreements into an explainable contradiction matrix, extracts conflicting assumptions, and identifies counterfactual resolution paths without forcing artificial consensus.

---

## 1. System Context & Component Topology

`prismthinker` operates between retrieval systems (e.g., `vectorprism`) and workflow orchestrators (e.g., `chorusgraph`), providing deterministic evaluation before tokens are generated or tools are executed.

```
                           [ User Query + Raw Evidence ]
                                         │
                                         ▼
                     ┌───────────────────────────────────────┐
                     │     Epistemic Regime Classifier       │
                     └───────────────────┬───────────────────┘
                                         │
                         Is Closed Axiomatic / Fast-Path?
                                         │
                     ┌───────────────────┴───────────────────┐
                     ▼ (YES)                                 ▼ (NO)
        ┌─────────────────────────┐             ┌────────────────────────┐
        │  Axiomatic Fast-Path    │             │   Dynamic Selector     │
        │   (AST Safe Evaluator)  │             │ (Picks relevant heads) │
        └────────────┬────────────┘             └───────────┬────────────┘
                     │                                      ▼
                     │                          ┌────────────────────────┐
                     │                          │  Evaluator Pool (N)    │
                     │                          │  Consumes Context,     │
                     │                          │  Emits Claims & Assump.│
                     │                          └───────────┬────────────┘
                     │                                      ▼
                     │                          ┌────────────────────────┐
                     │                          │ Multi-Component Engine │
                     │                          │ (Δ_ij Matrix + Reason) │
                     │                          └───────────┬────────────┘
                     │                                      ▼
                     │                          ┌────────────────────────┐
                     │                          │ Counterfactual Engine  │
                     │                          │ ("What fact resolves?")│
                     │                          └───────────┬────────────┘
                     │                                      ▼
                     │                          ┌────────────────────────┐
                     │                          │ Decision Graph Output  │
                     │                          │ (Disposition + Radar)  │
                     │                          └───────────┬────────────┘
                     └──────────────────────────────────────┼─────────────────┐
                                                            ▼                 ▼
                                                    [ Final Verdict ]  [ HITL Radar ]

```

---

## 2. Directory Layout

```text
prismthinker/
├── pyproject.toml
├── README.md
├── src/
│   └── prismthinker/
│       ├── __init__.py
│       ├── classifier.py            # AST-safe math resolver & regime router
│       ├── core/
│       │   ├── __init__.py
│       │   ├── schemas.py           # Core Pydantic contracts & DecisionGraph
│       │   ├── selector.py          # Dynamic evaluator registry & selector
│       │   ├── contradiction.py     # Multi-component explainable Δ_ij engine
│       │   ├── counterfactual.py    # Parameter perturbation & resolution prober
│       │   └── engine.py            # Main PrismThinker orchestration entrypoint
│       ├── evaluators/
│       │   ├── __init__.py
│       │   ├── base.py              # Base evaluator abstract contract
│       │   ├── formal.py            # Symbolic deduction & invariant verifier
│       │   ├── empirical.py         # Statistical posterior & distribution verifier
│       │   ├── causal.py            # Directed graph reachability & do-calculus
│       │   ├── policy.py            # Regulatory, deontological & hard boundary gates
│       │   └── utility.py           # Objective function, SLA & efficiency scorer
│       └── experimental/
│           └── latent/
│               ├── __init__.py
│               ├── projections.py   # Orthogonal multi-subspace projector
│               └── steering.py      # In-flight activation cancellation / clamp
└── tests/
    ├── conftest.py
    ├── test_classifier.py
    ├── test_evaluators.py
    ├── test_contradiction.py
    ├── test_counterfactual.py
    └── test_end_to_end.py
```

---

## 3. Data Contracts (`core/schemas.py`)

```python
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class EpistemicRegime(str, Enum):
    CLOSED_FORMAL = "closed_formal"          # Arithmetic, pure math, logic syntax
    EMPIRICAL = "empirical"                  # Inductive distributions, telemetry, observations
    POLICY_NORMATIVE = "policy_normative"    # Security, ethics, hard regulations, legal
    PRAGMATIC_SYSTEMS = "pragmatic_systems"  # Architecture, performance, SLAs, costs
    OPEN_DIALECTIC = "open_dialectic"        # Complex multi-method domain problems

class ReasoningDisposition(str, Enum):
    CONSENSUS = "consensus"
    QUALIFIED_CONSENSUS = "qualified_consensus"
    CONFLICT = "conflict"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    HARD_VETO = "hard_veto"
    HUMAN_REVIEW = "human_review"

class EvidenceItem(BaseModel):
    id: str
    content: str
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Claim(BaseModel):
    id: str
    evaluator: str
    statement: str
    polarity: float = Field(ge=-1.0, le=1.0)  # -1.0 = Reject/Veto, +1.0 = Affirm
    confidence: float = Field(ge=0.0, le=1.0)
    cited_evidence_ids: List[str] = Field(default_factory=list)

class ReasoningContext(BaseModel):
    query: str
    evidence: List[EvidenceItem] = Field(default_factory=list)
    structured_facts: Dict[str, Any] = Field(default_factory=dict)
    candidate_action: Optional[Dict[str, Any]] = None
    rules: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    domain: Optional[str] = None

class EvaluatorResult(BaseModel):
    evaluator: str
    conclusion: str  # "approve", "reject", "caution", "undetermined"
    confidence: float = Field(ge=0.0, le=1.0)
    claims: List[Claim] = Field(default_factory=list)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    unresolved_questions: List[str] = Field(default_factory=list)
    hard_veto: bool = False
    reason_codes: List[str] = Field(default_factory=list)

class ConflictComponent(BaseModel):
    conclusion_conflict: float = 0.0
    evidence_conflict: float = 0.0
    premise_conflict: float = 0.0
    constraint_conflict: float = 0.0
    assumption_conflict: float = 0.0

class PairwiseDisagreement(BaseModel):
    pair: List[str]  # [Evaluator A, Evaluator B]
    delta: float
    components: ConflictComponent
    reason_codes: List[str]

class CounterfactualProbe(BaseModel):
    parameter_changed: str
    delta_before: float
    predicted_delta_after: float
    resolving_condition: str

class DecisionGraph(BaseModel):
    query: str
    recommended_conclusion: str
    disposition: ReasoningDisposition
    confidence: float
    contradiction_score: float  # Orthogonal axis 1: Disagreement across evaluators
    uncertainty_score: float    # Orthogonal axis 2: Missing evidence / ambiguity
    evaluators: Dict[str, EvaluatorResult]
    critical_conflicts: List[PairwiseDisagreement] = Field(default_factory=list)
    shared_assumptions: List[str] = Field(default_factory=list)
    conflicting_assumptions: List[str] = Field(default_factory=list)
    counterfactuals: List[CounterfactualProbe] = Field(default_factory=list)
    requires_human_review: bool
```

---

## 4. Pipeline Execution Logic

### Phase 1: Regime Classification & Axiomatic Fast-Path

* Scans query using an AST visitor pattern (`ast.NodeVisitor`).
* Pure closed-form arithmetic and simple algebraic identities (`2 + 2`, `(12 * 8) / 4`) evaluate deterministically in $<1\text{ ms}$, bypassing the evaluator pool entirely.
* Non-standard mathematical foundations (e.g., `mod 3`, `quaternion`) bypass the fast-path and route into `OPEN_DIALECTIC`.

### Phase 2: Dynamic Evaluator Selection

Instead of instantiating all evaluators blindly, the active regime and domain filter the necessary evaluators:

* **`POLICY_NORMATIVE`**: `policy` + `formal` + `utility`
* **`PRAGMATIC_SYSTEMS`**: `utility` + `causal` + `empirical`
* **`EMPIRICAL`**: `empirical` + `causal`
* **`OPEN_DIALECTIC`**: All evaluators active

### Phase 3: Independent Evaluation & Claim Generation

Each evaluator receives the unmodified `ReasoningContext` and emits:

1. `claims`: Atomic factual assertions tied to specific `EvidenceItem.id` citations.
2. `assumptions`: Environmental conditions assumed true to validate the claim (e.g., *"Network partition does not exceed 500ms"*).
3. `confidence`: Scored against empirical variance, formal proof satisfiability, or distance from indifference.

### Phase 4: Multi-Component Contradiction Measurement ($\Delta_{ij}$)

Contradiction between Evaluator $A$ and Evaluator $B$ is measured across discrete, inspectable dimensions:


$$\Delta_{ij} = w_1 C_{\text{conclusion}} + w_2 C_{\text{constraint}} + w_3 C_{\text{evidence}} + w_4 C_{\text{assumption}} + w_5 C_{\text{premise}}$$

* $w = [0.35, 0.25, 0.15, 0.15, 0.10]$
* **Dynamic Gate:** $\tau_{\text{base}} = 0.40$. If $\Delta_{\max} > 0.40$, the system enters `CONFLICT` or `HARD_VETO`.
* **Independent Uncertainty:** Computed separately as $U = (1 - \bar{c}) + 0.1 \cdot N_{\text{unresolved}}$, preventing confusion between genuine disagreement and lack of data.

### Phase 5: Counterfactual Sensitivity Probing

When $\Delta_{\max} > 0.40$, the engine runs counterfactual permutations over the structured fact parameters:

* Mutates values in `context.structured_facts`.
* Re-evaluates active evaluators on mutated contexts.
* Identifies boundary transitions: *"If `cache_ttl` decreases from `60s` to `10s`, Policy approval switches to True and $\Delta$ drops from 0.82 to 0.08."*

### Phase 6: Output Assembly & Arbitration

Emits the comprehensive `DecisionGraph`. If `requires_human_review = True`, the payload exports the full state needed to render the interactive **Epistemic Radar** frontend.

---

## 5. Architectural Invariants

1. **Preference Isolation:** User history and persona weights MUST NEVER be ingested inside the evaluator pool or contradiction engine. Personalization is applied downstream at presentation time only.
2. **Deterministic Reproducibility:** Every `Claim` must trace to an `evidence_id`, a rule string, or a structured fact key. Uncited assertions receive a confidence penalty.
3. **Paraconsistent Preservation:** The engine never averages conflicting claims into a compromised middle ground. If Policy rejects and Utility approves, both states remain fully represented in the `DecisionGraph`.
