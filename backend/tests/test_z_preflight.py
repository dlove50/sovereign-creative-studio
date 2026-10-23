"""Preflight: the port check is the reason this tool exists, so it is pinned hardest.

The studio went days without producing an image because the backend dialled
ComfyUI on 8001 while ComfyUI answered on 8188, and nothing said so. A check
that reported only "cannot connect" would have left that exactly as unresolved,
so the assertions below are about the tool naming *where the service actually
is* and *the line to change*, not merely that something is wrong.

Network probes are monkeypatched rather than bound. Binding real ports makes a
suite order-dependent and flaky on a busy machine -- and the machine this runs
on is the one with a wedged GPU and no free memory.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

_TOOL = Path(__file__).resolve().parent.parent.parent / "tools" / "preflight.py"


def _load():
    """Load tools/preflight.py by path; tools/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("preflight_tool", _TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = _load()


# --------------------------------------------------------------------------
# .env parsing -- must work with no dependencies, since a broken venv is one
# of the things this tool diagnoses
# --------------------------------------------------------------------------

def test_env_parsing_handles_the_shapes_a_real_file_has(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join([
            "# a comment",
            "",
            "COMFYUI_BASE_URL=http://127.0.0.1:8188",
            'QUOTED="http://example.test:1234"',
            "SINGLE='value'",
            "WITH_COMMENT=http://127.0.0.1:9000 # trailing note",
            "  SPACED  =  padded  ",
            "NOT_A_SETTING",
        ]),
        encoding="utf-8",
    )
    values = pf.read_env_file(env)

    assert values["COMFYUI_BASE_URL"] == "http://127.0.0.1:8188"
    assert values["QUOTED"] == "http://example.test:1234"
    assert values["SINGLE"] == "value"
    assert values["WITH_COMMENT"] == "http://127.0.0.1:9000", (
        "an inline comment ended up inside the URL")
    assert values["SPACED"] == "padded"
    assert "NOT_A_SETTING" not in values


def test_a_missing_env_file_is_not_an_error(tmp_path):
    assert pf.read_env_file(tmp_path / "nope.env") == {}


def test_process_environment_beats_the_env_file(monkeypatch):
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://127.0.0.1:7777")
    value, origin = pf.setting({"COMFYUI_BASE_URL": "http://127.0.0.1:8001"},
                               "COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    assert value == "http://127.0.0.1:7777"
    assert origin == "environment"


def test_the_env_file_beats_the_repo_default(monkeypatch):
    monkeypatch.delenv("COMFYUI_BASE_URL", raising=False)
    value, origin = pf.setting({"COMFYUI_BASE_URL": "http://127.0.0.1:8188"},
                               "COMFYUI_BASE_URL", "http://127.0.0.1:8001")
    assert value == "http://127.0.0.1:8188"
    assert origin == "backend/.env"


def test_an_empty_setting_falls_through_rather_than_winning(monkeypatch):
    """KEY= in a .env must not override the default with an empty string."""
    monkeypatch.delenv("COMFYUI_BASE_URL", raising=False)
    value, origin = pf.setting({"COMFYUI_BASE_URL": "   "},
                               "COMFYUI_BASE_URL", "http://127.0.0.1:8001")
    assert value == "http://127.0.0.1:8001"
    assert origin == "repo default"


# --------------------------------------------------------------------------
# URL splitting
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url,host,port", [
    ("http://127.0.0.1:8188", "127.0.0.1", 8188),
    ("http://127.0.0.1:8188/", "127.0.0.1", 8188),
    ("http://localhost:8001/prompt", "localhost", 8001),
    ("http://127.0.0.1", "127.0.0.1", 8001),          # no port -> default
    ("127.0.0.1:8188", "127.0.0.1", 8188),            # no scheme
    ("http://127.0.0.1:notaport", "127.0.0.1", 8001), # junk -> default
])
def test_host_and_port_are_split_from_the_shapes_people_write(url, host, port):
    assert pf.split_host_port(url, 8001) == (host, port)


# --------------------------------------------------------------------------
# The port check -- the whole point
# --------------------------------------------------------------------------

@pytest.fixture
def listening(monkeypatch):
    """Pretend exactly `ports` are open; nothing answers HTTP."""
    def _install(ports):
        monkeypatch.setattr(pf, "port_open",
                            lambda host, port, timeout=1.5: port in ports)
        monkeypatch.setattr(pf, "http_ok", lambda url, timeout=4.0: False)
    return _install


def test_the_real_blocker_is_diagnosed_with_the_exact_fix(listening):
    """Configured 8001, ComfyUI actually on 8188 -- David's situation."""
    listening({8188})
    report = pf.Report()
    pf.check_comfyui(report, {"COMFYUI_BASE_URL": "http://127.0.0.1:8001"})
    row = report.rows[0]

    assert row["status"] == pf.FAIL
    assert "8001" in row["detail"] and "8188" in row["detail"]
    assert row["fix"] == "set COMFYUI_BASE_URL=http://127.0.0.1:8188 in backend/.env", (
        "the fix must be a line the user can paste, not advice to investigate")
    assert report.blocked


def test_the_configured_port_answering_is_simply_ok(listening):
    listening({8001})
    report = pf.Report()
    pf.check_comfyui(report, {"COMFYUI_BASE_URL": "http://127.0.0.1:8001"})
    assert report.rows[0]["status"] == pf.OK
    assert not report.blocked


def test_nothing_anywhere_says_to_start_it_rather_than_guessing(listening):
    listening(set())
    report = pf.Report()
    pf.check_comfyui(report, {"COMFYUI_BASE_URL": "http://127.0.0.1:8001"})
    row = report.rows[0]

    assert row["status"] == pf.FAIL
    assert "start-comfyui-rocm.sh" in row["fix"]
    # Must not claim to have found it somewhere when it found nothing.
    assert "listening on" not in row["detail"]


def test_finding_it_on_the_backend_port_is_flagged_as_ambiguous(listening):
    """8000 is the backend's own port, so a hit there is probably not ComfyUI
    and must not be presented as the answer."""
    listening({8000})
    report = pf.Report()
    pf.check_comfyui(report, {"COMFYUI_BASE_URL": "http://127.0.0.1:8001"})
    detail = report.rows[0]["detail"]
    assert "backend's own port" in detail, (
        "a hit on 8000 was reported as ComfyUI with no caveat")


def test_an_http_answer_counts_even_when_the_socket_probe_would_not(monkeypatch):
    """A service behind a proxy may answer HTTP while a raw connect looks odd."""
    monkeypatch.setattr(pf, "http_ok", lambda url, timeout=4.0: True)
    monkeypatch.setattr(pf, "port_open", lambda h, p, timeout=1.5: False)
    report = pf.Report()
    pf.check_comfyui(report, {"COMFYUI_BASE_URL": "http://127.0.0.1:8001"})
    assert report.rows[0]["status"] == pf.OK


# --------------------------------------------------------------------------
# Other checks
# --------------------------------------------------------------------------

def test_an_unresolvable_workflow_path_blocks(monkeypatch, tmp_path):
    report = pf.Report()
    pf.check_workflows(report, {"COMFYUI_WORKFLOW_PATH": "workflows/not_here.json"})
    row = report.rows[0]
    assert row["status"] == pf.FAIL
    assert "not_here.json" in row["detail"]


def test_the_repo_default_workflows_do_resolve():
    """Guards against a rename breaking the default render path."""
    report = pf.Report()
    pf.check_workflows(report, {})
    assert report.rows[0]["status"] == pf.OK, report.rows[0]["detail"]


def test_a_models_dir_with_no_weights_blocks(tmp_path):
    report = pf.Report()
    pf.check_models_dir(report, tmp_path)
    assert report.rows[0]["status"] == pf.FAIL
    assert "no weight files" in report.rows[0]["detail"]


def test_a_models_dir_with_weights_reports_the_total(tmp_path):
    (tmp_path / "a.safetensors").write_bytes(b"x" * 2048)
    (tmp_path / "b.gguf").write_bytes(b"y" * 1024)
    (tmp_path / "readme.txt").write_text("ignored")
    report = pf.Report()
    pf.check_models_dir(report, tmp_path)
    assert report.rows[0]["status"] == pf.OK
    assert "2 weight file" in report.rows[0]["detail"]


def test_models_are_a_warning_when_not_requested():
    """Omitting --models-dir must not fail a preflight."""
    report = pf.Report()
    pf.check_models_dir(report, None)
    assert report.rows[0]["status"] == pf.WARN
    assert not report.blocked


def test_an_unwritable_storage_dir_blocks(tmp_path, monkeypatch):
    # This suite sets STORAGE_DIR in the process environment at import time,
    # and setting() correctly lets that win -- so it has to go for the passed
    # value to be the one under test.
    monkeypatch.delenv("STORAGE_DIR", raising=False)
    monkeypatch.setattr(pf.os, "access", lambda p, mode: False)
    report = pf.Report()
    pf.check_storage(report, {"STORAGE_DIR": str(tmp_path)})
    assert report.rows[0]["status"] == pf.FAIL


def test_a_writable_storage_dir_is_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("STORAGE_DIR", raising=False)
    report = pf.Report()
    pf.check_storage(report, {"STORAGE_DIR": str(tmp_path)})
    assert report.rows[0]["status"] == pf.OK


# --------------------------------------------------------------------------
# Exit contract: warnings must not fail a pre-render hook
# --------------------------------------------------------------------------

def test_only_failures_block():
    report = pf.Report()
    report.add(pf.OK, "a", "fine")
    report.add(pf.WARN, "b", "not ideal")
    assert not report.blocked
    report.add(pf.FAIL, "c", "broken")
    assert report.blocked


def test_the_tool_renders_without_raising(capsys):
    """print_human does its own column maths; an empty or ragged report must
    not traceback in front of someone already debugging something else."""
    report = pf.Report()
    report.print_human()
    report.add(pf.FAIL, "x", "detail", "a fix")
    report.add(pf.OK, "a much longer check name", "detail")
    report.print_human()
    assert "a fix" in capsys.readouterr().out
