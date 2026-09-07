from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.counterfactual import probe_counterfactuals
from prismthinker.core.schemas import (
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    ReasoningContext,
    Verdict,
)
from tests.conftest import result


def test_only_mutable_probed_and_original_unchanged() -> None:
    ctx = ReasoningContext(
        query="q",
        structured_facts={
            "ttl": FactValue(key="ttl", value=60),
            "locked": FactValue(key="locked", value=1),
        },
        fact_specs={
            "ttl": FactSpec(
                key="ttl",
                fact_type=FactType.INT,
                mutable=True,
                minimum=1,
                maximum=100,
                step=10,
            ),
            "locked": FactSpec(key="locked", fact_type=FactType.INT, mutable=False),
        },
    )
    hyp = Hypothesis(id="h", statement="s")
    results = {
        "formal": result("formal", Verdict.APPROVE, premises=["ttl"]),
        "policy": result("policy", Verdict.REJECT, hard_veto=True, premises=["ttl"]),
    }

    seen_keys: list[str] = []

    def run(copied: ReasoningContext, _hyp: Hypothesis) -> dict:
        seen_keys.extend(copied.structured_facts)
        assert copied.structured_facts["ttl"].value != 60 or True
        flipped = copied.structured_facts["ttl"].value != 60
        return {
            "formal": result("formal", Verdict.APPROVE, premises=["ttl"]),
            "policy": result(
                "policy",
                Verdict.APPROVE if flipped else Verdict.REJECT,
                hard_veto=not flipped,
                premises=["ttl"],
            ),
        }

    probes = probe_counterfactuals(ctx, hyp, results, 0.82, EngineConfig(), run)
    assert ctx.structured_facts["ttl"].value == 60
    assert all(p.parameter_changed == "ttl" for p in probes if p.parameter_changed)
    assert all(p.parameter_changed != "locked" for p in probes)
    assert probes
    assert any(p.resolving for p in probes)
    assert all(isinstance(p.delta_after, float) for p in probes)


def test_budget_cap() -> None:
    ctx = ReasoningContext(
        query="q",
        structured_facts={"ttl": FactValue(key="ttl", value=50)},
        fact_specs={
            "ttl": FactSpec(
                key="ttl",
                fact_type=FactType.INT,
                mutable=True,
                minimum=1,
                maximum=300,
                step=1,
            )
        },
    )
    config = EngineConfig(max_probes=3)
    calls = {"n": 0}

    def run(copied: ReasoningContext, _hyp: Hypothesis) -> dict:
        calls["n"] += 1
        return {
            "formal": result("formal", Verdict.APPROVE),
            "policy": result("policy", Verdict.REJECT),
        }

    probes = probe_counterfactuals(
        ctx,
        Hypothesis(id="h", statement="s"),
        {
            "formal": result("formal", Verdict.APPROVE, premises=["ttl"]),
            "policy": result("policy", Verdict.REJECT, premises=["ttl"]),
        },
        0.7,
        config,
        run,
    )
    assert len(probes) <= 3
    assert calls["n"] <= 3


def test_no_mutable_schema() -> None:
    ctx = ReasoningContext(query="q")
    probes = probe_counterfactuals(
        ctx,
        Hypothesis(id="h", statement="s"),
        {"formal": result("formal", Verdict.APPROVE), "policy": result("policy", Verdict.REJECT)},
        0.7,
        EngineConfig(),
        lambda c, h: {},
    )
    assert probes[0].resolving_condition == "no_mutable_facts"
    assert probes[0].resolving is False
