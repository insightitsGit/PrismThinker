# PrismThinker

[![PyPI version](https://img.shields.io/pypi/v/prismthinker.svg?color=blue)](https://pypi.org/project/prismthinker/)
[![Python Versions](https://img.shields.io/pypi/pyversions/prismthinker.svg)](https://pypi.org/project/prismthinker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/insightitsGit/PrismThinker/actions/workflows/ci.yml/badge.svg)](https://github.com/insightitsGit/PrismThinker/actions/workflows/ci.yml)

**Deterministic pre-execution firewall and epistemic decision gate for autonomous AI agents.**

PrismThinker is **AI agent guardrails** at the **tool-call firewall**, not a chat filter. It sits immediately before the execution boundary (API mutations, tool calls, SQL writes). Independent heads (policy, formal, empirical, causal, utility) score one typed action. Genuine contradiction is kept, not averaged. An authorized policy veto returns `tools: []`. When a call is blocked, budgeted counterfactuals say which **mutable fact** would clear it.

That is how you **prevent agent hallucination tool calling**: the model may still propose `disburse_refund($4200)`. The coprocessor decides whether the host is allowed to run it. No LLM is on the `evaluate()` path — these are **deterministic LLM guardrails** in the sense that the *gate* does not sample.

```text
ReasoningContext  →  PrismThinker.evaluate  →  DecisionGraph  →  to_chorusgraph()  →  EXECUTE | REFUSE | ESCALATE | GATHER
```

Current routing: [v1.2 eligibility gate and migration](docs/eligibility-v1.2.md), schema `1.2.0`. The [frozen v1.1 specification](docs/architecture-specification-v1.1.md) remains historical. Changes: [`CHANGELOG.md`](CHANGELOG.md).

---

## Why PrismThinker?

Most agent pilots stall because **enterprises cannot trust agents to execute**. Given *"maximize refund velocity"* and *"never disburse more than $2,500 without a supervisor"*, a single self-attention pass will often **average the conflict into a compromise**. In production that compromise is a policy violation.

Text classifiers and LLM-as-a-judge do not close that **execution-containment** gap:

- **Pre-execution, not post-generation.** Operates on a typed `Hypothesis` + `CandidateAction`, not on the assistant's prose after the fact.
- **Never averages disagreement.** If policy forbids and utility wants it, both verdicts stay on the graph. Authorized `HARD_VETO` locks tool calls (`tools: []`) every time.
- **Recovery is a probed fact, not a 403 string.** Counterfactuals permute **mutable typed facts** and report which change lifts the veto. They do not rewrite `action.payload` for you.
- **No GPU / no model on the default path.** Runtime dependency is `pydantic` only. Local bench eval p50 is **1.6 ms**. Production default `isolate_heads=True` adds process-spawn cost (measured mean **~494 ms** vs **~2.3 ms** in thread mode). Fast-path arithmetic is the sub-millisecond case.

It does **not** import [VectorPrism](https://github.com/insightitsGit/VectorPrism) or [ChorusGraph](https://github.com/insightitsGit/ChorusGraph). Both companion repos are public. Joins are adapters only: `from_vectorprism()` in, `to_chorusgraph()` out. `evaluate()` still runs on a hand-built `ReasoningContext`.

---

## How it compares

| | Text guardrails (NeMo Guardrails, Guardrails AI) | Static policy (OPA, Cedar) | PrismThinker |
|---|---|---|---|
| **Focus** | Post-generation text / toxicity / topical rails | Boolean allow / deny on attributes | Pre-execution multi-method logic on one hypothesis |
| **Conflict** | Often an extra LLM judge (consensus can be hallucinated) | Single allow/deny; no second method | Closed-form \(\Delta_{ij}\); heads are not blended |
| **Uncertainty** | Folded into one confidence | Not a first-class score | Saturated \(U \in [0,1]\), independent of \(\Delta\) |
| **Recovery** | None, or a static message | Error string | Budgeted counterfactual probes on mutable facts |
| **Latency** | An extra model call | Microseconds–milliseconds | **No model** on `evaluate()`; 1.6 ms p50 local bench |

NeMo / Guardrails AI are the right tool for *what the model is allowed to say*. OPA / Cedar are the right tool for *attribute RBAC*. Neither measures whether **independent methods agree** on the same proposed tool call, and neither emits a nullable `recommended_verdict` when they do not.

---

## Installation

```bash
pip install prismthinker
```

Python **3.11+**. PyPI: [prismthinker 1.1.0](https://pypi.org/project/prismthinker/1.1.0/).

```bash
pip install -e ".[dev]"      # pytest, coverage, build
pip install "prismthinker[bench]"
pip install "prismthinker[latent]"   # torch; never required for evaluate()
```

---

## Quickstart: guard a tool call

Bind the prohibition to a **mutable typed fact**. Recovery probes `structured_facts`, not `action.payload`.

```python
from prismthinker import (
    ActionKind,
    CandidateAction,
    DeonticModality,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    PolicyRule,
    PrismThinker,
    ReasoningContext,
    ReasoningDisposition,
    RuleSeverity,
)
from prismthinker.adapters.chorusgraph import to_chorusgraph

context = ReasoningContext(
    query="Process emergency customer refund exception",
    hypothesis=Hypothesis(
        id="hyp_tx_901",
        statement="Disburse unverified refund payment",
        action=CandidateAction(
            id="act_01",
            kind=ActionKind.TOOL_INVOCATION,
            name="disburse_refund",
            payload={"amount": 4200, "user_tier": "standard"},
        ),
    ),
    structured_facts={
        "amount": FactValue(key="amount", value=4200),
        "user_tier": FactValue(key="user_tier", value="standard"),
    },
    fact_specs={
        "amount": FactSpec(
            key="amount",
            fact_type=FactType.INT,
            mutable=True,
            minimum=0,
            maximum=10000,
            step=500,
        )
    },
    policy_rules=[
        PolicyRule(
            id="rule_refund_cap",
            modality=DeonticModality.PROHIBITION,
            predicate="fact.amount > 2500 and fact.user_tier == standard",
            severity=RuleSeverity.HARD_VETO,
            text="Standard tier refunds cannot exceed $2,500 without manager signature.",
        )
    ],
)

graph = PrismThinker().evaluate(context)
envelope = to_chorusgraph(graph, allowed_tools=["disburse_refund"])

if graph.disposition is ReasoningDisposition.HARD_VETO:
    print("BLOCKED", graph.recommended_rationale)  # lattice.hard_veto
    print(envelope.directive, envelope.allowed_tools)  # refuse []
    for cf in graph.counterfactuals:
        if cf.resolving:
            print("RECOVERY", cf.resolving_condition)
            # amount 4200 → 2200 lifts the veto
else:
    run_tool(context.hypothesis.action)
```

Measured on this snippet: policy `REJECT` + `hard_veto`, formal still `APPROVE`, \(\Delta = 0.42\), directive `REFUSE`, tools `[]`. `PresentationContext` (user, persona, history) is rejected. Preference isolation is an invariant.

LangChain / LlamaIndex / generic RAG:

```python
from prismthinker.adapters.documents import from_langchain, from_documents
from prismthinker.adapters.rag import allow_generation

ctx = from_langchain(query, lc_docs, extra=seed_with_hypothesis_and_rules)
graph = PrismThinker().evaluate(ctx)
if not allow_generation(graph):
    raise PermissionError(graph.recommended_rationale)
```

---

## Core architecture

```text
[ Candidate action / Hypothesis ]
               │
               ▼
1. Epistemic regime classifier     fast-path arithmetic (AST whitelist) or dialectic
               │
               ▼
2. Dynamic evaluator selection     policy, formal, empirical, causal, utility
               │
               ▼
3. Independent head evaluation     typed claims; no shared decision procedure
               │
               ▼
4. Contradiction + uncertainty     closed-form Δ_ij ; saturated U ∈ [0, 1]
               │
               ▼
5. Counterfactual probes           mutable FactSpec values only
               │
               ▼
6. Priority disposition lattice    DecisionGraph + ChorusGraphDirective
```

### Contradiction \(\Delta_{ij}\)

$$
\Delta_{ij} = w_c C_{\text{conclusion}} + w_k C_{\text{constraint}} + w_e C_{\text{evidence}} + w_a C_{\text{assumption}} + w_p C_{\text{premise}}
$$

Default \(\tau_{\text{base}} = 0.40\). If \(\Delta_{\max} > \tau_{\text{eff}}\), the lattice is `CONFLICT` (nullable verdict) unless an authorized policy veto already won. Weights are engineering priors, **not a calibrated fit**.

### Disposition lattice (first match wins)

The following lattice describes evaluator agreement. The [eligibility gate](docs/eligibility-v1.2.md) takes precedence when producing the operational directive: a proven BLOCK refuses even when the lattice reports CONFLICT.

1. Authorized policy veto → `HARD_VETO` / `REJECT`
2. Fewer than 2 determined heads **or** \(U \ge u_{\text{insufficient}}\) → `INSUFFICIENT_EVIDENCE` / `null`
3. \(\Delta_{\max} > \tau_{\text{eff}}\) → `CONFLICT` / `null`
4. Majority + dissent / caution / qualified \(\Delta\) → `QUALIFIED_CONSENSUS`
5. Unanimous determined + low \(\Delta\) → `CONSENSUS`
6. Majority tie → `CONFLICT` / `null`

Fallback mapping when the eligibility gate has no directive:

| Graph | Directive | Tools |
|---|---|---|
| `HARD_VETO` | `REFUSE` | `[]` |
| `CONFLICT` | `ESCALATE` | `[]` |
| `INSUFFICIENT_EVIDENCE` | `GATHER` | `[]` |
| Consensus / qualified + tool + `APPROVE` | `EXECUTE` | caller allowlist |
| Consensus / qualified + assertion + `APPROVE` | `ANSWER` | `[]` |
| Consensus / qualified + `REJECT` | `REFUSE` | `[]` |

Only `EXECUTE` may keep tools. That is the firewall.

---

## RAG and orchestrators

Framework-agnostic. Compatible with LangChain, LangGraph, CrewAI, or any runtime that honors `ChorusGraphEnvelope`. There is no MCP or AutoGen adapter in v1.1 — pass a `ReasoningContext` in and honor the envelope out.

- **Retriever-agnostic:** `EvidenceItem` / `from_documents` / `from_langchain` / `from_llamaindex`, or [VectorPrism](https://github.com/insightitsGit/VectorPrism) via `from_vectorprism()`.
- **Orchestrator-agnostic:** [ChorusGraph](https://github.com/insightitsGit/ChorusGraph) via `to_chorusgraph()`, or LangGraph / CrewAI / a custom host.

Unix rule: VectorPrism finds evidence. PrismThinker tests the logic. ChorusGraph (or your orchestrator) runs tools **only** if the envelope says `EXECUTE`.

---

## Benchmark: Oresteia justice (`python -m bench.justice`)

Public-domain myth, not a copyrighted screenplay. Retrieval is allowed to surface both blood-price and the court. The lattice must not average that into “maybe kill him.”

| Case | Lattice | \(\Delta\) | Tools |
|---|---|---|---|
| Extra-judicial killing | `HARD_VETO` | 0.43 | `[]` |
| Furies' street execution | `HARD_VETO` | 0.43 | `[]` |
| Athena's civic court | `CONSENSUS` | 0.10 | `EXECUTE open_court` |
| What should happen to him? | `QUALIFIED_CONSENSUS` | 0.16 | `ANSWER`, tools `[]` |

Local 28-scenario bench (2026-09-07): labeled **1.000**, contract **1.000**. `EXECUTE` once among 28 is the point: disagreeing scrapes should hesitate.

---

## Validation status

The reproducible [validation harness](validation/README.md) covers agent execution, policy/compliance and evidence-intensive reasoning. On its 12-case synthetic validation split (`local-v0.1.1`, seed 42):

- **0 unsafe autonomous actions**, **50% autonomous coverage**
- **100% selective verdict accuracy** and **100% directive accuracy**
- **1.00 conflict F1**, **0 runtime failures**
- Exact verdict agreement **50%**: six mismatches still produced the correct `ESCALATE`

These are synthetic fixtures with scripted mock baselines, not evidence of superiority over live language models. Protocol for the next live-model experiment: [`validation/protocol-v0.2.md`](validation/protocol-v0.2.md).

**Calibration is not claimed.** \(\tau_{\text{base}}=0.40\), `qualified_tau=0.20`, `u_insufficient=0.60` are engineering priors.

---

## Tests

Saved scientific validation reports:

- [Fresh v1.2 full comparison](validation/reports/local-v1.2-fresh-001/FINDINGS.md): 180 new frozen cases and 1,080 model calls. PrismThinker made 6/93 unsafe executions versus majority vote's 28/93 at equal 48.3% coverage; the gate-only baseline made 21/93 at 56.7% coverage. Remaining causal failures, Delta limitations and a conflict-reporting audit are documented. Assistant-authored synthetic data, not independent expert validation.
- [Local multi-model findings: 180 cases](validation/reports/local-v0.2-L-002/INTERPRETATION.md), [full measurements and plots](validation/reports/local-v0.2-L-002/summary.md), and [reproduction protocol](validation/LOCAL_SCIENCE.md). The corrected repeat observed 0/101 unsafe executions at 43.9% coverage, but 53.3% directive accuracy and zero conflict F1. It is a post-audit repeat on authored synthetic cases, not an independent held-out benchmark.
- [Original local-run input audit](validation/reports/local-v0.2-L-001/AUDIT.md), with the compromised run's raw results preserved.
- [v0.1.1 scripted-baseline report](validation/reports/generated/20260907T081332Z-7535746d/summary.md) and [latency report](validation/reports/generated/latency-20260907T081123Z-9c6f716a/summary.md).

```bash
pytest
```

CI (`.github/workflows/ci.yml`) runs pytest on 3.11 and 3.12, then `python -m build` + `twine check`. Isolation and predicate coverage must stay ≥ 90% (`core/isolation.py`, `core/predicates.py` are at 100% locally). The refund snippet above is pinned in `tests/test_readme_quickstart.py`.

---

## What v1.1 is not

- Not an LLM product. No NL→policy. `EngineConfig.llm.enabled=True` fail-closes.
- Not SMT. Formal is typed facts + a recursive-descent predicate parser.
- Not a retriever and not an orchestrator. `evaluate()` does not import `adapters/`.
- Not numpy/scipy. Invariants forbid those imports on the core path.

---

## License / community

**Author:** Amin Parva ([Insight IT Solutions LLC](https://www.insightits.com))  
**Contact:** [GitHub Issues](https://github.com/insightitsGit/PrismThinker/issues)  
**License:** MIT (`LICENSE`)  
**Source:** [github.com/insightitsGit/PrismThinker](https://github.com/insightitsGit/PrismThinker)  
**PyPI:** [pypi.org/project/prismthinker/](https://pypi.org/project/prismthinker/)
