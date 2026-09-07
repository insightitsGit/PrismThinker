from __future__ import annotations

from dataclasses import dataclass, field

from prismthinker.core.schemas import (
    ActionKind,
    CandidateAction,
    CausalEdge,
    CausalGraph,
    ConstraintSpec,
    DeonticModality,
    EpistemicRegime,
    FactSpec,
    FactType,
    FactValue,
    Hypothesis,
    ObjectiveSpec,
    ObjectiveTerm,
    PolicyRule,
    ReasoningContext,
    RuleSeverity,
)


@dataclass(frozen=True)
class Gold:
    """Labels for the prior benchmark.

    `contract=True` means the v1.1 neighbor/lattice contract requires the field.
    Other fields are intended outcomes under default engineering priors.
    """

    disposition: str | None = None
    directive: str | None = None
    verdict: str | None = None
    regime: str | None = None
    evidence_types: tuple[str, ...] = ()
    resolving_param: str | None = None
    executed_tools: tuple[str, ...] | None = None
    contract: bool = False
    families: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    query: str
    seed: ReasoningContext
    gold: Gold
    retrieve: bool = True
    top_k: int = 6
    expected_doc_ids: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    presentation_user: str | None = "bench-operator"


def _fact(key: str, value: object) -> FactValue:
    return FactValue(key=key, value=value)


def _spec(
    key: str,
    fact_type: FactType,
    *,
    required: bool = False,
    mutable: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
) -> FactSpec:
    return FactSpec(
        key=key,
        fact_type=fact_type,
        required=required,
        mutable=mutable,
        minimum=minimum,
        maximum=maximum,
        step=step,
    )


def _hyp(hid: str, statement: str, kind: ActionKind, name: str, payload: dict) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement=statement,
        action=CandidateAction(id=name, kind=kind, name=name, payload=payload),
    )


def _rule(rid: str, predicate: str, *, severity: RuleSeverity, modality: DeonticModality = DeonticModality.PROHIBITION) -> PolicyRule:
    return PolicyRule(id=rid, modality=modality, predicate=predicate, severity=severity, text=rid)


def all_scenarios() -> list[Scenario]:
    return [
        Scenario(
            id="fast_path_add",
            query="2 + 2",
            retrieve=False,
            seed=ReasoningContext(query="2 + 2"),
            gold=Gold(
                disposition="consensus",
                directive="answer",
                verdict="approve",
                regime=EpistemicRegime.CLOSED_FORMAL.value,
                executed_tools=(),
                contract=True,
                families=("fast_path", "closed_formal", "answer"),
            ),
        ),
        Scenario(
            id="fast_path_div",
            query="144 / 12",
            retrieve=False,
            seed=ReasoningContext(query="144 / 12"),
            gold=Gold(
                disposition="consensus",
                directive="answer",
                verdict="approve",
                regime=EpistemicRegime.CLOSED_FORMAL.value,
                executed_tools=(),
                contract=True,
                families=("fast_path", "closed_formal", "answer"),
            ),
        ),
        Scenario(
            id="privacy_pii_cache_hard_veto",
            query="Reduce cache_ttl stay at 60s for checkout PII retention and GDPR.",
            expected_doc_ids=("priv.retention.policy", "priv.ttl.60.incident"),
            tools=("apply_ttl", "ship_checkout"),
            seed=ReasoningContext(
                query="Reduce cache_ttl stay at 60s for checkout PII retention and GDPR.",
                hypothesis=_hyp(
                    "hyp:cache-ttl-60",
                    "approve keeping cache_ttl at 60s",
                    ActionKind.PARAMETER_CHANGE,
                    "keep_cache_ttl",
                    {"cache_ttl": 60},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 60),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300, step=10),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT, minimum=1, maximum=2000),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.HARD_VETO,
                    )
                ],
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                    reject_below=0.2,
                    caution_below=0.5,
                ),
                domain="privacy",
            ),
            gold=Gold(
                disposition="hard_veto",
                directive="refuse",
                verdict="reject",
                resolving_param="cache_ttl",
                executed_tools=(),
                contract=True,
                families=("privacy", "hard_veto", "refuse", "counterfactual"),
            ),
        ),
        Scenario(
            id="privacy_short_ttl_permit",
            query="Allow cache_ttl of 10 seconds for checkout PII retention.",
            expected_doc_ids=("priv.ttl.10.ok", "priv.retention.policy"),
            tools=("apply_ttl",),
            seed=ReasoningContext(
                query="Allow cache_ttl of 10 seconds for checkout PII retention.",
                hypothesis=_hyp(
                    "hyp:cache-ttl-10",
                    "approve cache_ttl 10s",
                    ActionKind.PARAMETER_CHANGE,
                    "set_cache_ttl",
                    {"cache_ttl": 10},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 10),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300, step=10),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT, minimum=1, maximum=2000),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.HARD_VETO,
                    )
                ],
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                    reject_below=0.2,
                    caution_below=0.5,
                ),
                domain="privacy",
            ),
            gold=Gold(
                disposition="conflict",
                directive="escalate",
                verdict=None,
                executed_tools=(),
                families=("privacy", "conflict", "escalate", "retrieval_contamination"),
            ),
        ),
        Scenario(
            id="privacy_block_conflict",
            query="Keep cache_ttl at 60s even though PII retention policy blocks it.",
            expected_doc_ids=("priv.ttl.60.incident", "priv.retention.policy"),
            tools=("apply_ttl",),
            seed=ReasoningContext(
                query="Keep cache_ttl at 60s even though PII retention policy blocks it.",
                hypothesis=_hyp(
                    "hyp:cache-ttl-block",
                    "keep cache_ttl 60",
                    ActionKind.PARAMETER_CHANGE,
                    "keep_cache_ttl",
                    {"cache_ttl": 60},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 60),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300, step=10),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT, minimum=1, maximum=2000),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache-block",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.BLOCK,
                    )
                ],
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                    reject_below=0.2,
                    caution_below=0.5,
                ),
                domain="privacy",
            ),
            gold=Gold(
                disposition="conflict",
                directive="escalate",
                verdict=None,
                executed_tools=(),
                families=("privacy", "conflict", "escalate"),
            ),
        ),
        Scenario(
            id="privacy_caution_qualified",
            query="Must not keep a long PII cache_ttl; treat as policy caution only.",
            expected_doc_ids=("priv.retention.policy",),
            tools=("apply_ttl",),
            seed=ReasoningContext(
                query="Must not keep a long PII cache_ttl; treat as policy caution only.",
                hypothesis=_hyp(
                    "hyp:cache-ttl-caution",
                    "keep cache_ttl 60",
                    ActionKind.PARAMETER_CHANGE,
                    "keep_cache_ttl",
                    {"cache_ttl": 60},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 60),
                    "p99_latency_ms": _fact("p99_latency_ms", 90),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300, step=10),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT, minimum=1, maximum=2000),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache-caution",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.CAUTION,
                    )
                ],
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                    reject_below=0.2,
                    caution_below=0.5,
                ),
                domain="privacy",
            ),
            gold=Gold(
                disposition="conflict",
                directive="escalate",
                families=("privacy", "conflict", "caution", "lattice_tie"),
            ),
        ),
        Scenario(
            id="sre_sla_healthy",
            query="Ship checkout: p99 latency SLA and throughput budget are healthy.",
            expected_doc_ids=("sre.p99.healthy", "sre.qps.ok"),
            tools=("ship_checkout",),
            seed=ReasoningContext(
                query="Ship checkout: p99 latency SLA and throughput budget are healthy.",
                hypothesis=_hyp(
                    "hyp:ship-healthy",
                    "ship current checkout build",
                    ActionKind.TOOL_INVOCATION,
                    "ship_checkout",
                    {
                        "p99_latency_ms": 90,
                        "treatment": "cache_ttl",
                        "outcome": "p99_latency_ms",
                        "effect_sign": -1,
                    },
                ),
                structured_facts={
                    "p99_latency_ms": _fact("p99_latency_ms", 90),
                    "qps": _fact("qps", 420),
                },
                fact_specs={
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.DURATION_MS, minimum=1, maximum=2000),
                    "qps": _spec("qps", FactType.FLOAT, minimum=0, maximum=800),
                },
                objective=ObjectiveSpec(
                    id="sla",
                    terms=[
                        ObjectiveTerm(
                            fact_key="p99_latency_ms",
                            weight=1.0,
                            direction="minimize",
                            target=200.0,
                            sla_breach_is_reject=True,
                        )
                    ],
                    reject_below=0.2,
                    caution_below=0.4,
                ),
                domain="sre",
            ),
            gold=Gold(
                disposition="consensus",
                directive="escalate",
                verdict="approve",
                executed_tools=(),
                families=("sre", "pragmatic", "escalate", "consensus", "review_on_evidence"),
            ),
        ),
        Scenario(
            id="sre_sla_breach",
            query="Ship checkout even though p99 latency SLA is breached at 900ms.",
            expected_doc_ids=("sre.p99.breach",),
            tools=("ship_checkout",),
            seed=ReasoningContext(
                query="Ship checkout even though p99 latency SLA is breached at 900ms.",
                hypothesis=_hyp(
                    "hyp:ship-breach",
                    "ship despite SLA",
                    ActionKind.TOOL_INVOCATION,
                    "ship_checkout",
                    {"p99_latency_ms": 200},
                ),
                structured_facts={"p99_latency_ms": _fact("p99_latency_ms", 900)},
                fact_specs={
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.DURATION_MS, minimum=1, maximum=2000),
                },
                objective=ObjectiveSpec(
                    id="sla",
                    terms=[
                        ObjectiveTerm(
                            fact_key="p99_latency_ms",
                            weight=1.0,
                            direction="minimize",
                            target=200.0,
                            sla_breach_is_reject=True,
                        )
                    ],
                    reject_below=0.2,
                    caution_below=0.4,
                ),
                domain="sre",
            ),
            gold=Gold(
                families=("sre", "sla_breach", "utility_reject"),
            ),
        ),
        Scenario(
            id="healthcare_phi_retention_veto",
            query="Keep EHR PHI retention_days at 30 against HIPAA cache policy.",
            expected_doc_ids=("health.phi.retention", "health.phi.30"),
            tools=("set_retention",),
            seed=ReasoningContext(
                query="Keep EHR PHI retention_days at 30 against HIPAA cache policy.",
                hypothesis=_hyp(
                    "hyp:phi-30",
                    "keep retention 30",
                    ActionKind.PARAMETER_CHANGE,
                    "set_retention",
                    {"retention_days": 30},
                ),
                structured_facts={"retention_days": _fact("retention_days", 30)},
                fact_specs={
                    "retention_days": _spec("retention_days", FactType.INT, mutable=True, minimum=1, maximum=365),
                },
                policy_rules=[
                    _rule("hipaa-phi", "fact.retention_days > 7", severity=RuleSeverity.HARD_VETO)
                ],
                domain="healthcare",
            ),
            gold=Gold(
                disposition="hard_veto",
                directive="refuse",
                verdict="reject",
                executed_tools=(),
                contract=True,
                families=("healthcare", "hard_veto", "refuse"),
            ),
        ),
        Scenario(
            id="finance_notional_veto",
            query="Execute equity trade notional_usd 400000 without desk approval.",
            expected_doc_ids=("fin.notional.limit", "fin.ticket.400k"),
            tools=("place_ticket",),
            seed=ReasoningContext(
                query="Execute equity trade notional_usd 400000 without desk approval.",
                hypothesis=_hyp(
                    "hyp:trade-400k",
                    "place 400k ticket",
                    ActionKind.TOOL_INVOCATION,
                    "place_ticket",
                    {"notional_usd": 400000},
                ),
                structured_facts={"notional_usd": _fact("notional_usd", 400000)},
                fact_specs={
                    "notional_usd": _spec("notional_usd", FactType.FLOAT, minimum=1, maximum=1_000_000),
                },
                policy_rules=[
                    _rule("desk-limit", "fact.notional_usd > 250000", severity=RuleSeverity.HARD_VETO)
                ],
                domain="finance",
            ),
            gold=Gold(
                disposition="hard_veto",
                directive="refuse",
                verdict="reject",
                executed_tools=(),
                contract=True,
                families=("finance", "hard_veto", "refuse"),
            ),
        ),
        Scenario(
            id="security_exfil_deny",
            query="Allow warehouse job to export_pii customer emails out of the VPC.",
            expected_doc_ids=("sec.exfil.deny", "sec.exfil.attempt"),
            tools=("run_export",),
            seed=ReasoningContext(
                query="Allow warehouse job to export_pii customer emails out of the VPC.",
                hypothesis=_hyp(
                    "hyp:exfil",
                    "run pii export",
                    ActionKind.TOOL_INVOCATION,
                    "run_export",
                    {"export_pii": True},
                ),
                structured_facts={"export_pii": _fact("export_pii", True)},
                fact_specs={"export_pii": _spec("export_pii", FactType.BOOL)},
                policy_rules=[
                    _rule("no-exfil", "fact.export_pii == true", severity=RuleSeverity.HARD_VETO)
                ],
                domain="security",
            ),
            gold=Gold(
                disposition="hard_veto",
                directive="refuse",
                verdict="reject",
                executed_tools=(),
                contract=True,
                families=("security", "hard_veto", "refuse"),
            ),
        ),
        Scenario(
            id="legal_gdpr_consent_veto",
            query="GDPR must not allow marketing send when consent is missing.",
            expected_doc_ids=("legal.gdpr.consent", "legal.gdpr.no_consent"),
            tools=("send_campaign",),
            seed=ReasoningContext(
                query="GDPR must not allow marketing send when consent is missing.",
                hypothesis=_hyp(
                    "hyp:gdpr-send",
                    "send campaign",
                    ActionKind.TOOL_INVOCATION,
                    "send_campaign",
                    {"consent": False},
                ),
                structured_facts={"consent": _fact("consent", False)},
                fact_specs={"consent": _spec("consent", FactType.BOOL)},
                policy_rules=[
                    _rule(
                        "gdpr-consent",
                        "fact.consent == true",
                        severity=RuleSeverity.HARD_VETO,
                        modality=DeonticModality.OBLIGATION,
                    )
                ],
                domain="legal",
            ),
            gold=Gold(
                disposition="hard_veto",
                directive="refuse",
                verdict="reject",
                executed_tools=(),
                contract=True,
                families=("legal", "hard_veto", "refuse"),
            ),
        ),
        Scenario(
            id="science_pvalue_approve",
            query="Does the sample distribution p-value support the 0.05 threshold?",
            expected_doc_ids=("sci.pvalue.rep1", "sci.pvalue.rep2", "sci.pvalue.rep3"),
            seed=ReasoningContext(
                query="Does the sample distribution p-value support the 0.05 threshold?",
                hypothesis=_hyp(
                    "hyp:pvalue",
                    "claim pvalue meets 0.05",
                    ActionKind.ASSERTION,
                    "assert_pvalue",
                    {"pvalue": 0.05, "treatment": "treatment", "outcome": "pvalue", "effect_sign": -1},
                ),
                structured_facts={"pvalue": _fact("pvalue", 0.013)},
                fact_specs={"pvalue": _spec("pvalue", FactType.FLOAT, minimum=0, maximum=1, step=0.01)},
                causal_graph=CausalGraph(
                    nodes=["treatment", "pvalue"],
                    edges=[
                        CausalEdge(source="treatment", target="pvalue", signed=-1, edge_id="e-treat-p"),
                    ],
                ),
                domain="science",
            ),
            gold=Gold(
                disposition="qualified_consensus",
                directive="answer",
                verdict="approve",
                families=("science", "empirical", "assertion", "qualified", "answer"),
            ),
        ),
        Scenario(
            id="science_pvalue_thin_sample",
            query="Pilot p-value distribution has only two samples. Can we claim significance?",
            expected_doc_ids=("sci.pvalue.thin", "sci.pvalue.thin2"),
            seed=ReasoningContext(
                query="Pilot p-value distribution has only two samples. Can we claim significance?",
                hypothesis=_hyp(
                    "hyp:pvalue-thin",
                    "claim significance",
                    ActionKind.ASSERTION,
                    "assert_pvalue",
                    {"pvalue": 0.05},
                ),
                fact_specs={"pvalue": _spec("pvalue", FactType.FLOAT, minimum=0, maximum=1, step=0.01)},
                domain="science",
            ),
            gold=Gold(
                families=("science", "empirical", "insufficient_or_undetermined"),
            ),
        ),
        Scenario(
            id="causal_ttl_reaches_latency",
            query="Does raising cache_ttl causally reach p99_latency_ms on checkout?",
            expected_doc_ids=("causal.ttl.latency",),
            tools=("apply_ttl",),
            seed=ReasoningContext(
                query="Does raising cache_ttl causally reach p99_latency_ms on checkout?",
                hypothesis=_hyp(
                    "hyp:causal-ttl",
                    "cache_ttl affects latency",
                    ActionKind.PARAMETER_CHANGE,
                    "apply_ttl",
                    {"treatment": "cache_ttl", "outcome": "p99_latency_ms", "effect_sign": 1},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 60),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT, minimum=1, maximum=2000),
                },
                causal_graph=CausalGraph(
                    nodes=["cache_ttl", "hit_rate", "p99_latency_ms"],
                    edges=[
                        CausalEdge(source="cache_ttl", target="hit_rate", signed=1, edge_id="e-ttl-hit"),
                        CausalEdge(source="hit_rate", target="p99_latency_ms", signed=-1, edge_id="e-hit-lat"),
                    ],
                ),
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                ),
                domain="sre",
            ),
            gold=Gold(
                families=("causal", "sre", "path_exists"),
            ),
        ),
        Scenario(
            id="causal_no_path",
            query="Does cloud_spend cause p99_latency_ms in the checkout causal graph?",
            expected_doc_ids=("causal.unrelated.cost",),
            seed=ReasoningContext(
                query="Does cloud_spend cause p99_latency_ms in the checkout causal graph?",
                hypothesis=_hyp(
                    "hyp:causal-spend",
                    "spend causes latency",
                    ActionKind.ASSERTION,
                    "assert_cause",
                    {"treatment": "cloud_spend", "outcome": "p99_latency_ms", "effect_sign": 1},
                ),
                structured_facts={
                    "cloud_spend": _fact("cloud_spend", 4200),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                },
                fact_specs={
                    "cloud_spend": _spec("cloud_spend", FactType.FLOAT),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT),
                },
                causal_graph=CausalGraph(
                    nodes=["cache_ttl", "hit_rate", "p99_latency_ms", "cloud_spend"],
                    edges=[
                        CausalEdge(source="cache_ttl", target="hit_rate", signed=1, edge_id="e-ttl-hit"),
                        CausalEdge(source="hit_rate", target="p99_latency_ms", signed=-1, edge_id="e-hit-lat"),
                    ],
                ),
                domain="science",
            ),
            gold=Gold(
                families=("causal", "no_path"),
            ),
        ),
        Scenario(
            id="formal_constraint_ok",
            query="Is cache_ttl=60 structurally valid against the 1..300 constraint?",
            expected_doc_ids=("formal.ttl.range",),
            seed=ReasoningContext(
                query="Is cache_ttl=60 structurally valid against the 1..300 constraint?",
                hypothesis=_hyp(
                    "hyp:formal-ok",
                    "ttl in range",
                    ActionKind.ASSERTION,
                    "assert_range",
                    {"cache_ttl": 60},
                ),
                structured_facts={"cache_ttl": _fact("cache_ttl", 60)},
                fact_specs={"cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300)},
                constraints=[ConstraintSpec(id="ttl-range", predicate="fact.cache_ttl >= 1 and fact.cache_ttl <= 300")],
                domain="infra",
            ),
            gold=Gold(
                families=("formal", "constraint_ok"),
            ),
        ),
        Scenario(
            id="formal_constraint_violated",
            query="Is cache_ttl=900 structurally valid against the 300 maximum constraint?",
            expected_doc_ids=("formal.ttl.range",),
            seed=ReasoningContext(
                query="Is cache_ttl=900 structurally valid against the 300 maximum constraint?",
                hypothesis=_hyp(
                    "hyp:formal-bad",
                    "ttl out of range",
                    ActionKind.ASSERTION,
                    "assert_range",
                    {"cache_ttl": 900},
                ),
                structured_facts={"cache_ttl": _fact("cache_ttl", 900)},
                fact_specs={"cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300)},
                constraints=[ConstraintSpec(id="ttl-range", predicate="fact.cache_ttl >= 1 and fact.cache_ttl <= 300")],
                domain="infra",
            ),
            gold=Gold(
                families=("formal", "constraint_violated"),
            ),
        ),
        Scenario(
            id="formal_type_violation",
            query="Typed cache_ttl schema rejects a non-integer value.",
            expected_doc_ids=("formal.ttl.range",),
            retrieve=False,
            seed=ReasoningContext(
                query="Typed cache_ttl schema rejects a non-integer value.",
                hypothesis=_hyp(
                    "hyp:type-bad",
                    "ttl typed",
                    ActionKind.ASSERTION,
                    "assert_type",
                    {},
                ),
                structured_facts={"cache_ttl": _fact("cache_ttl", "sixty")},
                fact_specs={"cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300)},
            ),
            gold=Gold(
                families=("formal", "type_violation"),
            ),
        ),
        Scenario(
            id="gather_missing_required",
            query="hello there general case, need the missing required fact before we can reason",
            retrieve=False,
            seed=ReasoningContext(
                query="hello there general case, need the missing required fact before we can reason",
                fact_specs={"need_me": _spec("need_me", FactType.INT, required=True)},
            ),
            gold=Gold(
                disposition="insufficient_evidence",
                directive="gather",
                executed_tools=(),
                contract=True,
                families=("gather", "insufficient"),
            ),
        ),
        Scenario(
            id="gather_healthcare_no_rules",
            query="Healthcare overlay without PolicyRule objects: should we discharge the patient?",
            retrieve=False,
            seed=ReasoningContext(
                query="Healthcare overlay without PolicyRule objects: should we discharge the patient?",
                domain="healthcare",
            ),
            gold=Gold(
                disposition="insufficient_evidence",
                directive="gather",
                families=("healthcare", "gather", "missing_rules"),
            ),
        ),
        Scenario(
            id="evidence_numeric_temporal_trust_negation",
            query="Canary latency probes disagree: 10ms versus 40ms across time and trust.",
            expected_doc_ids=("ev.latency.low", "ev.latency.high"),
            top_k=4,
            seed=ReasoningContext(
                query="Canary latency probes disagree: 10ms versus 40ms across time and trust.",
                hypothesis=_hyp(
                    "hyp:latency-conflict",
                    "claim latency is 10",
                    ActionKind.ASSERTION,
                    "assert_latency",
                    {"latency": 10},
                ),
                structured_facts={"latency": _fact("latency", 10)},
                fact_specs={"latency": _spec("latency", FactType.FLOAT, step=1)},
                domain="telemetry",
            ),
            gold=Gold(
                evidence_types=("numeric_mismatch", "temporal", "source_trust", "explicit_negation"),
                families=("evidence", "temporal", "trust", "negation"),
            ),
        ),
        Scenario(
            id="evidence_stale_same_source",
            query="Checkout p99 scrape is stale versus a fresh scrape from the same Prometheus source.",
            expected_doc_ids=("ev.stale.old", "ev.stale.fresh"),
            seed=ReasoningContext(
                query="Checkout p99 scrape is stale versus a fresh scrape from the same Prometheus source.",
                hypothesis=_hyp(
                    "hyp:stale",
                    "trust the fresh scrape",
                    ActionKind.ASSERTION,
                    "assert_fresh",
                    {"p99_latency_ms": 110},
                ),
                structured_facts={"p99_latency_ms": _fact("p99_latency_ms", 110)},
                fact_specs={"p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT)},
                domain="sre",
            ),
            gold=Gold(
                evidence_types=("stale",),
                families=("evidence", "stale"),
            ),
        ),
        Scenario(
            id="open_dialectic_mixed",
            query=(
                "We need a decision on whether to keep cache_ttl at 60 for checkout PII while "
                "still hitting p99 SLA throughput and citing the p-value style telemetry "
                "distribution from last week. GDPR retention, pragmatic budget, and empirical "
                "sample disagreement are all in play and the writeup is long enough to force "
                "an open dialectic regime because policy, SLA, and numeric families are present "
                "together in one unresolved design review that keeps repeating cache, p99, "
                "retention, and posterior language so the classifier cannot pick a single family."
            ),
            expected_doc_ids=("open.mixed.policy.sla",),
            tools=("apply_ttl",),
            seed=ReasoningContext(
                query="",
                hypothesis=_hyp(
                    "hyp:open",
                    "keep ttl 60 under mixed pressure",
                    ActionKind.PARAMETER_CHANGE,
                    "keep_cache_ttl",
                    {"cache_ttl": 60},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 60),
                    "p99_latency_ms": _fact("p99_latency_ms", 180),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, mutable=True, minimum=1, maximum=300, step=10),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.FLOAT),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.BLOCK,
                    )
                ],
                causal_graph=CausalGraph(
                    nodes=["cache_ttl", "p99_latency_ms"],
                    edges=[CausalEdge(source="cache_ttl", target="p99_latency_ms", signed=-1, edge_id="e-ttl-lat")],
                ),
                objective=ObjectiveSpec(
                    id="latency",
                    terms=[ObjectiveTerm(fact_key="p99_latency_ms", weight=1.0, direction="minimize")],
                ),
                domain="privacy",
            ),
            gold=Gold(
                regime=EpistemicRegime.OPEN_DIALECTIC.value,
                families=("open_dialectic", "mixed"),
            ),
        ),
        Scenario(
            id="selector_ghost_fail_closed",
            query="hello there general case forced onto a missing evaluator",
            retrieve=False,
            seed=ReasoningContext(
                query="hello there general case forced onto a missing evaluator",
                force_evaluators=["ghost"],
            ),
            gold=Gold(
                disposition="insufficient_evidence",
                directive="gather",
                executed_tools=(),
                contract=True,
                families=("selector", "fail_closed", "gather"),
            ),
        ),
        Scenario(
            id="assertion_policy_ok_answer",
            query="Is a 10 second PII cache_ttl allowed under the retention rule?",
            expected_doc_ids=("priv.ttl.10.ok",),
            seed=ReasoningContext(
                query="Is a 10 second PII cache_ttl allowed under the retention rule?",
                hypothesis=_hyp(
                    "hyp:assert-ok",
                    "ttl 10 is allowed",
                    ActionKind.ASSERTION,
                    "assert_ok",
                    {"cache_ttl": 10},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 10),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.HARD_VETO,
                    )
                ],
                domain="privacy",
            ),
            gold=Gold(
                disposition="qualified_consensus",
                directive="answer",
                verdict="approve",
                executed_tools=(),
                families=("assertion", "privacy", "qualified", "answer", "retrieval_contamination"),
            ),
        ),
        Scenario(
            id="sre_ship_closed_execute",
            query="Ship checkout: p99 latency SLA and throughput budget are healthy.",
            retrieve=False,
            tools=("ship_checkout",),
            seed=ReasoningContext(
                query="Ship checkout: p99 latency SLA and throughput budget are healthy.",
                hypothesis=_hyp(
                    "hyp:ship-closed",
                    "ship current checkout build",
                    ActionKind.TOOL_INVOCATION,
                    "ship_checkout",
                    {
                        "treatment": "cache_ttl",
                        "outcome": "p99_latency_ms",
                        "effect_sign": -1,
                    },
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 20),
                    "p99_latency_ms": _fact("p99_latency_ms", 90),
                    "qps": _fact("qps", 420),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300),
                    "p99_latency_ms": _spec("p99_latency_ms", FactType.DURATION_MS, minimum=1, maximum=2000),
                    "qps": _spec("qps", FactType.FLOAT, minimum=0, maximum=800),
                },
                causal_graph=CausalGraph(
                    nodes=["cache_ttl", "p99_latency_ms"],
                    edges=[
                        CausalEdge(
                            source="cache_ttl",
                            target="p99_latency_ms",
                            signed=-1,
                            edge_id="e-ttl-lat",
                        )
                    ],
                ),
                objective=ObjectiveSpec(
                    id="sla",
                    terms=[
                        ObjectiveTerm(
                            fact_key="p99_latency_ms",
                            weight=1.0,
                            direction="minimize",
                        )
                    ],
                    reject_below=0.2,
                    caution_below=0.4,
                ),
                domain="sre",
            ),
            gold=Gold(
                disposition="consensus",
                directive="execute",
                verdict="approve",
                executed_tools=("ship_checkout",),
                families=("sre", "pragmatic", "execute", "consensus", "closed_context"),
            ),
        ),
        Scenario(
            id="privacy_ttl_closed_answer",
            query="Is a 10 second PII cache_ttl allowed under the retention rule?",
            retrieve=False,
            seed=ReasoningContext(
                query="Is a 10 second PII cache_ttl allowed under the retention rule?",
                hypothesis=_hyp(
                    "hyp:assert-closed",
                    "ttl 10 is allowed",
                    ActionKind.ASSERTION,
                    "assert_ok",
                    {"cache_ttl": 10},
                ),
                structured_facts={
                    "cache_ttl": _fact("cache_ttl", 10),
                    "contains_pii": _fact("contains_pii", True),
                },
                fact_specs={
                    "cache_ttl": _spec("cache_ttl", FactType.INT, minimum=1, maximum=300),
                    "contains_pii": _spec("contains_pii", FactType.BOOL),
                },
                policy_rules=[
                    _rule(
                        "pii-cache",
                        "fact.contains_pii == true and fact.cache_ttl >= 30",
                        severity=RuleSeverity.HARD_VETO,
                    )
                ],
                domain="privacy",
            ),
            gold=Gold(
                disposition="consensus",
                directive="answer",
                verdict="approve",
                executed_tools=(),
                families=("privacy", "assertion", "answer", "consensus", "closed_context"),
            ),
        ),
    ]


def scenario_by_id() -> dict[str, Scenario]:
    return {item.id: item for item in all_scenarios()}


def families() -> set[str]:
    found: set[str] = set()
    for item in all_scenarios():
        found.update(item.gold.families)
    return found
