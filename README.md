# PrismThinker

[![PyPI version](https://img.shields.io/pypi/v/prismthinker.svg?color=blue)](https://pypi.org/project/prismthinker/)
[![Python Versions](https://img.shields.io/pypi/pyversions/prismthinker.svg)](https://pypi.org/project/prismthinker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/insightitsGit/PrismThinker/actions/workflows/ci.yml/badge.svg)](https://github.com/insightitsGit/PrismThinker/actions/workflows/ci.yml)

**A typed decision gate for evaluating proposed AI-agent actions before execution.**

PrismThinker checks structured facts, constraints, policies, evidence, causal
paths and objectives. It preserves evaluator verdicts and disagreement in a
`DecisionGraph`, then maps that graph to an operational directive. The host
orchestrator must enforce the directive before running tools.

```text
Host-owned ReasoningContext → eligibility checks + evaluators → DecisionGraph
                                                               ↓
                                                       to_chorusgraph()
                                                               ↓
                                      EXECUTE | ANSWER | REFUSE | ESCALATE | GATHER
```

## Test results at a glance

- **247 automated tests passed locally**, covering the engine, adapters and
  validation harness. See [tests and reproduction instructions](#tests) and
  [hardening regression tests](tests/test_enterprise_correctness.py).
- **180/180 correct action directives after the fixes**, with **0 unsafe
  executions across 93 unsafe cases**. Execution coverage remained **48.3%**
  (87/180 cases). See the [development replay report](validation/reports/enterprise-correctness-development.md)
  and [per-case results](validation/reports/enterprise-correctness-development.json).
- **Real local-model comparison: 180 frozen cases and 1,080 model calls.**
  The original full engine produced **6/93 unsafe executions**, versus
  multi-model majority vote's **28/93**, at the same **48.3% execution coverage**.
  See the [full findings](validation/reports/local-v1.2-fresh-001/FINDINGS.md)
  and [measurement audit](validation/reports/local-v1.2-fresh-001/MEASUREMENT_AUDIT.md).

The original study used assistant-authored cases frozen before model evaluation.
The subsequent replay tests repairs on those already inspected cases; it is not
an independent held-out result. Both reports are retained so readers can inspect
the improvements and their limits. [All saved validation reports](#tests).

## Current status

This checkout prepares the **1.2.0 beta SDK release**, using schema **1.2.0**,
including the enterprise-hardening changes described here. See the
[release notes](CHANGELOG.md). The release has been validated locally; a build
does not publish it to PyPI or establish that remote CI has passed.

**The current target is a supervised SDK pilot or shadow evaluation, not
unattended enterprise production.** Keep production actions behind human
approval during the pilot. Passing tests and repairing known cases do not
establish safety on unseen customer workloads.

- **Implemented:** eligibility checks that cannot be outweighed by evaluator
  votes; scoped policy authority; typed conflict signals; mandatory causal and
  objective checks; guarded evidence supersession; a trusted proposal adapter.
- **Locally verified:** 247 tests passed. The development replay gets 180/180
  directives correct, with 0 unsafe executions among 93 unsafe cases and 48.3%
  execution coverage. Those cases were inspected before the fixes.
- **Still required for production:** approval bound to exact action arguments and
  current policy, replay protection, request-wide limits and deadlines, host/API
  authentication and authorization, audit and monitoring controls, rollback,
  release checks and independently reviewed customer validation.

See [enterprise behavior and integration requirements](docs/enterprise-hardening.md),
[v1.2 eligibility and migration](docs/eligibility-v1.2.md), and the
[development replay](validation/reports/enterprise-correctness-development.md).
The [frozen v1.1 specification](docs/architecture-specification-v1.1.md) is historical.

## What the library provides

- Policy, formal, empirical, causal and utility evaluators for one typed hypothesis.
- Eligibility routing: proven blockers refuse; unresolved authority or conflicts
  escalate; missing required information gathers evidence.
- Contradiction and uncertainty diagnostics. Their thresholds are engineering
  priors, and incremental value from Δ over simpler disagreement is unproven.
- Budgeted counterfactual probes on mutable facts. These are diagnostic proposals,
  not authorization to alter facts or execute a modified action.
- A default evaluation path with no model calls or GPU requirement. The core
  dependency is `pydantic`; benchmarks, validation and latent experiments use extras.

Latency depends on configuration, workload and hardware. Default process
isolation adds startup overhead; historical thread-mode numbers are not a
production latency guarantee. See the saved [latency measurements](validation/reports/generated/latency-20260907T081123Z-9c6f716a/summary.md).

---

## Installation

```bash
pip install prismthinker
```

Python **3.11+**. The command above installs the published package. To use the
implementation described here, install from this checkout:

```bash
pip install -e ".[dev,validation]"  # full test suite, coverage, build
pip install -e ".[bench]"          # optional local benchmark services
pip install -e ".[latent]"         # optional torch experiments
```

---

## Quickstart: guard a tool call

This example uses host-owned facts and policy. The host must verify that facts
match the proposed action and remain current at execution. Recovery probes
`structured_facts`, not `action.payload`; a resolving probe does not approve
the original payload.

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
    RuleSeverity,
)
from prismthinker.adapters.chorusgraph import to_chorusgraph
from prismthinker.core.schemas import ChorusGraphDirective

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

if envelope.directive is ChorusGraphDirective.EXECUTE:
    # In a pilot, also obtain human approval. The host must validate arguments,
    # check the tool allowlist and execute exactly the evaluated action.
    print("ELIGIBLE FOR HOST EXECUTION", context.hypothesis.action)
else:
    print("NOT EXECUTABLE", envelope.directive.value, envelope.allowed_tools)
    for cf in graph.counterfactuals:
        if cf.resolving:
            print("DIAGNOSTIC PROPOSAL", cf.resolving_condition)
```

This refund produces `REFUSE` and an empty tool list. Always consume the final
adapter directive: the legacy graph verdict describes evaluator agreement and
can differ from the eligibility decision. `PresentationContext` is rejected by
`evaluate()`.

### Untrusted action proposals

For model-proposed actions, use
`prismthinker.adapters.trusted.evaluate_proposal`. It accepts a statement and
candidate action, rejects extra top-level fields, checks a host action-name
allowlist and evaluates a deep copy of host-owned context. The host supplies
policies, evidence, authority, facts and allowed tools.

This is an in-process boundary. It does not authenticate network clients, sign
envelopes or prevent replay. Never accept a client-supplied `EXECUTE` envelope
as authorization. See the [trusted SDK example](docs/enterprise-hardening.md#trusted-sdk-entry-point).

---

## Core architecture

```text
[ Candidate action / Hypothesis ]
               │
               ▼
0. Eligibility assessment         mandatory checks, authority and evidence
               │
               ▼
1. Epistemic regime classifier     fast-path arithmetic (AST whitelist) or dialectic
               │
               ▼
2. Dynamic evaluator selection     policy, formal, empirical, causal, utility
               │
               ▼
3. Head evaluation                 typed claims and evaluator diagnostics
               │
               ▼
4. Contradiction + uncertainty     closed-form Δ_ij ; saturated U ∈ [0, 1]
               │
               ▼
5. Counterfactual probes           mutable FactSpec values only
               │
               ▼
6. Priority disposition lattice    legacy graph verdict
               │
               ▼
7. Directive adapter               eligibility takes precedence; host enforces
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

Only `EXECUTE` may keep tools. Consensus with `CAUTION`, or an execution decision
requiring review, escalates. The host remains responsible for actual execution
enforcement.

---

## RAG and orchestrators

Framework-agnostic. Compatible with LangChain, LangGraph, CrewAI, or any runtime that honors `ChorusGraphEnvelope`. There is no dedicated MCP or AutoGen adapter in this source tree — pass a `ReasoningContext` in and honor the envelope out.

- **Retriever-agnostic:** `EvidenceItem` / `from_documents` / `from_langchain` / `from_llamaindex`, or [VectorPrism](https://github.com/insightitsGit/VectorPrism) via `from_vectorprism()`.
- **Orchestrator-agnostic:** [ChorusGraph](https://github.com/insightitsGit/ChorusGraph) via `to_chorusgraph()`, or LangGraph / CrewAI / a custom host.

Unix rule: VectorPrism finds evidence. PrismThinker tests the logic. ChorusGraph (or your orchestrator) runs tools **only** if the envelope says `EXECUTE`.

---

## Validation status

The [validation harness](validation/README.md) covers agent execution,
policy/compliance and evidence-conflict reasoning.

The frozen **v1.2 local-model study** used 180 assistant-authored cases and
1,080 model calls. PrismThinker made **6/93 unsafe executions**, compared with
majority vote's **28/93**, at equal **48.3% execution coverage**. These are
local small-model comparisons on authored data, not independent expert validation.

After inspecting those cases and fixing causal, objective and evidence handling,
the **development replay** produces **180/180 correct directives**, **0/93 unsafe
executions** and unchanged **48.3% coverage**. The shared eligibility-only ablation
also gets all directives correct. This demonstrates repair of known failures;
it does not establish generalization or unique benefit from Δ.

The reports preserve the original failures and explain conflict-metric caveats.
The replay's legacy verdict and broad-conflict metrics differ from operational
directives and semantic conflict. Its zero engine-latency fields are uninstrumented
placeholders. See the [measurement limits](validation/reports/enterprise-correctness-development.md#measurement-limits).

**Calibration is not claimed.** `tau_base=0.40`, `qualified_tau=0.20` and
`u_insufficient=0.60` are engineering priors. Aligned Δ remains a shadow diagnostic.

---

## Tests

The [enterprise correctness milestone](docs/enterprise-hardening.md) adds mandatory
causal/objective gates and a trusted SDK proposal boundary. Its
[development replay](validation/reports/enterprise-correctness-development.md)
corrects all 180 previously inspected directives, with 0/93 unsafe executions.
This replay is a regression check, not new held-out scientific validation.

Saved scientific validation reports:

- [Fresh v1.2 full comparison](validation/reports/local-v1.2-fresh-001/FINDINGS.md): 180 new frozen cases and 1,080 model calls. PrismThinker made 6/93 unsafe executions versus majority vote's 28/93 at equal 48.3% coverage; the gate-only baseline made 21/93 at 56.7% coverage. The original causal failures, Delta limitations and a conflict-reporting audit are documented; the subsequent development replay is separate. Assistant-authored synthetic data, not independent expert validation.
- [Local multi-model findings: 180 cases](validation/reports/local-v0.2-L-002/INTERPRETATION.md), [full measurements and plots](validation/reports/local-v0.2-L-002/summary.md), and [reproduction protocol](validation/LOCAL_SCIENCE.md). The corrected repeat observed 0/101 unsafe executions at 43.9% coverage, but 53.3% directive accuracy and zero conflict F1. It is a post-audit repeat on authored synthetic cases, not an independent held-out benchmark.
- [Original local-run input audit](validation/reports/local-v0.2-L-001/AUDIT.md), with the compromised run's raw results preserved.
- [v0.1.1 scripted-baseline report](validation/reports/generated/20260907T081332Z-7535746d/summary.md) and [latency report](validation/reports/generated/latency-20260907T081123Z-9c6f716a/summary.md).

```bash
pytest
```

The latest full local run passed **247 tests**. CI (`.github/workflows/ci.yml`)
is configured to run pytest on Python 3.11 and 3.12, plus package build and
`twine check`. Isolation and predicate coverage checks require at least 90%.
The refund behavior is covered by `tests/test_readme_quickstart.py`; the new
hardening checks are in `tests/test_enterprise_correctness.py`. Local success
does not establish the status of a remote CI run.

---

## Scope and limitations

- Not a hosted production service. The FastAPI services under `bench/` are benchmark helpers.
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
