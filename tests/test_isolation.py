from __future__ import annotations

import time
from multiprocessing import Process, Queue

from prismthinker.config import EngineConfig
from prismthinker.core.engine import materialize_hypothesis
from prismthinker.core.isolation import (
    _queue_get,
    head_worker,
    run_head_isolated,
    run_in_process,
    sleep_worker,
    start_head_workers,
    terminate_process,
    wait_workers_ready,
)
from prismthinker.core.schemas import ReasoningContext, Verdict


def _die_silent(out) -> None:
    return


def _ready_then_hang(out) -> None:
    out.put(("ready", None))
    time.sleep(30)


def _ready_then_crash(out) -> None:
    out.put(("ready", None))
    out.put(("crash", "unit boom"))


def _boom(out) -> None:
    raise RuntimeError("isolated boom")


def test_run_in_process_terminates_hung_worker() -> None:
    status, payload = run_in_process(sleep_worker, (30.0,), timeout_s=0.3)
    assert status == "timeout"
    assert payload is None


def test_run_in_process_returns_ok() -> None:
    status, payload = run_in_process(sleep_worker, (0.0,), timeout_s=5.0)
    assert status == "ok"
    assert payload == 0.0


def test_run_in_process_crash_on_empty_exit() -> None:
    status, payload = run_in_process(_die_silent, (), timeout_s=5.0)
    assert status == "crash"
    assert payload == "worker exited without a result"


def test_run_in_process_crash_on_uncaught() -> None:
    status, payload = run_in_process(_boom, (), timeout_s=5.0)
    assert status == "crash"


def test_isolated_standard_head_returns_result() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    status, result, message = run_head_isolated(
        "formal",
        context,
        hypothesis,
        EngineConfig(),
        15.0,
    )
    assert status == "ok"
    assert result is not None
    assert result.evaluator == "formal"
    assert result.verdict is not Verdict.UNDETERMINED or result.reason_codes
    assert message == ""


def test_isolated_unknown_head_crashes_at_startup() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    status, result, message = run_head_isolated(
        "not_a_head",
        context,
        hypothesis,
        EngineConfig(),
        15.0,
    )
    assert status == "crash"
    assert result is None
    assert message


def test_head_worker_puts_ok_in_process() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    queue: Queue = Queue()
    head_worker(
        "formal",
        context.model_dump(mode="json"),
        hypothesis.model_dump(mode="json"),
        EngineConfig().model_dump(mode="json"),
        queue,
    )
    status, payload = queue.get(timeout=5)
    assert status == "ready"
    status, payload = queue.get(timeout=5)
    assert status == "ok"
    assert isinstance(payload, dict)
    assert payload["evaluator"] == "formal"


def test_head_worker_puts_crash_for_unknown_head() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    queue: Queue = Queue()
    head_worker(
        "not_a_head",
        context.model_dump(mode="json"),
        hypothesis.model_dump(mode="json"),
        EngineConfig().model_dump(mode="json"),
        queue,
    )
    status, payload = queue.get(timeout=5)
    assert status == "crash"
    assert payload


def test_sleep_worker_puts_ok_in_process() -> None:
    queue: Queue = Queue()
    sleep_worker(0.0, queue)
    assert queue.get(timeout=1) == ("ok", 0.0)


def test_head_worker_puts_crash_for_invalid_context() -> None:
    queue: Queue = Queue()
    head_worker("formal", {"query": 1}, {"id": "h", "statement": "s"}, EngineConfig().model_dump(mode="json"), queue)
    status, payload = queue.get(timeout=5)
    assert status == "crash"
    assert "ValidationError" in str(payload) or "validation" in str(payload).lower() or payload


def test_terminate_process_on_dead_worker_is_noop() -> None:
    queue: Queue = Queue()
    process = Process(target=_die_silent, args=(queue,))
    process.start()
    process.join(timeout=5.0)
    terminate_process(process)
    assert not process.is_alive()


def test_wait_workers_ready_flags_non_ready_status() -> None:
    queue: Queue = Queue()
    process = Process(target=sleep_worker, args=(0.0, queue))
    process.start()
    try:
        failures = wait_workers_ready([("sleeper", process, queue)], timeout_s=5.0)
        assert "sleeper" in failures
    finally:
        terminate_process(process)


def test_wait_workers_ready_times_out_hung_startup() -> None:
    queue: Queue = Queue()
    process = Process(target=sleep_worker, args=(30.0, queue))
    process.start()
    try:
        failures = wait_workers_ready([("slow", process, queue)], timeout_s=0.25)
        assert failures["slow"] == "worker failed to start before startup timeout"
        assert not process.is_alive()
    finally:
        terminate_process(process)


def test_wait_workers_ready_skips_already_ready() -> None:
    ready_queue: Queue = Queue()
    slow_queue: Queue = Queue()
    ready_process = Process(target=_ready_then_hang, args=(ready_queue,))
    slow_process = Process(target=sleep_worker, args=(30.0, slow_queue))
    ready_process.start()
    slow_process.start()
    try:
        failures = wait_workers_ready(
            [("ready", ready_process, ready_queue), ("slow", slow_process, slow_queue)],
            timeout_s=0.4,
        )
        assert "slow" in failures
        assert "ready" not in failures
    finally:
        terminate_process(ready_process)
        terminate_process(slow_process)


def test_wait_workers_ready_flags_dead_process() -> None:
    queue: Queue = Queue()
    process = Process(target=_die_silent, args=(queue,))
    process.start()
    process.join(timeout=5.0)
    failures = wait_workers_ready([("dead", process, queue)], timeout_s=2.0)
    assert "dead" in failures
    assert "exited" in failures["dead"]


def test_queue_get_empty_is_none() -> None:
    queue: Queue = Queue()
    assert _queue_get(queue, 0.05) is None


def test_ready_then_hang_times_out_on_result() -> None:
    queue: Queue = Queue()
    process = Process(target=_ready_then_hang, args=(queue,))
    process.start()
    try:
        failures = wait_workers_ready([("hang", process, queue)], timeout_s=5.0)
        assert failures == {}
        assert _queue_get(queue, 0.2) is None
    finally:
        terminate_process(process)
        assert not process.is_alive()


def test_ready_then_crash_payload() -> None:
    queue: Queue = Queue()
    process = Process(target=_ready_then_crash, args=(queue,))
    process.start()
    try:
        failures = wait_workers_ready([("boom", process, queue)], timeout_s=5.0)
        assert failures == {}
        item = _queue_get(queue, 5.0)
        assert item == ("crash", "unit boom")
    finally:
        terminate_process(process)


def test_start_head_workers_formal_signals_ready() -> None:
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    workers = start_head_workers(
        ["formal"],
        context.model_dump(mode="json"),
        hypothesis.model_dump(mode="json"),
        EngineConfig().model_dump(mode="json"),
    )
    try:
        failures = wait_workers_ready(workers, timeout_s=15.0)
        assert failures == {}
        name, process, queue = workers[0]
        item = _queue_get(queue, 15.0)
        assert item is not None
        status, payload = item
        assert status == "ok"
        assert isinstance(payload, dict)
        assert name == "formal"
    finally:
        for _, process, _ in workers:
            terminate_process(process)


class _StubHungProcess:
    def __init__(self) -> None:
        self._alive = True
        self.kill_called = False

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        return

    def join(self, timeout: float | None = None) -> None:
        return

    def kill(self) -> None:
        self.kill_called = True
        self._alive = False


def test_terminate_process_kills_if_terminate_fails() -> None:
    process = _StubHungProcess()
    terminate_process(process)  # type: ignore[arg-type]
    assert process.kill_called
    assert not process.is_alive()


def test_run_head_isolated_times_out_waiting_for_result(monkeypatch) -> None:
    from prismthinker.core import isolation as iso

    real_get = iso._queue_get

    def gated(queue, timeout_s):
        if timeout_s >= 0.5:
            return None
        return real_get(queue, timeout_s)

    monkeypatch.setattr(iso, "_queue_get", gated)
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    status, result, message = run_head_isolated(
        "formal",
        context,
        hypothesis,
        EngineConfig(),
        15.0,
    )
    assert status == "timeout"
    assert result is None
    assert "timed out" in message


def test_run_head_isolated_crash_after_ready(monkeypatch) -> None:
    from prismthinker.core import isolation as iso

    real_get = iso._queue_get

    def gated(queue, timeout_s):
        if timeout_s >= 0.5:
            return ("crash", "post-ready boom")
        return real_get(queue, timeout_s)

    monkeypatch.setattr(iso, "_queue_get", gated)
    context = ReasoningContext(query="hello there general case")
    hypothesis = materialize_hypothesis(context)
    status, result, message = run_head_isolated(
        "formal",
        context,
        hypothesis,
        EngineConfig(),
        15.0,
    )
    assert status == "crash"
    assert result is None
    assert message == "post-ready boom"
