from __future__ import annotations

from prismthinker.config import ClassifierFeatureConfig, EngineConfig
from prismthinker.core.schemas import FactType, ReasoningContext

POLICY_DOMAINS = frozenset({"legal", "security", "privacy", "healthcare", "finance"})
SLA_KEY_MARKERS = ("latency", "cost", "qps", "ttl")
EMPIRICAL_LEXEMES = ("p-value", "pvalue", "distribution", "posterior", "sample")
POLICY_LEXEMES = ("allow", "deny", "gdpr", "retention", "pii", "must not")
PRAGMATIC_LEXEMES = ("sla", "p99", "cache", "throughput", "budget")


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _has_numeric(context: ReasoningContext) -> bool:
    for item in context.structured_facts.values():
        if isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
            return True
    for spec in context.fact_specs.values():
        if spec.fact_type in {FactType.INT, FactType.FLOAT, FactType.DURATION_MS}:
            if spec.key in context.structured_facts:
                return True
    for ev in context.evidence:
        if ev.numeric_claims:
            return True
    return False


def _sla_like(context: ReasoningContext) -> bool:
    keys = list(context.structured_facts) + list(context.fact_specs)
    lowered = [k.lower() for k in keys]
    return any(any(m in key for m in SLA_KEY_MARKERS) for key in lowered)


def _lexeme_hit(text: str, lexemes: tuple[str, ...]) -> bool:
    blob = text.lower()
    return any(lex in blob for lex in lexemes)


def feature_scores(
    context: ReasoningContext,
    config: EngineConfig | ClassifierFeatureConfig | None = None,
) -> dict[str, float]:
    weights = config.classifier if isinstance(config, EngineConfig) else (config or ClassifierFeatureConfig())
    query = context.query
    empirical = 0.0
    policy = 0.0
    pragmatic = 0.0
    open_score = 0.0

    numeric = _has_numeric(context)
    if numeric:
        empirical += weights.numeric_empirical
        pragmatic += weights.numeric_pragmatic
    if context.causal_graph is not None:
        empirical += weights.graph_empirical
        pragmatic += weights.graph_pragmatic
    if context.objective is not None or _sla_like(context):
        pragmatic += weights.objective_pragmatic
    if context.policy_rules:
        policy += weights.policy_rules
    if context.domain and context.domain.lower() in POLICY_DOMAINS:
        policy += weights.policy_domain
    if _lexeme_hit(query, EMPIRICAL_LEXEMES):
        empirical += weights.lexeme_empirical
    if _lexeme_hit(query, POLICY_LEXEMES):
        policy += weights.lexeme_policy
    if _lexeme_hit(query, PRAGMATIC_LEXEMES):
        pragmatic += weights.lexeme_pragmatic

    families = 0
    if numeric or context.causal_graph is not None or _lexeme_hit(query, EMPIRICAL_LEXEMES):
        families += 1
    if context.policy_rules or (context.domain and context.domain.lower() in POLICY_DOMAINS) or _lexeme_hit(query, POLICY_LEXEMES):
        families += 1
    if context.objective is not None or _sla_like(context) or _lexeme_hit(query, PRAGMATIC_LEXEMES):
        families += 1

    present = sum(
        [
            bool(context.policy_rules),
            context.causal_graph is not None,
            context.objective is not None,
            numeric,
        ]
    )
    if present >= 2:
        open_score += weights.open_multi_present
    if len(query) > weights.long_query_chars and families >= 2:
        open_score += weights.open_long_query

    return {
        "empirical": _clip(empirical),
        "policy_normative": _clip(policy),
        "pragmatic_systems": _clip(pragmatic),
        "open_dialectic": _clip(open_score),
    }
