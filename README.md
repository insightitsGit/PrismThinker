# PrismThinker

**Model-agnostic, disagreement-aware epistemic reasoning coprocessor.**

Standalone library. One job:

```text
ReasoningContext  →  PrismThinker.evaluate  →  DecisionGraph
```

It scores one typed hypothesis across independent heads, **keeps conflict instead of averaging it**, and emits a graph any orchestrator can honor **before** tokens are generated or tools run.

It does **not** import [VectorPrism](https://github.com/insightitsGit/VectorPrism) or [ChorusGraph](https://github.com/insightitsGit/ChorusGraph). In the **macro application stack** they compose; at the **package boundary** they stay decoupled. Joins are typed adapters only: `from_vectorprism()` in, `to_chorusgraph()` out. `evaluate()` still runs on a hand-built JSON `ReasoningContext` with no retriever and no orchestrator.

Implementation contract: [`docs/architecture-specification-v1.1.md`](docs/architecture-specification-v1.1.md) — **v1.1 FROZEN**, schema `1.1.0`.

```text
[ User request / autonomous task ]
        │
        ▼
1. ChorusGraph          orchestration & candidate tool calls
        │ needs evidence
        ▼
2. VectorPrism          rhetorical/causal chunks, PSM 1024d, reject funny neighbors
        │ from_vectorprism()     ← package join, not a core import
        ▼
3. PrismThinker         typed ReasoningContext → Δ, U, lattice → DecisionGraph
        │ to_chorusgraph()       ← package join, not a core import
        ▼
4. ChorusGraph          EXECUTE runs the allowlist; REFUSE / ESCALATE / GATHER → tools []
```

VectorPrism finds high-signal evidence. PrismThinker tests the logic. ChorusGraph runs the workflow — and only if the envelope says `EXECUTE`.

**Python 3.11+** · **pydantic 2** · no LLM required on the v1.1 path · no ANN / vector-DB client on the evaluate path · no PyTorch on the default install

**Author:** Amin Parva

---

## Critical: PrismThinker is the measurement layer — not a chat model

| Layer | Product | Owns | Must not own |
|---|---|---|---|
| Orchestration | **ChorusGraph** (or LangGraph / CrewAI / …) | workflow, candidate tools, honor/refuse | averaging head verdicts |
| Sensory retrieve | **VectorPrism** (or Pinecone / Qdrant / SQL / fixture) | chunk, encode, ANN | lattice, veto, tools |
| Verification | **PrismThinker** | typed hypothesis, heads, \(\Delta\), \(U\), `DecisionGraph` | search index, tool runtime |

Unix rule: each product does one thing, talks through typed contracts, and never assumes the others are present.

**Supported**

```text
facts + rules + hypothesis + optional evidence
        → PrismThinker.evaluate(ReasoningContext)
        → DecisionGraph
```

Optional helpers (not used by `engine.py`): `from_vectorprism` (VectorPrism join), `to_chorusgraph` (ChorusGraph join), `from_documents`, `from_langchain`, `from_llamaindex`. You can swap either neighbor without touching `core/`.

**Not supported (will look like “PrismThinker didn’t help”)**

```text
untyped chat history + persona weights  →  PrismThinker.evaluate(...)
free-text “just decide” with no Hypothesis / facts / rules
averaging head verdicts into a compromise score
calling evaluate() and expecting it to retrieve or run tools
```

`PresentationContext` (user, persona, history) is a downstream object. `evaluate()` **rejects** it. Preference isolation is an invariant, not a style choice.

---

## Two modes of operation

### Mode 1 — Sovereign Prism stack

[VectorPrism](https://github.com/insightitsGit/VectorPrism) + PrismThinker + [ChorusGraph](https://github.com/insightitsGit/ChorusGraph). VectorPrism cuts and indexes; `from_vectorprism()` types the evidence; PrismThinker measures \(\Delta\) and \(U\); `to_chorusgraph()` is the only path that may keep a tool allowlist (`EXECUTE`). Packages stay decoupled.

### Mode 2 — Universal RAG plug-in

Keep Pinecone, Weaviate, Qdrant, Chroma, pgvector, LangChain, or LlamaIndex. PrismThinker does not care how the text was retrieved. It is an **intermediate verification gate** between top-k chunks and the LLM (or tool call):

```text
[ User query ]
      │
      ▼
[ Any retriever — cosine / hybrid / SQL ]
      │  top-k documents
      ▼
ReasoningContext assembly   map docs → EvidenceItem; type Hypothesis + PolicyRule
      │
      ▼
PrismThinker.evaluate       evidence conflict, heads, Δ, U, lattice
      │
      ├─ CONSENSUS / QUALIFIED_CONSENSUS → allow_generation: pass citations to the LLM
      ├─ INSUFFICIENT_EVIDENCE           → GATHER: ask, do not invent
      └─ CONFLICT / HARD_VETO            → halt; do not generate; surface the radar
```

The retriever still dumps chunks. The caller still owns the prompt. PrismThinker decides whether those chunks are safe to synthesize.

```python
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
from prismthinker.adapters.rag import allow_generation

# 1. Standard RAG retrieval from any vector store
# retrieved_docs = vector_store.similarity_search(query, k=4)

evidence = [
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
    hypothesis=Hypothesis(
        id="hyp_1",
        statement="Approve automated refund for disputed transaction.",
        action=CandidateAction(
            id="act_refund",
            kind=ActionKind.TOOL_INVOCATION,
            name="issue_refund",
            payload={"amount": 750},
        ),
    ),
    evidence=evidence,
    policy_rules=[
        PolicyRule(
            id="rule_refund_cap",
            modality="prohibition",
            predicate="action.payload.amount > 500",
            severity=RuleSeverity.HARD_VETO,
            text="Automated refunds cannot exceed $500.",
        )
    ],
)

graph = PrismThinker().evaluate(context)

if graph.disposition is ReasoningDisposition.HARD_VETO or not allow_generation(graph):
    # Halt before the LLM hallucinates an approval
    raise PermissionError(graph.recommended_rationale)

# Safe to feed verified evidence into the prompt
response = llm.generate(prompt=query, context=graph)
```

The caller types the `Hypothesis` (including `action.payload` the policy can bind). Retrieval rank is not authority: prefer `metadata.trust`; clipped `score` is a topical fallback. LangChain / LlamaIndex objects can skip the manual loop:

```python
from prismthinker.adapters.documents import from_langchain, from_llamaindex, from_documents

ctx = from_langchain(query, lc_docs, extra=seed_with_hypothesis_and_rules)
```

---

## Why PrismThinker exists

Retrieval returns neighbors. Orchestration wants a tool call. Neither measures **whether independent methods agree** on the same proposition.

Enterprise stacks get stuck in two bad defaults:

1. **One model, one answer** — a single LLM or a blended score hides the fact that policy said *no* and utility said *yes*.
2. **Committee of prompts** — five system prompts are not five methods. They share a generator and are not methodologically independent.

PrismThinker makes disagreement **typed, explainable, and actionable**:

- One `Hypothesis` every head scores — typed by the **caller** (the agent proposing the action), never by the retriever
- Five default heads with distinct `independence_class` values
- Closed-form contradiction \(\Delta_{ij}\) (not vibes)
- Disposition lattice with a **nullable** `recommended_verdict`
- Egress directive the orchestrator must not “soft ignore”

You keep Pinecone / Qdrant / Milvus. You keep LangGraph / CrewAI / Semantic Kernel. PrismThinker is the drop-in auditor, not a full-stack migration.

---

## What you get on every call

Every path, including `2 + 2` fast-path, returns the same `DecisionGraph`:

| Field | Meaning |
|---|---|
| `disposition` | `hard_veto` / `conflict` / `insufficient_evidence` / `qualified_consensus` / `consensus` |
| `recommended_verdict` | `approve` / `reject` / `caution` / **`null` under conflict or insufficient** |
| `evaluators` | Per-head verdicts **all kept** — nothing is dropped on timeout |
| `contradiction_score` | \(\Delta_{\max}\) |
| `uncertainty_score` | Saturated \(U \in [0,1]\) |
| `counterfactuals` | Budgeted probes on **mutable typed facts** only |
| `config_hash` | SHA-256 of canonical `EngineConfig` |
| `radar` | Axes + unresolved questions + hints (payload, not a UI) |

Optional orchestrator mapping (`to_chorusgraph`, same rules for any runtime):

| Disposition / flags | Directive | Tools |
|---|---|---|
| `HARD_VETO` | `REFUSE` | `[]` |
| `CONFLICT` | `ESCALATE` | `[]` |
| `INSUFFICIENT_EVIDENCE` | `GATHER` | `[]` + `gather_fact_keys` |
| Consensus / qualified + action + `APPROVE` | `EXECUTE` | caller allowlist |
| Consensus / qualified + assertion + `APPROVE` | `ANSWER` | `[]` |
| Consensus / qualified + `REJECT` | `REFUSE` | `[]` |
| Consensus / qualified + `CAUTION` | `ESCALATE` | `[]` |
| `review_required` would have been `EXECUTE` | `ESCALATE` | `[]` |

A `HARD_VETO` is a refuse, not a suggestion. ChorusGraph (or any orchestrator) MUST strip the tool allowlist to `[]` on `REFUSE`, `ESCALATE`, and `GATHER`. Severe contradiction (\(\Delta_{\max} > \tau_{\text{base}}\), default `0.40`) is `CONFLICT` → `ESCALATE` → tools `[]`. That is how PrismThinker protects the workflow runtime without importing it.

---

## High-value use cases

### 1. Policy vs utility (PII / GDPR / HIPAA / desk limits)

**Expectation:** policy may `REJECT` + `hard_veto`; formal and utility may still `APPROVE`. Lattice rule 1 → `HARD_VETO` → `REFUSE`. Both states stay on the graph. A resolving counterfactual (e.g. `cache_ttl` 60 → 20) is a HITL hint, not an auto-fix.

Worked example in tests: `tests/test_end_to_end.py::test_worked_example_cache_ttl`  
Bench: `privacy_pii_cache_hard_veto`, `healthcare_phi_retention_veto`, `finance_notional_veto`, `legal_gdpr_consent_veto`, `security_exfil_deny`

### 2. SRE / SLA ship gates

**Expectation:** utility can approve a healthy `p99`; causal can confirm a path; empirical uses the **caller fact** as the point estimate and trust-weights scrapes. If Prometheus sources disagree, `review_required` can promote a would-be `EXECUTE` to `ESCALATE`. That is correct — do not auto-ship through conflicting telemetry.

Bench: `sre_sla_healthy` (consensus + escalate on review), `sre_ship_closed_execute` (closed context `EXECUTE`), `sre_sla_breach`

### 3. Retrieval-contaminated decisions

**Expectation:** the same 10s PII TTL is `ANSWER` on closed facts and `CONFLICT` / `QUALIFIED` once **retrieved neighbors** inject other `cache_ttl` numeric claims. Extra evidence changes the lattice more than \(\tau\) does. That evidence can come from any store — it is not VectorPrism-specific.

Bench: `privacy_ttl_closed_answer` vs `assertion_policy_ok_answer` / `privacy_short_ttl_permit`

### 4. Science / threshold claims

**Expectation:** `p-value` and SLA targets are one-sided (`minimize` / `maximize`). A distribution lexeme still needs ≥3 observations. Thin pilots stay undetermined or conflict — they do not become a posterior.

Bench: `science_pvalue_approve`, `science_pvalue_thin_sample`

### 5. Fail-closed gather

**Expectation:** missing required `FactSpec`, policy domain with no `PolicyRule`, forced unknown evaluator, or only one determined head → `INSUFFICIENT_EVIDENCE` → `GATHER`. ChorusGraph must not invent tools.

Tests: `test_gather_fact_keys_from_missing_required`, `test_selector_fail_closed_keeps_named_heads`  
Bench: `gather_missing_required`, `gather_healthcare_no_rules`, `selector_ghost_fail_closed`

### 6. Axiomatic fast-path

**Expectation:** a query that is **only** a whitelist AST expression (`2 + 2`) returns the same envelope, `CLOSED_FORMAL`, `ANSWER`, citation `CitationKind.HYPOTHESIS`. Mixed prose (`is 2+2 legal to cache?`) does **not** fast-path.

Tests: `tests/test_ast_safe.py`

### 7. Open justice after retrieval (Oresteia)

Same shape as “should the detective kill the killer / what should happen to him,” run on a **public-domain** myth. PrismThinker will not ingest a copyrighted screenplay.

Index story chunks → retrieve on an open question → `evaluate()`. Retrieval is allowed to surface **both** the oracle that demands blood **and** the Furies / civic court. The lattice must not average that into “maybe kill him.”

**Measured result** (`python -m bench.justice`):

| Question | What retrieval found | Directive |
|---|---|---|
| Should Orestes kill Clytemnestra extra-judicially? | Oracle pressure, the killing, Furies | **`REFUSE` / `HARD_VETO`**. Policy vetoes; formal still `APPROVE`. Tools `[]`. |
| Should the Furies execute him in the street? | Blood-price counter, split verdict, Athena’s court | **`REFUSE` / `HARD_VETO`** again. Revenge text was retrieved; private execution still forbidden. |
| Should Athena’s court try him? | Court founding, commentary, counter-maxim | **`EXECUTE` `open_court`**. Consensus `APPROVE`. Only ship path. |
| What should happen to him? | Open commentary, Furies, split jury | **`ANSWER` / `QUALIFIED_CONSENSUS`**. Civic verdict, not a street killing. Δ ≈ 0.16. |

That is a good result: retrieval is messy on purpose; the coprocessor still refuses extra-judicial killing, allows a court, and answers fate as **qualified**, not as a rewritten ending.

Tests: `tests/test_justice_story.py`  
Runner: `python -m bench.justice` → `bench/out/justice/report.md`

---

## Install

```bash
pip install -e ".[dev]"
```

Neighbor bench extras (optional HTTP mock retriever, FastAPI stand-ins, Qdrant — **not** VectorPrism):

```bash
pip install -e ".[bench]"
```

Research latent extra (`experimental/latent`, not imported by `engine.py`):

```bash
pip install -e ".[latent]"   # pulls torch; never required for evaluate()
```

---

## Quickstart

```python
from prismthinker import PrismThinker, ReasoningContext

graph = PrismThinker().evaluate(ReasoningContext(query="2 + 2"))
print(graph.disposition, graph.fast_path.value)  # consensus, 4
```

Policy-gated parameter change (the v1.1 worked example):

```python
from prismthinker import PrismThinker
from prismthinker.adapters.chorusgraph import to_chorusgraph
from tests.conftest import cache_ttl_context

graph = PrismThinker().evaluate(cache_ttl_context())
assert graph.disposition.value == "hard_veto"
assert graph.evaluators["policy"].hard_veto is True
assert graph.evaluators["formal"].verdict.value == "approve"  # kept

envelope = to_chorusgraph(graph, allowed_tools=["apply_ttl"])
assert envelope.directive.value == "refuse"
assert envelope.allowed_tools == []
```

Plug-and-play on an existing retriever is **Mode 2** (see [Two modes of operation](#two-modes-of-operation)). Same `evaluate()` as the sovereign stack.

**Boundary:** [VectorPrism](https://github.com/insightitsGit/VectorPrism) is the sensory layer (rhetorical/causal cuts, PSM 1024d, HNSW + intent rescore). PrismThinker is the executive layer (`ReasoningContext` → lattice). They join only through `from_vectorprism()`. PrismThinker does not chunk, dense-embed, or keep an ANN index.

```python
from prismthinker import PrismThinker
from prismthinker.adapters.vectorprism import VectorPrismDocument, from_vectorprism

ctx = from_vectorprism(
    query,
    [
        VectorPrismDocument(
            id="chunk-1",
            text="cache_ttl of 10 seconds",
            source="policy.privacy",
            score=0.81,  # topical fallback only
            metadata={
                "trust": 0.95,
                "numeric_claims": {"cache_ttl": 10},
                "negates_id": "chunk-0",  # upstream factual inversion
            },
        )
    ],
    extra=seed_with_hypothesis_and_rules,
)
graph = PrismThinker().evaluate(ctx)
```

Mapping: `text → EvidenceItem.content`; `metadata.trust` else clipped `score → trust`; `metadata.numeric_claims` lifted as typed numbers (heads do not parse prose); `metadata.negates_id` / `negates_ids` feed the evidence-conflict pass (`EXPLICIT_NEGATION`) before the epistemic pool.

`from_documents` / LangChain / LlamaIndex helpers use the same mapping. Production `PolicyRule` / `CausalGraph` belong in a registry on `extra=` or the caller, not in ANN chunks. Rank is not a preference signal.

Local hashed n-gram retrieve (`bench/chunks.py`, `bench/encode.py`, `bench/index.py`) is a **bench stand-in** so tests can run without VectorPrism. It is not the product encoder.

---

## Heads (v1.1 default registry)

| Head | Asks | May `hard_veto` | Backend |
|---|---|---|---|
| `formal` | Is this structurally valid? | **No.** Never reads `PolicyRule`. | solver / predicates |
| `policy` | Is this permitted? | **Yes** (only default veto head) | deontic rules |
| `empirical` | Do numeric observations meet the threshold? | No | stats |
| `causal` | Does treatment reach outcome on the graph? | No | signed graph |
| `utility` | Does the objective score pass? | No | objective terms |

They may share a **predicate parser**. They must not share a decision procedure. Two LLM prompts do **not** count as two independence classes. `EngineConfig.llm.enabled=True` fail-closes (`REASON_LLM_INVALID`). There is no LLM evaluator backend in v1.1.

---

## Disposition lattice (priority, not averaging)

First matching rule wins:

1. Authorized policy veto → `HARD_VETO` / `REJECT`
2. Fewer than 2 determined heads **or** \(U \ge u_{\text{insufficient}}\) → `INSUFFICIENT_EVIDENCE` / `null`
3. \(\Delta_{\max} > \tau_{\text{eff}}\) → `CONFLICT` / `null`
4. Majority + (dissent **or** caution **or** \(\Delta_{\max} > \tau_{\text{qualified,eff}}\)) → `QUALIFIED_CONSENSUS`
5. Unanimous determined + low \(\Delta\) → `CONSENSUS`
6. Majority tie → `CONFLICT` / `null`

\(\tau_{\text{eff}}\) starts from the prior `tau_base` (default `0.40`) and is adjusted per run when `dynamic_tau=True` (default). Approve-vs-reject in the same pool **tightens** \(\tau\) (never widens to hide a split). Values are in `timings_ms.tau_effective` / `tau_base`. Set `dynamic_tau=False` to lock the raw prior.

---

## Tests and what they expect

```bash
pytest
```

Current suite: **108 tests** (`tests/`, `pythonpath` includes `src` and repo root). Non-LLM paths are deterministic on `disposition`, `recommended_verdict`, \(\Delta\), \(U\), and per-head verdicts (`test_byte_stable_non_llm_fields`).

| File | What it guards | Expectation if it fails |
|---|---|---|
| `test_invariants.py` | Preference isolation, formal≠policy, veto capability, fail-closed LLM/selector/timeout, closed reason codes, citation sanitizer, no latent/torch/adapter import from engine, pool deep-copies, sanitized crashes | **Ship-blocker.** A pass here is the v1.1 constitution. |
| `test_ast_safe.py` | Whitelist walker; no `eval`; mixed prose rejected; `2+2` envelope | Fast-path leaked into dialectic, or unsafe AST |
| `test_classifier.py` | Regime features, overlays, force override, math-shaped ≠ fast-path | Wrong heads selected downstream |
| `test_evaluators.py` | Each head happy/missing; no context mutation; assumptions; fact-primary empirical; SLA one-sided; n≥3 on distribution lexemes | A head is inventing signal or writing the context |
| `test_evidence.py` | Numeric, trust, negation, stale, temporal conflicts | Evidence pass is silent |
| `test_contradiction.py` | Weights sum to 1; approve↔reject conclusion = 1; inverted constraints/assumptions; `EvaluatorPair` lex-sorts in `mode="before"` and is frozen | \(\Delta\) is no longer explainable |
| `test_uncertainty.py` | \(U\) saturated; empty evidence does not fake coverage | Insufficient/conflict gates mis-fire |
| `test_disposition.py` | Lattice table including tie → conflict | Averaging or a nullable-verdict bug |
| `test_counterfactual.py` | Only mutable specs; original facts unchanged; budget cap | Probes mutate production state |
| `test_thresholds.py` | Prior is the center; off switch; polar never widens; clip bounds; determinism | Dynamic \(\tau\) became a second lattice |
| `test_isolation.py` | Hung worker is terminated; isolated formal returns a result | Timeout cannot kill a head |
| `test_adapters.py` | `REFUSE` empty tools; conflict strips tools; triad `from_vectorprism` → evaluate → `to_chorusgraph` blocks execution | Orchestrator could still call tools, or VectorPrism inversions skipped the conflict pass |
| `test_rag_plugin.py` | Public plug-in imports; LangChain-shaped hits; refund cap `HARD_VETO` blocks generation; under-cap does not veto | RAG drop-in could not halt before the LLM |
| `test_chunks.py` | Bench ingest stamps `numeric_claims` + source trust; cosine is not trust; empirical can fire | Bare RAG text starved the lattice |
| `test_encode_index.py` | Bench hashed n-gram is unit; `EvidenceIndex` retrieves policy chunks; seed hypothesis kept | Bench stand-in drifted |
| `test_wire_and_bench.py` | Freshness mapping; local hybrid retrieval; **all `gold.contract` scenarios** | Neighbor wire or contract gold drifted |
| `test_justice_story.py` | Oresteia retrieve→evaluate: private killing `REFUSE`; court is not `REFUSE`; no screenplay | Averaged revenge into a ship, or ingested copyrighted text |
| `test_end_to_end.py` | Worked PII-cache example; `config_hash`; byte-stable fields | The spec’s §20 example is dead |

**Contract gold** (`gold.contract=True` in `bench/scenarios.py`) is the bar that must not move when priors or \(\tau_{\text{eff}}\) change:

- Fast-path arithmetic → `ANSWER` / consensus / approve
- Hard-veto domains → `REFUSE` / empty tools
- Missing required fact / ghost evaluator → `GATHER`
- Conflict → `recommended_verdict is None`

Labeled (non-contract) gold describes **intended outcomes under the current engineering priors**. It is a measurement target, not a proof of calibration.

---

## Optional neighbor bench (Docker Desktop + local)

The bench is a **stack simulator**. `bench/services/mock_retriever.py` is not VectorPrism. `bench/services/chorusgraph.py` is not ChorusGraph.

```bash
pip install -e ".[bench]"
docker compose up -d --build          # Qdrant :6333, mock retriever :8081, mock orchestrator :8082
python -m bench.runner --backend docker --out bench/out/docker
```

No Docker:

```bash
python -m bench.runner --backend local --out bench/out/local
```

What the runner does:

1. Index 28 generic `RetrievedDocument`s (hybrid hashed n-gram + lexical rerank; Qdrant on Docker)
2. For each of **28 labeled scenarios**, `retrieve` → `from_documents` → `evaluate` → `to_chorusgraph` → `honor_envelope`
3. Optionally sweep `tau_base × qualified_tau × u_insufficient` (27 cells)
4. Write `report.json`, `report.md`, and per-scenario wire dumps under `payloads/`

**Latest local default-prior mix** (engineering priors + dynamic \(\tau\), 28 scenarios):

| Directive | Count | Read as |
|---|---:|---|
| `ESCALATE` | 13–14 | Conflict or review — do not ship |
| `REFUSE` | 5 | Authorized veto |
| `ANSWER` | 4–5 | Assertion consensus / qualified |
| `GATHER` | 4 | True holes (facts/rules/types/ghost) |
| `EXECUTE` | 1 | Closed SRE ship only |

`GATHER` used to be 13/28 when retrieval noise starved heads. After fact-primary empirical, metadata lift, and formal-on-pragmatic, leftover gathers are the fail-closed cases. `EXECUTE` once is not a bug: live retrieval with disagreeing scrapes is supposed to hesitate.

Sweep takeaway: on this grid the **center** `tau_base=0.40`, `qualified_tau=0.20` is the unique 100% labeled cell. `0.30` over-conflicts; `0.50` swallows real splits. That is a **bench optimum**, not a fitted production prior.

---

## Calibration

**Status: not calibrated.** v1.1 says this in the spec and the code comments mean it.

| Knob | Default | What it is |
|---|---|---|
| `tau_base` | `0.40` | Prior center for “this \(\Delta_{\max}\) is conflict” |
| `qualified_tau` | `0.20` | Prior center for “majority but not clean” |
| `u_insufficient` | `0.60` | \(U\) at or above this → gather |
| Contradiction weights | 0.35 / 0.25 / 0.15 / 0.15 / 0.10 | Must sum to 1.0 |
| `uncited_penalty` | `0.50` | Confidence multiplier on uncited claims |
| Dynamic \(\tau\) shifts | ±0.02–0.06 | Deterministic, not learned |

**Calibrated** would mean: on a held-out, labeled corpus of real retrievals (any store) + human/policy outcomes, the chosen \(\tau\) (or a domain profile) minimizes a stated loss (false `EXECUTE`, missed veto, over-`GATHER`) with confidence intervals, and the profile is versioned separately from schema `1.1.0`. You do **not** need VectorPrism to calibrate.

**We do not have that.** What we have:

1. **Engineering priors** — chosen so the lattice is usable and the worked example is executable.
2. **A 28-scenario synthetic-but-wired bench** — real Qdrant/HTTP payloads, designed cases, not a customer corpus.
3. **A sweep** — shows the prior is *load-bearing* (`0.40` least-wrong *here*).
4. **Dynamic \(\tau\)** — uses the prior as input so one global `0.40` is not a lock. It is still a hand-written schedule.

**How to calibrate later (without opening v1.2 schema):**

1. Log `DecisionGraph` + the orchestrator journal (`EXECUTE`/`REFUSE`/human override).
2. Label **false ship**, **missed veto**, **needless gather**, **correct hesitate**.
3. Fit **domain profiles** (`EngineConfig` per `privacy` / `sre` / `finance`) that override `tau_base`, `qualified_tau`, `u_insufficient` only.
4. Keep `config_hash` in the graph so two profiles never silently mix.
5. Do **not** train \(\Delta\) weights or add LLM heads to “finish” v1.1.

`dynamic_tau=False` is the control for A/B against a frozen prior. ECE / reliability diagrams belong on the orchestrator or a later calibration package — not inside `evaluate()`.

---

## Configuration

```python
from prismthinker import EngineConfig, LLMConfig, PrismThinker

thinker = PrismThinker(
    EngineConfig(
        tau_base=0.40,
        qualified_tau=0.20,
        u_insufficient=0.60,
        dynamic_tau=True,
        isolate_heads=True,          # process isolation for standard heads
        llm=LLMConfig(enabled=False),
    )
)
```

`DecisionGraph.config_hash` is SHA-256 of the canonical JSON of this object (sorted keys). Changing selector tables, \(\tau\), or `dynamic_tau` changes the hash. Tests pin “same constructor → same hash,” not a frozen hex in the spec.

Latency budgets (priors, not SLOs we have measured in prod): fast-path ≪ 1 ms; head 250 ms; pool 400 ms; counterfactuals +200 ms.

---

## What v1.1 explicitly is not

- Not an LLM product. No NL→policy, no streaming dialectic.
- Not SMT. Formal is typed facts + recursive-descent predicates.
- Not a retriever and not an orchestrator. Mode 1 composes the triad; Mode 2 drops into any RAG pipeline. `evaluate()` never imports `adapters/`, `vectorprism`, or `chorusgraph`.
- Not activation steering. `experimental/latent` must not be imported by `engine.py` (`test_engine_does_not_import_latent`, `test_engine_does_not_import_torch`). `torch` is `.[latent]` only.
- Not a radar UI. `EpistemicRadarPayload` is data.

A later version is allowed only when implementation or benchmarks **falsify** a v1.1 rule.

Product-boundary note: [`docs/research-handoff-vectorprism-coupling.md`](docs/research-handoff-vectorprism-coupling.md).

---

## Repository map

```text
src/prismthinker/
  core/          engine, lattice, Δ, U, thresholds, isolation
  evaluators/    formal, policy, empirical, causal, utility
  classifier/    AST fast-path + feature regime
  adapters/      from_vectorprism / from_documents / from_langchain ingress,
                 allow_generation RAG gate, chorusgraph egress, HTTP clients
                 (engine.py must not import this tree)
docs/            architecture-specification-v1.1.md (contract)
tests/           invariants first
bench/           corpus, scenarios, hashed-ngram stand-in index, Docker neighbors, justice demo
docker-compose.yml
```

---

## License / status

**Author:** Amin Parva

Package version `1.1.0`. Schema `1.1.0`. Architecture **frozen**. Calibration **not claimed**.
