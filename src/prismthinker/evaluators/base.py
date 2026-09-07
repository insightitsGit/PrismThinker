from __future__ import annotations

from abc import ABC, abstractmethod

from prismthinker.core.schemas import (
    EvaluatorCapability,
    EvaluatorResult,
    Hypothesis,
    ReasoningContext,
)


class Evaluator(ABC):
    capability: EvaluatorCapability

    @abstractmethod
    def evaluate(self, context: ReasoningContext, hypothesis: Hypothesis) -> EvaluatorResult:
        """Pure. No I/O. Do not mutate context or hypothesis."""
