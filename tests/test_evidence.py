from __future__ import annotations

from datetime import datetime, timezone

from prismthinker.config import EngineConfig
from prismthinker.core.evidence import detect_evidence_conflicts
from prismthinker.core.schemas import EvidenceConflictType, EvidenceItem, ReasoningContext
from prismthinker.reason_codes import REASON_EVIDENCE_STALE, REASON_EVIDENCE_TEMPORAL


def test_numeric_mismatch_and_explicit_negation() -> None:
    ctx = ReasoningContext(
        query="q",
        evidence=[
            EvidenceItem(
                id="e1",
                content="a",
                source="s",
                trust=0.9,
                numeric_claims={"latency": 10.0},
            ),
            EvidenceItem(
                id="e2",
                content="b",
                source="t",
                trust=0.2,
                numeric_claims={"latency": 40.0},
                metadata={"negates_id": "e1"},
            ),
        ],
    )
    conflicts = detect_evidence_conflicts(ctx, EngineConfig())
    types = {c.conflict_type for c in conflicts}
    assert EvidenceConflictType.NUMERIC_MISMATCH in types
    assert EvidenceConflictType.EXPLICIT_NEGATION in types
    assert EvidenceConflictType.SOURCE_TRUST in types


def test_stale_same_source() -> None:
    ctx = ReasoningContext(
        query="q",
        evidence=[
            EvidenceItem(
                id="e1",
                content="old",
                source="metrics",
                freshness_hours=200.0,
            ),
            EvidenceItem(
                id="e2",
                content="new",
                source="metrics",
                freshness_hours=2.0,
            ),
        ],
    )
    conflicts = detect_evidence_conflicts(ctx, EngineConfig(stale_hours=168.0))
    stale = [c for c in conflicts if c.conflict_type is EvidenceConflictType.STALE]
    assert stale
    assert REASON_EVIDENCE_STALE in stale[0].reason_codes


def test_temporal_mismatch_on_shared_numeric() -> None:
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 8, tzinfo=timezone.utc)
    ctx = ReasoningContext(
        query="q",
        evidence=[
            EvidenceItem(
                id="e1",
                content="a",
                source="s",
                retrieved_at=older,
                numeric_claims={"latency": 10.0},
            ),
            EvidenceItem(
                id="e2",
                content="b",
                source="t",
                retrieved_at=newer,
                numeric_claims={"latency": 40.0},
            ),
        ],
    )
    conflicts = detect_evidence_conflicts(ctx, EngineConfig())
    types = {c.conflict_type for c in conflicts}
    assert EvidenceConflictType.NUMERIC_MISMATCH in types
    assert EvidenceConflictType.TEMPORAL in types
    temporal = [c for c in conflicts if c.conflict_type is EvidenceConflictType.TEMPORAL]
    assert REASON_EVIDENCE_TEMPORAL in temporal[0].reason_codes