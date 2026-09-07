# Research handoff: PrismThinker does not need VectorPrism

**Status:** open research note (not a spec change)  
**Date:** 2026-09-06  
**Repo:** https://github.com/insightitsGit/PrismThinker  
**Related:** [VectorPrism](https://github.com/insightitsGit/VectorPrism), [ChorusGraph](https://github.com/insightitsGit/ChorusGraph)  
**Contract:** [`architecture-specification-v1.1.md`](./architecture-specification-v1.1.md) — frozen, schema `1.1.0`

This note exists because the README / spec *story* makes it look like three products are one pipeline. They are not mixed at runtime. If you only read the diagram, you will over-couple them.

---

## 1. The issue in one sentence

**PrismThinker evaluates a typed `ReasoningContext`. VectorPrism is an optional document-shaped *ingress example*, not an input to `evaluate()` and not a package dependency.**

You do not import VectorPrism. You do not call VectorPrism inside the lattice. You can (and should) run PrismThinker with a hand-built context: hypothesis + facts + rules + evidence.

The mix you are seeing is **product positioning + a bench fake**, not a shared brain.

---

## 2. What PrismThinker actually requires

Public API (`src/prismthinker/__init__.py`):

```text
PrismThinker.evaluate(ReasoningContext) → DecisionGraph
```

That is the whole product.

`ReasoningContext` is owned by PrismThinker (`src/prismthinker/core/schemas.py`). Typical fields a head actually reads:

| Input | Who must supply it | Why |
|---|---|---|
| `Hypothesis` | caller | the one proposition every head scores |
| `facts` / `fact_specs` | caller (or lifted from extra metadata) | empirical / probes |
| `policy_rules` | caller | only `policy` may veto |
| `constraints` | caller | `formal` structure |
| `causal_graph` | caller | `causal` path tests |
| `evidence[]` | caller | citations, trust, numeric claims, staleness |
| `domain`, `query` | caller | selector + classifier |

None of those types mention VectorPrism. `pyproject.toml` runtime deps are **pydantic only**. There is no `vectorprism` Python package, no VectorPrism import, no ANN, no Qdrant on the default evaluate path.

**Minimum working call (no retrieval):**

```python
from prismthinker import PrismThinker, ReasoningContext, Hypothesis
# ... fill Hypothesis, facts, PolicyRule, EvidenceItem yourself ...
graph = PrismThinker().evaluate(ctx)
```

If that context is well-typed, VectorPrism is irrelevant.

---

## 3. What VectorPrism actually is (in this repo)

Three different things share the name. That is the confusion.

### A. Named neighbor in the spec (example, not ownership)

Spec §5.1 defines an **ingress mapping**: documents → `ReasoningContext`.

VectorPrism is named the way “S3” is named in a storage spec: a likely producer of blobs, not a fused module.

The spec also says retrieval rank **must not** enter evaluators as a preference signal. Rank may only become `EvidenceItem.trust`. That rule only makes sense if retrieval stays **outside** the lattice.

### B. Adapter in this repo (shape copy, no VectorPrism code)

`src/prismthinker/adapters/vectorprism.py`

- `VectorPrismDocument` — a local pydantic model (id, text, source, score, metadata)
- `from_vectorprism(...)` — maps those docs into `ReasoningContext`
- HTTP request/response models for a retrieve/index API

This is **not** the VectorPrism codebase. It is a DTO named after the sibling product. You could rename it `RetrievedDocument` and nothing in `engine.py` would change.

`from_vectorprism` is also **not** on the public `__all__` of the package root. Callers who only `import prismthinker` never see it.

### C. Bench stand-in (fake service)

`bench/services/vectorprism.py` + `bench/store.py` + Docker Compose `:8081`

This is **vectorprism-lite**: FastAPI + hashed n-gram / Qdrant. It exists so we could stress `from_vectorprism` with retrieval-shaped payloads. It is **not** [insightitsGit/VectorPrism](https://github.com/insightitsGit/VectorPrism).

Same pattern on the other side: `bench/services/chorusgraph.py` is not ChorusGraph.

---

## 4. Why it looked mixed

| Layer | What we did | What it accidentally implied |
|---|---|---|
| Spec topology | “sits between vectorprism and chorusgraph” | PrismThinker cannot run without them |
| README | worked examples use `from_vectorprism` | retrieve is part of evaluate |
| Bench | 28 scenarios: retrieve → evaluate → honor envelope | calibration needs VectorPrism traffic |
| Docker | Qdrant + vectorprism-lite | this repo *is* a retriever |
| Calibration note | “log real VectorPrism retrievals” | priors cannot be studied without ANN |

All of that is **integration theater for the neighbor contract**. It is useful if you are wiring a stack. It is misleading if you are researching the measurement layer.

ChorusGraph is the same story, inverted: `to_chorusgraph(graph)` is an **egress mapper**. `evaluate()` does not know about tools. Tools are forbidden unless the envelope says `EXECUTE`.

---

## 5. What is *not* mixed (invariants to keep)

1. **`engine.py` must not import adapters.** Heads, lattice, \(\Delta\), \(U\), selector live on `ReasoningContext` only.
2. **`experimental/latent` must not be imported by the engine.** Separate freeze rule; same idea: no silent fusion.
3. **Presentation / persona / chat history is rejected.** Retrieval rank is also not a preference. Both are “do not let a neighbor leak into the lattice.”
4. **Hard veto stays in `policy`.** A retrieved document cannot veto by existing; a `PolicyRule` can.
5. **Byte-stability** is `config_hash` + canonical context. Neighbor HTTP is out of that hash.

If a future change makes `evaluate()` call VectorPrism or Qdrant, that is a spec break, not a feature.

---

## 6. When you *would* use the VectorPrism adapter

Use it only as a **translator** at the process boundary:

```text
some retriever (VectorPrism or otherwise)
        → list of {id, text, source, score, metadata}
        → from_vectorprism(...)   # optional
        → ReasoningContext
        → PrismThinker.evaluate
        → DecisionGraph
        → to_chorusgraph(...)     # optional
        → orchestrator honors directive
```

You need *some* evidence/facts/rules. You do **not** need that evidence to come from VectorPrism. A CRM, a policy store, a unit-test fixture, or a human form is equally valid.

The empirical head cares about **typed facts and numeric claims**, not about ANN neighbors. If retrieval dumps unstructured text with no `FactSpec` / `numeric_claims` / rules, you get `GATHER` or `UNDETERMINED` — that is a **caller packaging** problem, not a reason to merge the products.

---

## 7. Research questions (this is the work)

Use these as the actual issue list. Do not start by reading VectorPrism’s encoder.

### Coupling (primary)

1. Should the spec stop naming `vectorprism` / `chorusgraph` as topology and instead name **ingress DTO** / **egress envelope**? (Recommended direction: yes — names in §5 are examples.)
2. Should `VectorPrismDocument` be renamed `RetrievedDocument` so the adapter is retriever-agnostic?
3. Should HTTP clients (`VectorPrismClient`, `ChorusGraphClient`) leave this package entirely and live in an integration repo?
4. Is `bench/services/vectorprism.py` allowed to keep the VectorPrism name, or does that poison onboarding?

### Boundary of responsibility

5. Who types the hypothesis — retriever, PrismThinker classifier, or ChorusGraph? Today: **caller**. Retrieval does not invent a `Hypothesis`.
6. Who owns `policy_rule` / `causal_graph` in document metadata? Lifting them from VectorPrism-shaped metadata was a bench convenience. A real policy store may be a better source than ANN chunks.
7. Is trust = retrieval score acceptable, or must trust come from a provenance system VectorPrism does not own?

### What not to research here

8. **Calibration of \(\tau\)** is a *separate* issue. It needs labeled **DecisionGraphs + outcomes**, not VectorPrism. You can calibrate on fixture contexts. See README § Calibration. Do not block calibration on retrieving from VectorPrism.
9. VectorPrism’s own ANN / hybrid rank quality is VectorPrism’s problem. PrismThinker should be invariant to *how* documents were found, given the same `EvidenceItem`s.
10. Do not open v1.2 (LLM heads, learned \(\Delta\), multi-hypothesis) to “integrate VectorPrism.” That would mix products for real.

---

## 8. Suggested reading order

Spend time here, in this order:

1. `src/prismthinker/__init__.py` — public surface (no VectorPrism)
2. `src/prismthinker/core/engine.py` — `evaluate()`; confirm no adapter import
3. `src/prismthinker/core/schemas.py` — `ReasoningContext`, `Hypothesis`, `DecisionGraph`
4. Spec §1 topology vs §5 neighbor contracts (notice: adapter, not engine)
5. `src/prismthinker/adapters/vectorprism.py` — mapping only
6. `tests/test_end_to_end.py` / `tests/test_invariants.py` — engine tests with **hand-built** context
7. `bench/runner.py` — the one place retrieve is wired (optional path)

Skip until you need the neighbor story: `bench/store.py`, Qdrant, Docker, VectorPrism’s repo.

---

## 9. Working hypothesis for the research

Treat the three repos as **three contracts**, not one mixed service:

| Product | Owns | Must not own |
|---|---|---|
| VectorPrism | split, encode, ANN, retrieved documents | lattice, veto, tools |
| **PrismThinker** | typed hypothesis, independent heads, \(\Delta\), disposition, `DecisionGraph` | search index, tool runtime |
| ChorusGraph | graph runtime, tools, tokens, honor/refuse | averaging head verdicts |

The bug in the current narrative is using VectorPrism as the **default mental model of an input**, so it feels like you must mix them to have a complete system. A complete PrismThinker run is a complete `ReasoningContext`. Retrieval is one way to fill `evidence[]`. It is not part of thinking.

---

## 10. If you change something later (do not do this in v1.1 freeze)

Allowed without a schema bump (documentation / naming only):

- README: lead with `evaluate(ReasoningContext)`; put VectorPrism under “optional ingress”
- Rename DTOs in a later minor if you accept adapter churn
- Move `bench/services/*` docs to “stack simulator, not the sibling products”

Not allowed under frozen v1.1:

- Importing VectorPrism or Qdrant from `engine.py`
- Making `evaluate()` retrieve
- Treating retrieval score as a sixth head
- Training \(\tau\) on VectorPrism rank

---

## 11. Bottom line

You were right not to see a reason to mix them.

- **Need VectorPrism to use PrismThinker?** No.
- **Need VectorPrism inside the lattice?** No, and it would be a freeze violation.
- **Need a retriever at all?** Only if the caller has no other way to populate evidence/facts. Many of the strongest tests never retrieve.
- **Why the name is everywhere:** sibling-stack story + optional adapter + a fake bench service that borrowed the name.

Research the **ingress contract** (what a document must contain to become evidence/facts/rules). Do not research merging the codebases.
