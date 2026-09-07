from __future__ import annotations

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import EvaluatorResult, ReasoningContext, Verdict


def uncertainty_score(
    results: dict[str, EvaluatorResult],
    context: ReasoningContext,
    config: EngineConfig,
) -> float:
    determined = [r for r in results.values() if r.verdict is not Verdict.UNDETERMINED]
    c_bar = (
        sum(r.confidence for r in determined) / len(determined) if determined else 0.0
    )

    cited: set[str] = set()
    for result in results.values():
        cited.update(result.supporting_evidence_ids)
        cited.update(result.contradicting_evidence_ids)
        for claim in result.claims:
            for citation in claim.citations:
                if citation.kind.value == "evidence":
                    cited.add(citation.ref)

    n_evidence = len(context.evidence)
    if n_evidence == 0:
        coverage = 1.0
    else:
        coverage = len(cited) / max(1, n_evidence)

    required = [s for s in context.fact_specs.values() if s.required]
    missing = sum(1 for spec in required if spec.key not in context.structured_facts)
    missing_ratio = missing / max(1, len(required)) if required else 0.0

    unresolved = sum(len(r.unresolved_questions) for r in results.values())
    n_tilde = min(1.0, unresolved / max(1, config.n_unresolved_cap))

    raw = (
        0.50 * (1.0 - c_bar)
        + 0.20 * (1.0 - coverage)
        + 0.20 * missing_ratio
        + 0.10 * n_tilde
    )
    return max(0.0, min(1.0, raw))
