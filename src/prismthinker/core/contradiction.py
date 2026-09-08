from __future__ import annotations

from collections import defaultdict

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import (
    AssumptionAtom,
    ConflictComponent,
    ConstraintStatus,
    EvaluatorPair,
    EvaluatorResult,
    PairwiseDisagreement,
    Verdict,
    verdict_polarity,
)
from prismthinker.reason_codes import (
    REASON_ASSUMPTION_FLIP,
    REASON_INVERTED_CONSTRAINT,
    REASON_INVERTED_EVIDENCE,
    REASON_PAIR_BOTH_UNDETERMINED,
    REASON_PAIR_UNDETERMINED_SKIPPED,
)


def jaccard_distance(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return 1.0 - (len(left & right) / len(union))


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def _constraint_sets(result: EvaluatorResult) -> tuple[set[str], set[str]]:
    satisfied: set[str] = set()
    violated: set[str] = set()
    for item in result.constraints_applied:
        if item.status is ConstraintStatus.SATISFIED:
            satisfied.add(item.constraint_id)
        elif item.status is ConstraintStatus.VIOLATED:
            violated.add(item.constraint_id)
    return satisfied, violated


def pairwise_delta(
    left: EvaluatorResult,
    right: EvaluatorResult,
    config: EngineConfig,
) -> PairwiseDisagreement:
    codes: list[str] = []
    if left.verdict is Verdict.UNDETERMINED and right.verdict is Verdict.UNDETERMINED:
        return PairwiseDisagreement(
            pair=EvaluatorPair(left=left.evaluator, right=right.evaluator),
            delta=0.0,
            components=ConflictComponent(),
            reason_codes=[REASON_PAIR_BOTH_UNDETERMINED],
        )

    pi = verdict_polarity(left.verdict)
    pj = verdict_polarity(right.verdict)
    if pi is None or pj is None:
        c_conclusion = 0.0
        codes.append(REASON_PAIR_UNDETERMINED_SKIPPED)
    else:
        c_conclusion = 0.5 * abs(pi - pj)

    s_i, v_i = _constraint_sets(left)
    s_j, v_j = _constraint_sets(right)
    inverted = (s_i & v_j) | (s_j & v_i)
    applied = s_i | s_j | v_i | v_j
    c_constraint = 0.0 if not applied else len(inverted) / len(applied)
    if inverted:
        codes.append(REASON_INVERTED_CONSTRAINT)

    e_plus_i, e_minus_i = set(left.supporting_evidence_ids), set(left.contradicting_evidence_ids)
    e_plus_j, e_minus_j = set(right.supporting_evidence_ids), set(right.contradicting_evidence_ids)
    inv_e = (e_plus_i & e_minus_j) | (e_plus_j & e_minus_i)
    e_union = e_plus_i | e_plus_j | e_minus_i | e_minus_j
    c_evidence = _clip(
        0.6 * (len(inv_e) / max(1, len(e_union))) + 0.4 * jaccard_distance(e_plus_i, e_plus_j)
    )
    if inv_e:
        codes.append(REASON_INVERTED_EVIDENCE)

    pred_i = {a.predicate: a.polarity for a in left.assumptions}
    pred_j = {a.predicate: a.polarity for a in right.assumptions}
    shared = set(pred_i) & set(pred_j)
    if not shared:
        c_assumption = 0.0
    else:
        flips = [1.0 if pred_i[p] != pred_j[p] else 0.0 for p in shared]
        c_assumption = sum(flips) / len(flips)
        if any(flips):
            codes.append(REASON_ASSUMPTION_FLIP)

    c_premise = jaccard_distance(set(left.premise_ids), set(right.premise_ids))
    weights = config.contradiction
    delta = (
        weights.conclusion * c_conclusion
        + weights.constraint * c_constraint
        + weights.evidence * c_evidence
        + weights.assumption * c_assumption
        + weights.premise * c_premise
    )
    return PairwiseDisagreement(
        pair=EvaluatorPair(left=left.evaluator, right=right.evaluator),
        delta=_clip(delta),
        components=ConflictComponent(
            conclusion_conflict=_clip(c_conclusion),
            evidence_conflict=_clip(c_evidence),
            premise_conflict=_clip(c_premise),
            constraint_conflict=_clip(c_constraint),
            assumption_conflict=_clip(c_assumption),
        ),
        reason_codes=codes,
    )


def contradiction_matrix(
    results: dict[str, EvaluatorResult],
    config: EngineConfig,
) -> tuple[list[PairwiseDisagreement], float]:
    names = list(results)
    pairs: list[PairwiseDisagreement] = []
    deltas: list[float] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            left, right = results[a], results[b]
            item = pairwise_delta(left, right, config)
            pairs.append(item)
            both_undetermined = (
                left.verdict is Verdict.UNDETERMINED and right.verdict is Verdict.UNDETERMINED
            )
            if not both_undetermined:
                deltas.append(item.delta)
    delta_max = max(deltas) if deltas else 0.0
    return pairs, delta_max


def assumption_partition(
    results: dict[str, EvaluatorResult],
) -> tuple[list[AssumptionAtom], list[AssumptionAtom]]:
    determined = {
        name: res
        for name, res in results.items()
        if res.verdict is not Verdict.UNDETERMINED
    }
    by_pred: dict[str, list[AssumptionAtom]] = defaultdict(list)
    for res in determined.values():
        for atom in res.assumptions:
            by_pred[atom.predicate].append(atom)
    shared: list[AssumptionAtom] = []
    conflicting: list[AssumptionAtom] = []
    for predicate, atoms in by_pred.items():
        if len(atoms) < 2:
            continue
        polarities = {a.polarity for a in atoms}
        if len(polarities) == 1:
            shared.append(atoms[0])
        else:
            conflicting.extend(atoms)
    return shared, conflicting


def critical_pairs(
    pairs: list[PairwiseDisagreement],
    tau_base: float,
) -> list[PairwiseDisagreement]:
    # Match the lattice's documented strict threshold (Delta > tau).
    return [p for p in pairs if p.delta > tau_base]
