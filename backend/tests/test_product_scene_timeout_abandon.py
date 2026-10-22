"""A timed-out ComfyUI prompt must be stopped, and stopped safely.

Before this, giving up on a slow render left it executing on the GPU with
nobody waiting for the result: it kept its VRAM while the next submission
stacked on top. On a machine already short of memory that compounds.

The safety constraint is the interesting part. ComfyUI's POST /interrupt takes
no prompt_id and cancels whatever is currently executing, so issuing it blindly
can kill an unrelated job. The adapter must therefore delete by id while the
prompt is pending, and interrupt only once /queue confirms the running prompt
is ours.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.product_scene_generators import comfyui as psc  # noqa: E402

PID = "pid-timeout"


class _Resp:
    def __init__(self, data=None, boom=False):
        self._data = data if data is not None else {}
        self._boom = boom

    def raise_for_status(self):
        if self._boom:
            raise RuntimeError("queue unavailable")

    def json(self):
        return self._data


class _Client:
    """Minimal ComfyUI stand-in that records every call."""

    def __init__(self, queue: dict | None = None, *, queue_fails: bool = False,
                 action_fails: bool = False):
        self.queue = queue if queue is not None else {"queue_running": [], "queue_pending": []}
        self.queue_fails = queue_fails
        self.action_fails = action_fails
        self.calls: list[tuple[str, str, object]] = []

    async def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        if url == "/queue":
            return _Resp(self.queue, boom=self.queue_fails)
        if url.startswith("/history/"):
            return _Resp({})           # never completes -> drives the timeout
        raise AssertionError(f"unexpected GET {url}")

    async def post(self, url, json=None, files=None, data=None):
        self.calls.append(("POST", url, json))
        if self.action_fails:
            raise RuntimeError("action refused")
        return _Resp({})

    def posted(self, url) -> bool:
        return any(c[0] == "POST" and c[1] == url for c in self.calls)


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    """Keep the real loop but make the timeout immediate."""
    monkeypatch.setattr(psc, "_POLL_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(psc, "_POLL_INTERVAL_SECONDS", 0)


def _adapter():
    return psc.ComfyUIProductSceneGenerator.__new__(psc.ComfyUIProductSceneGenerator)


def _timeout(client) -> str:
    with pytest.raises(TimeoutError) as exc:
        asyncio.run(_adapter()._await_outputs(client, PID))
    return str(exc.value)


def test_pending_prompt_is_deleted_by_id_not_interrupted():
    client = _Client({"queue_running": [], "queue_pending": [[1, PID, {}]]})
    msg = _timeout(client)
    assert client.posted("/queue"), "pending prompt was not removed"
    assert not client.posted("/interrupt"), "must not interrupt a pending prompt"
    delete = next(c for c in client.calls if c[1] == "/queue" and c[0] == "POST")
    assert delete[2] == {"delete": [PID]}
    assert "removed from the pending queue" in msg


def test_running_prompt_is_interrupted():
    client = _Client({"queue_running": [[1, PID, {}]], "queue_pending": []})
    msg = _timeout(client)
    assert client.posted("/interrupt")
    assert "interrupted while running" in msg


def test_someone_elses_running_job_is_never_interrupted():
    """The safety property. Our prompt is gone; another job is executing."""
    client = _Client({"queue_running": [[1, "someone-elses-prompt", {}]],
                      "queue_pending": [[2, "another-pending", {}]]})
    msg = _timeout(client)
    assert not client.posted("/interrupt"), (
        "interrupted a prompt that was not ours -- this would cancel an "
        "unrelated render")
    assert not client.posted("/queue"), "deleted a queue entry that was not ours"
    assert "no longer queued" in msg


def test_unreachable_queue_degrades_without_interrupting():
    client = _Client(queue_fails=True)
    msg = _timeout(client)
    assert not client.posted("/interrupt")
    assert "could not reach /queue" in msg


def test_malformed_queue_response_is_not_trusted():
    client = _Client()
    client.queue = ["not", "a", "dict"]
    msg = _timeout(client)
    assert not client.posted("/interrupt")
    assert "could not read /queue" in msg


def test_failed_cleanup_is_reported_not_swallowed():
    client = _Client({"queue_running": [[1, PID, {}]], "queue_pending": []},
                     action_fails=True)
    msg = _timeout(client)
    assert "interrupt failed" in msg, msg


def test_timeout_message_states_the_budget():
    client = _Client()
    msg = _timeout(client)
    assert "timed out after ~0s" in msg   # 2 attempts x 0s under the fixture
    assert PID in msg


def test_successful_render_never_touches_the_queue():
    """Cleanup must not fire on the happy path."""
    class _Done(_Client):
        async def get(self, url, params=None):
            self.calls.append(("GET", url, params))
            if url.startswith("/history/"):
                return _Resp({PID: {"outputs": {"9": {"images": [{"filename": "a.png"}]}}}})
            return await super().get(url, params)

    client = _Done()
    out = asyncio.run(_adapter()._await_outputs(client, PID))
    assert out == {"9": {"images": [{"filename": "a.png"}]}}
    assert not client.posted("/interrupt")
    assert not any(c[1] == "/queue" for c in client.calls)


@pytest.mark.parametrize("queue,expected", [
    ({"queue_pending": [[1, "a", {}]]}, {"a"}),
    ({"queue_pending": [{"prompt_id": "b"}]}, {"b"}),          # dict form
    ({"queue_pending": [[1]]}, set()),                          # too short
    ({"queue_pending": [[1, 42]]}, set()),                      # non-string id
    ({"queue_pending": None}, set()),
    ({}, set()),
])
def test_queue_parsing_tolerates_shape_variation(queue, expected):
    got = psc.ComfyUIProductSceneGenerator._queued_prompt_ids(queue, "queue_pending")
    assert got == expected


# --- transport failures must name the endpoint -------------------------------
#
# product_scene_jobs persists str(exc) as the job's error, so whatever these
# raise is what the operator reads in the UI. A bare httpx ConnectError says
# only "All connection attempts failed", which does not say which endpoint was
# tried -- unhelpful precisely when COMFYUI_BASE_URL is pointing at the wrong
# port, the live misconfiguration on AiServerR9700 (ComfyUI on 8188, default
# 8001).

import httpx  # noqa: E402


class _Boom:
    """A client whose every call raises the given transport error."""

    def __init__(self, exc):
        self.exc = exc

    async def get(self, url, params=None):
        raise self.exc

    async def post(self, url, json=None, files=None, data=None):
        raise self.exc


def _adapter_with_url(url="http://127.0.0.1:8001"):
    a = _adapter()
    a.base_url = url
    return a


def test_connect_error_names_the_base_url_the_operator_configured():
    a = _adapter_with_url()
    client = _Boom(httpx.ConnectError("All connection attempts failed"))
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(a._request(client.get, "/object_info"))
    msg = str(exc.value)
    assert "offline" in msg
    assert "http://127.0.0.1:8001" in msg, (
        "the message must name the endpoint; otherwise a wrong "
        "COMFYUI_BASE_URL is undiagnosable from the UI")
    assert msg != "All connection attempts failed"


def test_timeout_is_reported_as_a_timeout_not_an_offline_server():
    a = _adapter_with_url("http://127.0.0.1:8188")
    client = _Boom(httpx.ReadTimeout("timed out"))
    with pytest.raises(TimeoutError) as exc:
        asyncio.run(a._request(client.get, "/object_info"))
    msg = str(exc.value)
    assert "timed out" in msg and "http://127.0.0.1:8188" in msg
    assert "offline" not in msg, "a slow server is not an absent one"


def test_http_status_errors_surface_the_code_and_body():
    a = _adapter_with_url()

    class _Bad:
        async def post(self, url, json=None, files=None, data=None):
            request = httpx.Request("POST", "http://x/prompt")
            response = httpx.Response(500, text="workflow node missing",
                                      request=request)
            raise httpx.HTTPStatusError("boom", request=request,
                                        response=response)

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(a._request(_Bad().post, "/prompt", json={}))
    msg = str(exc.value)
    assert "HTTP 500" in msg
    assert "workflow node missing" in msg, "ComfyUI's own reason must survive"


def test_successful_request_returns_the_response_and_checks_status():
    a = _adapter_with_url()
    checked = []

    class _Ok:
        async def get(self, url, params=None):
            class _R:
                @staticmethod
                def raise_for_status():
                    checked.append(True)
            return _R()

    resp = asyncio.run(a._request(_Ok().get, "/object_info"))
    assert resp is not None
    assert checked == [True], "_request must still validate the status"
