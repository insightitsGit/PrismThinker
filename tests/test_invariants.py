from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import time

from pydantic import ValidationError

from prismthinker import PresentationContext, PrismThinker, ReasoningContext
from prismthinker.config import EngineConfig, LLMConfig
from prismthinker.core.disposition import drop_mismatched_claims, strip_unauthorized_vetoes
from prismthinker.core.engine import _sanitize_citations, materialize_hypothesis
from prismthinker.core.schemas import (
    ActionKind,
    Citation,
    CitationKind,
    Claim,
    EvidenceItem,
    FactSpec,
    FactType,
    FactValue,
    DeonticModality,
    EvaluatorCapability,
    EvaluatorPair,
    Hypothesis,
    IndependenceClass,
    PolicyRule,
    RuleSeverity,
    Verdict,
    BackendKind,
)
from prismthinker.reason_codes import (
    ALL_REASON_CODES,
    REASON_LLM_INVALID,
    REASON_POLARITY_MISMATCH,
    REASON_SELECTOR_INDEPENDENCE,
)
from prismthinker.evaluators.formal import FormalEvaluator
from tests.conftest import cache_ttl_context, result


FORBIDDEN = ("user", "persona", "history", "preference")


def test_reasoning_context_has_no_preference_fields() -> None:
    names = set(ReasoningContext.model_fields)
    blob = " ".join(names).lower()
    for word in FORBIDDEN:
        assert word not in blob


def test_evaluate_rejects_presentation_context(thinker: PrismThinker) -> None:
    with pytest.raises(TypeError):
        thinker.evaluate(PresentationContext(user_id="u1"))  # type: ignore[arg-type]


def test_conflict_preserves_both_states_and_null_recommendation(thinker: PrismThinker) -> None:
    ctx = cache_ttl_context()
    ctx.policy_rules[0] = PolicyRule(
        id="pii-cache",
        modality=DeonticModality.PROHIBITION,
        predicate="fact.contains_pii == true and fact.cache_ttl >= 30",
        severity=RuleSeverity.BLOCK,
        text="block not veto",
    )
    graph = thinker.evaluate(ctx)
    assert graph.recommended_verdict is None
    assert graph.disposition.value in {"conflict", "insufficient_evidence"}
    assert "policy" in graph.evaluators
    assert "utility" in graph.evaluators
    assert graph.evaluators["policy"].verdict is Verdict.REJECT
    assert graph.evaluators["utility"].verdict is Verdict.APPROVE


def test_unauthorized_veto_stripped() -> None:
    results = {
        "utility": result("utility", Verdict.REJECT, hard_veto=True),
        "formal": result("formal", Verdict.REJECT, hard_veto=True),
        "policy": result("policy", Verdict.REJECT, hard_veto=True),
    }
    caps = {
        "utility": EvaluatorCapability(
            name="utility",
            backend=BackendKind.RULES,
            independence_class=IndependenceClass.UTILITY_OBJECTIVE,
            may_hard_veto=False,
        ),
        "formal": EvaluatorCapability(
            name="formal",
            backend=BackendKind.SOLVER,
            independence_class=IndependenceClass.FORMAL_SYMBOLIC,
            may_hard_veto=False,
        ),
        "policy": EvaluatorCapability(
            name="policy",
            backend=BackendKind.RULES,
            independence_class=IndependenceClass.POLICY_DEONTIC,
            may_hard_veto=True,
        ),
    }
    cleaned, errors = strip_unauthorized_vetoes(results, caps)
    assert cleaned["utility"].hard_veto is False
    assert cleaned["formal"].hard_veto is False
    assert cleaned["policy"].hard_veto is True
    assert any(e.error_type == "unauthorized_veto" for e in errors)


def test_formal_ignores_policy_rules() -> None:
    ctx = cache_ttl_context()
    hyp = ctx.hypothesis
    assert hyp is not None
    formal = FormalEvaluator()
    first = formal.evaluate(ctx, hyp)
    ctx.policy_rules = []
    second = formal.evaluate(ctx, hyp)
    assert first.verdict == second.verdict
    assert first.hard_veto is False
    source = inspect.getsource(FormalEvaluator.evaluate)
    assert "policy_rules" not in source


def test_fast_path_cites_hypothesis(thinker: PrismThinker) -> None:
    graph = thinker.evaluate(ReasoningContext(query="2 + 2"))
    axiomatic = graph.evaluators["axiomatic"]
    assert axiomatic.claims
    kinds = {c.kind for claim in axiomatic.claims for c in claim.citations}
    assert CitationKind.HYPOTHESIS in kinds
    assert graph.fast_path is not None
    assert graph.fast_path.value == 4


def test_extra_forbid_rejects_user_id() -> None:
    with pytest.raises(ValidationError):
        ReasoningContext(query="q", user_id="u1")  # type: ignore[call-arg]


def test_materialized_hypothesis_is_assertion() -> None:
    hyp = materialize_hypothesis(ReasoningContext(query="is this true"))
    assert hyp.action is not None
    assert hyp.action.kind is ActionKind.ASSERTION


def test_timeout_head_stays_in_evaluators() -> None:
    class Slow:
        capability = FormalEvaluator.capability

        def evaluate(self, context, hypothesis):
            time.sleep(2)
            return FormalEvaluator().evaluate(context, hypothesis)

    thinker = PrismThinker(
        EngineConfig(head_timeout_ms=40, pool_budget_ms=80, isolate_heads=False)
    )
    thinker._registry["formal"] = Slow()
    graph = thinker.evaluate(ReasoningContext(query="hello there general case"))
    assert "formal" in graph.evaluators
    assert graph.evaluators["formal"].verdict is Verdict.UNDETERMINED
    assert any(err.error_type == "timeout" and err.evaluator == "formal" for err in graph.errors)


def test_selector_fail_closed_keeps_named_heads() -> None:
    graph = PrismThinker().evaluate(
        ReasoningContext(query="hello there general case", force_evaluators=["ghost"])
    )
    assert graph.disposition.value == "insufficient_evidence"
    assert REASON_SELECTOR_INDEPENDENCE in graph.review_reasons
    assert "ghost" in graph.evaluators
    assert graph.evaluators["ghost"].verdict is Verdict.UNDETERMINED


def test_llm_enabled_fails_closed() -> None:
    graph = PrismThinker(EngineConfig(llm=LLMConfig(enabled=True))).evaluate(
        ReasoningContext(query="hello there general case")
    )
    assert graph.disposition.value == "insufficient_evidence"
    assert REASON_LLM_INVALID in graph.review_reasons


def test_mismatched_claims_are_kept_and_tagged() -> None:
    seeded = result("formal", Verdict.APPROVE)
    seeded.claims = [
        Claim(
            id="bad",
            evaluator="formal",
            statement="nope",
            polarity=-1.0,
            confidence=1.0,
            citations=[Citation(kind=CitationKind.HYPOTHESIS, ref="h")],
            hypothesis_id="h",
        )
    ]
    out = drop_mismatched_claims({"formal": seeded})
    assert out["formal"].claims
    assert out["formal"].claims[0].id == "bad"
    assert REASON_POLARITY_MISMATCH in out["formal"].reason_codes


def test_reason_code_set_is_closed() -> None:
    assert "REASON_TYPE_VIOLATION" not in ALL_REASON_CODES
    assert "REASON_CONSTRAINT_VIOLATED" not in ALL_REASON_CODES


def test_sanitize_citations_drops_unknown_refs() -> None:
    hyp = materialize_hypothesis(ReasoningContext(query="q"))
    ctx = ReasoningContext(
        query="q",
        hypothesis=hyp,
        evidence=[EvidenceItem(id="e1", content="ok", source="s")],
        structured_facts={"cache_ttl": FactValue(key="cache_ttl", value=60)},
    )
    seeded = result("formal", Verdict.APPROVE)
    seeded.claims = [
        Claim(
            id="c1",
            evaluator="formal",
            statement="ok",
            polarity=1.0,
            confidence=1.0,
            citations=[
                Citation(kind=CitationKind.EVIDENCE, ref="e1"),
                Citation(kind=CitationKind.EVIDENCE, ref="ghost"),
                Citation(kind=CitationKind.FACT, ref="cache_ttl"),
                Citation(kind=CitationKind.FACT, ref="missing"),
                Citation(kind=CitationKind.HYPOTHESIS, ref=hyp.id),
                Citation(kind=CitationKind.HYPOTHESIS, ref="other"),
                Citation(kind=CitationKind.RULE, ref="no-such-rule"),
            ],
            hypothesis_id=hyp.id,
        )
    ]
    out = _sanitize_citations({"formal": seeded}, ctx, hyp)
    kept = {(c.kind, c.ref) for c in out["formal"].claims[0].citations}
    assert kept == {
        (CitationKind.EVIDENCE, "e1"),
        (CitationKind.FACT, "cache_ttl"),
        (CitationKind.HYPOTHESIS, hyp.id),
    }


def test_llm_config_nested_enabled_property() -> None:
    config = EngineConfig(llm=LLMConfig(enabled=True))
    assert config.llm.enabled is True
    assert config.llm_enabled is True


def test_engine_does_not_import_latent() -> None:
    import prismthinker.core.engine as engine

    source = inspect.getsource(engine)
    assert "experimental.latent" not in source
    assert "projections" not in source
    assert "steering" not in source


def test_engine_does_not_import_adapters() -> None:
    import prismthinker.core.engine as engine

    source = inspect.getsource(engine)
    assert "adapters" not in source
    assert "vectorprism" not in source
    assert "RetrievedDocument" not in source
    assert "from_documents" not in source


def test_engine_does_not_import_torch() -> None:
    import prismthinker.core.engine as engine

    source = inspect.getsource(engine)
    assert "torch" not in source
    assert "import numpy" not in source
    assert "import scipy" not in source


def test_core_never_imports_forbidden_runtime_deps() -> None:
    core_root = Path(__file__).resolve().parents[1] / "src" / "prismthinker" / "core"
    forbidden_roots = (
        "torch",
        "vectorprism",
        "chorusgraph",
        "qdrant",
        "qdrant_client",
        "faiss",
        "pinecone",
        "numpy",
        "scipy",
        "prismthinker.adapters",
        "prismthinker.experimental",
    )

    def banned(name: str) -> bool:
        return any(name == root or name.startswith(root + ".") for root in forbidden_roots)

    for path in core_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        hits = sorted(name for name in imported if banned(name))
        assert not hits, f"{path.name} imported {hits}"


def test_production_modules_do_not_import_latent() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "prismthinker"
    skip = root / "experimental"
    for path in root.rglob("*.py"):
        if skip in path.parents or path.parent == skip:
            continue
        source = path.read_text(encoding="utf-8")
        assert "experimental.latent" not in source
        assert "prismthinker.experimental" not in source


def test_thread_pool_workers_receive_deep_copies() -> None:
    class Mutator:
        capability = FormalEvaluator.capability

        def evaluate(self, context, hypothesis):
            time.sleep(0.05)
            context.structured_facts["n"].value = 999
            context.evidence.append(EvidenceItem(id="poison", content="x", source="mutator"))
            hypothesis.statement = "mutated"
            return FormalEvaluator().evaluate(context, hypothesis)

    hyp = Hypothesis(id="h1", statement="original")
    ctx = ReasoningContext(
        query="hello there general case",
        hypothesis=hyp,
        structured_facts={"n": FactValue(key="n", value=3)},
        fact_specs={"n": FactSpec(key="n", fact_type=FactType.INT, minimum=0, maximum=10)},
        evidence=[EvidenceItem(id="e1", content="ok", source="s")],
    )
    snapshot = ctx.model_dump()
    thinker = PrismThinker(EngineConfig(isolate_heads=False, head_timeout_ms=2000, pool_budget_ms=4000))
    thinker._registry["formal"] = Mutator()
    graph = thinker.evaluate(ctx)
    assert ctx.model_dump() == snapshot
    assert ctx.structured_facts["n"].value == 3
    assert ctx.hypothesis is not None
    assert ctx.hypothesis.statement == "original"
    assert all(item.id != "poison" for item in ctx.evidence)
    assert "formal" in graph.evaluators


def test_crash_message_is_single_line_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    class Boom:
        capability = FormalEvaluator.capability

        def evaluate(self, context, hypothesis):
            raise RuntimeError("unit boom")

    thinker = PrismThinker(EngineConfig(isolate_heads=False))
    thinker._registry["formal"] = Boom()
    with caplog.at_level("ERROR", logger="prismthinker"):
        graph = thinker.evaluate(ReasoningContext(query="hello there general case"))
    crash = next(err for err in graph.errors if err.evaluator == "formal" and err.error_type == "crash")
    assert crash.message == "RuntimeError: unit boom"
    assert "\n" not in crash.message
    assert "Traceback" not in crash.message
    assert 'File "' not in crash.message
    assert "unit boom" in caplog.text
    assert graph.evaluators["formal"].verdict is Verdict.UNDETERMINED
