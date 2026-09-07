# Changelog

All notable changes to this package are recorded here. Schema and architecture
version remain `1.1.0` unless a later release says otherwise.

## 1.1.0 — 2026-09-07

First public install (`pip install prismthinker`). MIT license. Architecture
**v1.1 FROZEN** (`docs/architecture-specification-v1.1.md`).

This is the executable close of the v1.0 holes: one typed `Hypothesis`, closed-form
\(\Delta_{ij}\), saturated \(U\), a priority lattice with nullable
`recommended_verdict`, authorized veto on `policy` only, and a pydantic-only
`evaluate()` path.

### Contract
- Public API: `PrismThinker.evaluate(ReasoningContext) → DecisionGraph`
- `PresentationContext` is rejected
- `EvaluatorPair` sorts in `mode="before"` and is frozen
- Polarity-mismatched claims are dropped before \(\Delta\) and tagged
  `REASON_POLARITY_MISMATCH`
- Crash messages on the graph are single-line; tracebacks stay in logs
- Thread-pool workers receive deep copies; production default is process isolation
  (`isolate_heads=True`)
- `dynamic_tau=True` derives bounded \(\tau_{\text{eff}}\) from run-local conditions;
  `dynamic_tau=False` restores `tau_base`

### Package boundary
- `core/` does not import VectorPrism, ChorusGraph, torch, or an ANN client
- `from_vectorprism()` / `to_chorusgraph()` are optional adapters
- Standard RAG plug-in: `from_langchain` / `from_documents` / `allow_generation`
- `experimental/latent` is `pip install 'prismthinker[latent]'` and is not on the
  evaluate path

### Not claimed
- Calibration of \(\tau\) / contradiction weights
- LLM evaluator backends
- Chunking, dense embedding, or ANN inside this package
