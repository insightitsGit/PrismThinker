"""Crash reporting for DecisionGraph.errors. Never put a traceback in the graph."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger("prismthinker")
MAX_CRASH_MESSAGE = 512


def crash_message(exc: BaseException, *, evaluator: str | None = None) -> str:
    """Log the full traceback; return a single-line summary for EvaluatorError.message."""
    extra = f" '{evaluator}'" if evaluator else ""
    LOGGER.exception("Evaluator%s crashed during execution.", extra)
    text = f"{type(exc).__name__}: {exc}".replace("\n", " ").strip()
    if len(text) > MAX_CRASH_MESSAGE:
        return text[: MAX_CRASH_MESSAGE - 3] + "..."
    return text
