from __future__ import annotations

from datetime import datetime, timezone

from prismthinker.config import EngineConfig
from prismthinker.core.schemas import (
    EvidenceConflict,
    EvidenceConflictType,
    ReasoningContext,
)
from prismthinker.reason_codes import (
    REASON_EVIDENCE_NEGATION,
    REASON_EVIDENCE_NUMERIC_MISMATCH,
    REASON_EVIDENCE_STALE,
    REASON_EVIDENCE_TEMPORAL,
    REASON_EVIDENCE_TRUST,
)


def _hours_old(item, now: datetime, stale_hours: float) -> bool:
    if item.freshness_hours is not None:
        return item.freshness_hours > stale_hours
    if item.retrieved_at is None:
        return False
    retrieved = item.retrieved_at
    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=timezone.utc)
    age = (now - retrieved).total_seconds() / 3600.0
    return age > stale_hours


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _numeric_mismatch(left, right, key: str, context: ReasoningContext) -> tuple[bool, float]:
    a = float(left.numeric_claims[key])
    b = float(right.numeric_claims[key])
    denom = max(abs(a), abs(b), 1e-12)
    rel = abs(a - b) / denom
    spec = context.fact_specs.get(key)
    step = spec.step if spec is not None else None
    mismatched = rel > 0.10
    if step is not None:
        mismatched = mismatched or abs(a - b) > step
    return mismatched, rel


def detect_evidence_conflicts(
    context: ReasoningContext,
    config: EngineConfig,
) -> list[EvidenceConflict]:
    items = context.evidence
    now = datetime.now(timezone.utc)
    conflicts: list[EvidenceConflict] = []
    for i, left in enumerate(items):
        for right in items[i + 1 :]:
            shared = set(left.numeric_claims) & set(right.numeric_claims)
            left_at = _aware(left.retrieved_at)
            right_at = _aware(right.retrieved_at)
            for key in shared:
                mismatched, rel = _numeric_mismatch(left, right, key, context)
                if mismatched:
                    conflicts.append(
                        EvidenceConflict(
                            left_id=left.id,
                            right_id=right.id,
                            conflict_type=EvidenceConflictType.NUMERIC_MISMATCH,
                            severity=min(1.0, rel / 0.5),
                            reason_codes=[REASON_EVIDENCE_NUMERIC_MISMATCH],
                            detail=f"{key}: {left.numeric_claims[key]} vs {right.numeric_claims[key]}",
                        )
                    )
                    if abs(left.trust - right.trust) >= 0.5:
                        conflicts.append(
                            EvidenceConflict(
                                left_id=left.id,
                                right_id=right.id,
                                conflict_type=EvidenceConflictType.SOURCE_TRUST,
                                severity=0.5,
                                reason_codes=[REASON_EVIDENCE_TRUST],
                                detail=f"trust {left.trust} vs {right.trust} on {key}",
                            )
                        )
                    if left_at is not None and right_at is not None and left_at != right_at:
                        hours = abs((left_at - right_at).total_seconds()) / 3600.0
                        conflicts.append(
                            EvidenceConflict(
                                left_id=left.id,
                                right_id=right.id,
                                conflict_type=EvidenceConflictType.TEMPORAL,
                                severity=min(1.0, hours / max(config.stale_hours, 1e-9)),
                                reason_codes=[REASON_EVIDENCE_TEMPORAL],
                                detail=f"{key} changed between {left_at.isoformat()} and {right_at.isoformat()}",
                            )
                        )
            left_old = _hours_old(left, now, config.stale_hours)
            right_old = _hours_old(right, now, config.stale_hours)
            same_family = left.source == right.source
            if same_family and (left_old ^ right_old):
                conflicts.append(
                    EvidenceConflict(
                        left_id=left.id,
                        right_id=right.id,
                        conflict_type=EvidenceConflictType.STALE,
                        severity=0.4,
                        reason_codes=[REASON_EVIDENCE_STALE],
                        detail="stale vs newer item on same source",
                    )
                )
            if left.metadata.get("negates_id") == right.id or right.metadata.get("negates_id") == left.id:
                conflicts.append(
                    EvidenceConflict(
                        left_id=left.id,
                        right_id=right.id,
                        conflict_type=EvidenceConflictType.EXPLICIT_NEGATION,
                        severity=1.0,
                        reason_codes=[REASON_EVIDENCE_NEGATION],
                        detail="explicit negation",
                    )
                )
    return conflicts
