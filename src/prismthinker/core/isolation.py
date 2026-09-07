"""Process isolation for evaluator heads. A timed-out worker is terminated."""

from __future__ import annotations

import time
from multiprocessing import Process, Queue
from queue import Empty
from typing import Any

from prismthinker.config import EngineConfig
from prismthinker.core.failures import crash_message
from prismthinker.core.schemas import EvaluatorResult, Hypothesis, ReasoningContext

HEAD_STARTUP_TIMEOUT_S = 20.0


def head_worker(
    name: str,
    context_data: dict[str, Any],
    hypothesis_data: dict[str, Any],
    config_data: dict[str, Any],
    out: Queue,
) -> None:
    from prismthinker.core.selector import build_registry

    try:
        context = ReasoningContext.model_validate(context_data)
        hypothesis = Hypothesis.model_validate(hypothesis_data)
        config = EngineConfig.model_validate(config_data)
        evaluator = build_registry(config)[name]
        out.put(("ready", None))
        result = evaluator.evaluate(context, hypothesis)
        out.put(("ok", result.model_dump(mode="json")))
    except Exception as exc:  # noqa: BLE001 — isolate worker crashes
        out.put(("crash", crash_message(exc, evaluator=name)))


def sleep_worker(seconds: float, out: Queue) -> None:
    time.sleep(seconds)
    out.put(("ok", seconds))


def terminate_process(process: Process) -> None:
    if not process.is_alive():
        return
    process.terminate()
    process.join(timeout=1.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=1.0)


def _queue_get(queue: Queue, timeout_s: float) -> tuple[str, Any] | None:
    try:
        return queue.get(timeout=max(0.0, timeout_s))
    except Empty:
        return None


def start_head_workers(
    names: list[str],
    context_data: dict[str, Any],
    hypothesis_data: dict[str, Any],
    config_data: dict[str, Any],
) -> list[tuple[str, Process, Queue]]:
    workers: list[tuple[str, Process, Queue]] = []
    for name in names:
        queue: Queue = Queue()
        process = Process(
            target=head_worker,
            args=(name, context_data, hypothesis_data, config_data, queue),
        )
        process.start()
        workers.append((name, process, queue))
    return workers


def wait_workers_ready(
    workers: list[tuple[str, Process, Queue]],
    timeout_s: float = HEAD_STARTUP_TIMEOUT_S,
) -> dict[str, str]:
    """Wait until each worker signals ready. Returns name → error for failures."""
    pending = {name for name, _, _ in workers}
    failures: dict[str, str] = {}
    deadline = time.perf_counter() + timeout_s
    while pending and time.perf_counter() < deadline:
        for name, process, queue in workers:
            if name not in pending:
                continue
            item = _queue_get(queue, 0.02)
            if item is None:
                if not process.is_alive():
                    pending.remove(name)
                    failures[name] = f"worker exited during startup ({process.exitcode})"
                continue
            status, payload = item
            pending.remove(name)
            if status != "ready":
                failures[name] = str(payload)
        if pending:
            time.sleep(0.01)
    for name, process, _queue in workers:
        if name in pending:
            terminate_process(process)
            failures[name] = "worker failed to start before startup timeout"
            pending.remove(name)
    return failures


def run_in_process(
    target,
    args: tuple,
    timeout_s: float,
) -> tuple[str, Any]:
    queue: Queue = Queue()
    process = Process(target=target, args=args + (queue,))
    process.start()
    process.join(timeout=max(0.0, timeout_s))
    if process.is_alive():
        terminate_process(process)
        return ("timeout", None)
    if process.exitcode not in (0, None) and queue.empty():
        return ("crash", f"exit {process.exitcode}")
    if queue.empty():
        return ("crash", "worker exited without a result")
    status, payload = queue.get()
    return (status, payload)


def run_head_isolated(
    name: str,
    context: ReasoningContext,
    hypothesis: Hypothesis,
    config: EngineConfig,
    timeout_s: float,
) -> tuple[str, EvaluatorResult | None, str]:
    workers = start_head_workers(
        [name],
        context.model_dump(mode="json"),
        hypothesis.model_dump(mode="json"),
        config.model_dump(mode="json"),
    )
    failures = wait_workers_ready(workers)
    if name in failures:
        _, process, _queue = workers[0]
        terminate_process(process)
        return ("crash", None, failures[name])
    _name, process, queue = workers[0]
    item = _queue_get(queue, timeout_s)
    if item is None:
        terminate_process(process)
        return ("timeout", None, "head timed out and worker was terminated")
    status, payload = item
    terminate_process(process)
    if status == "ok" and isinstance(payload, dict):
        return ("ok", EvaluatorResult.model_validate(payload), "")
    return ("crash", None, str(payload))
