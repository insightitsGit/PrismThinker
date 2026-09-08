# Changelog

All notable changes to this package are recorded here. The frozen v1.1 contract
is historical; the working implementation now emits schema `1.2.0`.

## Unreleased

- v1.2 eligibility gate: proven blockers refuse independently of evaluator voting;
  missing facts gather and unresolved authority/errors require review. Explicit
  trusted hard veto precedence is preserved. See `docs/eligibility-v1.2.md`.
- Typed aligned claims, separate conflict signals and an aligned shadow score.
  Existing Delta weights/formula are unchanged. Added gate-only validation ablation.
- Policy incomplete-check fail-open fixed; malformed constraints remain unchecked;
  tie reporting and strict critical-pair threshold corrected.
- New graphs/configs use schema 1.2.0; legacy 1.1.0 graphs remain readable.
- README is indexed around pre-execution agent guardrails / tool-call firewall
  (same `evaluate()` contract; no formula change)
- Public exports: `FactSpec`, `FactType`, `FactValue`

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
