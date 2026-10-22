"""One bad job must not kill a worker thread.

Every in-process job service runs a single daemon worker draining a
module-level queue. The loop body used `try/finally` with no `except`, so an
exception escaping the job function propagated out of `while True` and killed
the thread -- silently, with nothing logged.

`_ensure_worker()` does check `is_alive()` and restarts on the next enqueue, so
this self-heals eventually. What it does not fix is the work already sitting in
the queue when the thread dies: those ids are stranded until something else is
enqueued. A SQLite "database is locked" during `db.commit()` is a realistic
trigger with seven worker threads and the API sharing one file.

These tests drive `_worker_loop` directly rather than through a thread: the
loop exits on the `None` sentinel, so feeding it [bad, good, None] and checking
both ids were attempted proves the loop survived the first one.
"""
from __future__ import annotations

import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

# (module path, job function, queue attribute) for every patched service.
# generation_jobs is deliberately absent: amd-sync is editing its import block,
# so the same fix is recorded in docs/HANDOFF_AMD_R9700_LINUX.md instead.
SERVICES = [
    ("app.services.asset_jobs", "_run_background_removal", "_asset_queue"),
    ("app.services.avatar_jobs", "_run_avatar_video", "_avatar_queue"),
    ("app.services.copy_jobs", "_run_copy", "_copy_queue"),
    ("app.services.product_scene_jobs", "_run_product_scene", "_scene_queue"),
    ("app.services.transcription", "_run", "_queue"),
    ("app.services.video_jobs", "_run_video", "_video_queue"),
]


def _load(path):
    __import__(path)
    return sys.modules[path]


@pytest.fixture(autouse=True)
def _drained_queues():
    """The queues are module-level, so state leaks between tests.

    A test whose worker loop dies mid-queue leaves items behind and the next
    test then sees them, which made these tests order-dependent. Drain before
    and after so each runs against an empty queue.
    """
    def drain():
        for path, _fn, queue_name in SERVICES:
            q = getattr(_load(path), queue_name)
            while True:
                try:
                    q.get_nowait()
                except Exception:   # queue.Empty
                    break
                else:
                    q.task_done()
    drain()
    yield
    drain()


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_worker_survives_a_job_that_raises(path, fn_name, queue_name, monkeypatch):
    mod = _load(path)
    q = getattr(mod, queue_name)
    attempted: list[str] = []

    def _fake(job_id):
        attempted.append(job_id)
        if job_id == "bad":
            raise RuntimeError("simulated unhandled failure")

    monkeypatch.setattr(mod, fn_name, _fake)

    q.put("bad")
    q.put("good")
    q.put(None)            # sentinel: ends the loop
    mod._worker_loop()     # must return normally, not propagate

    assert attempted == ["bad", "good"], (
        "the worker stopped after the failing job; queued work would be "
        f"stranded (attempted={attempted})")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_the_failure_is_logged_not_swallowed_silently(path, fn_name, queue_name,
                                                      monkeypatch, caplog):
    mod = _load(path)
    q = getattr(mod, queue_name)

    def _boom(job_id):
        raise RuntimeError("simulated unhandled failure")

    monkeypatch.setattr(mod, fn_name, _boom)

    q.put("bad")
    q.put(None)
    with caplog.at_level("ERROR"):
        mod._worker_loop()

    assert any("bad" in r.getMessage() for r in caplog.records), (
        "a worker swallowing an exception without logging makes the next "
        "failure undiagnosable")
    assert any(r.exc_info for r in caplog.records), (
        "the traceback must be preserved; logger.exception, not logger.error")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_task_done_still_balances_the_queue(path, fn_name, queue_name, monkeypatch):
    """`finally` must keep running, or `queue.join()` would hang forever."""
    mod = _load(path)
    q = getattr(mod, queue_name)

    monkeypatch.setattr(mod, fn_name,
                        lambda job_id: (_ for _ in ()).throw(RuntimeError("x")))
    q.put("bad")
    q.put(None)
    mod._worker_loop()

    assert q.unfinished_tasks == 0, (
        "task_done() was not called for every get(); queue.join() would block")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_a_clean_job_is_unaffected(path, fn_name, queue_name, monkeypatch):
    mod = _load(path)
    q = getattr(mod, queue_name)
    done: list[str] = []
    monkeypatch.setattr(mod, fn_name, done.append)

    q.put("ok")
    q.put(None)
    mod._worker_loop()

    assert done == ["ok"]
    assert q.unfinished_tasks == 0
