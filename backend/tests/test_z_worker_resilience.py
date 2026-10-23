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

import logging
import os
import queue
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

# (module path, job function, queue attribute) for every patched service.
# generation_jobs is deliberately absent: amd-sync is editing its import block,
# so the same fix is recorded in docs/HANDOFF_AMD_R9700_LINUX.md. Adding
# ("app.services.generation_jobs", "_run_generation_job", "_job_queue") here is
# all that is needed once that lands.
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


@pytest.fixture
def service(monkeypatch):
    """Load a service with a private queue and a stand-in job function.

    The real queues are module-level, and other tests in the suite call
    enqueue_*, which starts the real daemon workers. Those threads stay alive
    and drain the same queue, so a test driving _worker_loop() directly races
    them: a real worker steals the None sentinel and the test's loop blocks on
    get() forever. That is not hypothetical -- it hung the full suite. Each
    test therefore gets its own queue.
    """
    def _install(path, fn_name, queue_name, job):
        mod = _load(path)
        q = queue.Queue()
        monkeypatch.setattr(mod, queue_name, q)
        monkeypatch.setattr(mod, fn_name, job)
        return mod, q
    return _install


def _raise(message="simulated unhandled failure"):
    def _job(job_id):
        raise RuntimeError(message)
    return _job


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_worker_survives_a_job_that_raises(path, fn_name, queue_name, service):
    attempted: list[str] = []

    def _job(job_id):
        attempted.append(job_id)
        if job_id == "bad":
            raise RuntimeError("simulated unhandled failure")

    mod, q = service(path, fn_name, queue_name, _job)
    q.put("bad")
    q.put("good")
    q.put(None)            # sentinel: ends the loop
    mod._worker_loop()     # must return normally, not propagate

    assert attempted == ["bad", "good"], (
        "the worker stopped after the failing job; queued work would be "
        f"stranded (attempted={attempted})")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_the_failure_is_logged_not_swallowed_silently(path, fn_name, queue_name,
                                                      service):
    """A handler on the module's own logger, not caplog.

    caplog captures through the root logger, so whether it sees anything
    depends on global logging state other tests can change -- this assertion
    passed in isolation and failed in the full run for exactly that reason.
    Attaching a handler directly to mod.logger, and neutralising the level and
    disable flags for the duration, makes it order-independent.
    """
    mod, q = service(path, fn_name, queue_name, _raise())
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture(level=logging.ERROR)
    prev_level, prev_disabled = mod.logger.level, mod.logger.disabled
    prev_manager = logging.root.manager.disable
    mod.logger.addHandler(handler)
    mod.logger.setLevel(logging.ERROR)
    mod.logger.disabled = False
    logging.disable(logging.NOTSET)
    try:
        q.put("bad")
        q.put(None)
        mod._worker_loop()
    finally:
        mod.logger.removeHandler(handler)
        mod.logger.setLevel(prev_level)
        mod.logger.disabled = prev_disabled
        logging.disable(prev_manager)

    assert any("bad" in r.getMessage() for r in records), (
        "a worker swallowing an exception without logging makes the next "
        f"failure undiagnosable (records={[r.getMessage() for r in records]})")
    assert any(r.exc_info for r in records), (
        "the traceback must be preserved; logger.exception, not logger.error")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_task_done_still_balances_the_queue(path, fn_name, queue_name, service):
    """`finally` must keep running, or `queue.join()` would hang forever."""
    mod, q = service(path, fn_name, queue_name, _raise())
    q.put("bad")
    q.put(None)
    mod._worker_loop()

    assert q.unfinished_tasks == 0, (
        "task_done() was not called for every get(); queue.join() would block")


@pytest.mark.parametrize("path,fn_name,queue_name", SERVICES)
def test_a_clean_job_is_unaffected(path, fn_name, queue_name, service):
    done: list[str] = []
    mod, q = service(path, fn_name, queue_name, done.append)
    q.put("ok")
    q.put(None)
    mod._worker_loop()

    assert done == ["ok"]
    assert q.unfinished_tasks == 0
