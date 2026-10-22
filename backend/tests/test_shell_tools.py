"""Tests for the shell tools in tools/.

These were verified by hand when written, but none of that was committed, so a
regression would be silent. The two behaviours worth pinning are the ones that
were bugs:

* `start-sovereign-linux.sh` reported a serving frontend as "not running"
  because `port_pids()` relied on lsof, which cannot see Next.js's listening
  socket in some containers. The detector now falls back to fuser, and `stop`
  depends on that working.
* `diagnose-svm-oom.sh` had no timeout guards, so `rocminfo` opening /dev/kfd
  on a wedged GPU would hang the whole report -- in exactly the situation the
  report exists for.

Each test runs the real script with a stub directory prepended to PATH, so the
script's own logic is exercised rather than mocked.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
LAUNCHER = TOOLS / "start-sovereign-linux.sh"
DIAGNOSTIC = TOOLS / "diagnose-svm-oom.sh"

pytestmark = pytest.mark.skipif(
    not shutil.which("bash"), reason="bash is required to drive these scripts")


def stub(bindir: Path, name: str, body: str) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(0o755)


def run(script: Path, args: list[str], bindir: Path | None = None,
        env: dict | None = None, timeout: int = 120):
    e = dict(os.environ)
    if bindir:
        e["PATH"] = f"{bindir}:{e['PATH']}"
    e.update(env or {})
    return subprocess.run(["bash", str(script), *args], capture_output=True,
                          text=True, timeout=timeout, env=e,
                          cwd=str(TOOLS.parent))


# --- start-sovereign-linux.sh ------------------------------------------------

def test_launcher_prints_usage_and_exits_2_with_no_args():
    r = run(LAUNCHER, [])
    assert r.returncode == 2
    assert "usage:" in r.stderr
    assert "start" in r.stderr and "stop" in r.stderr and "status" in r.stderr


def test_launcher_rejects_an_unknown_start_option():
    r = run(LAUNCHER, ["start", "--definitely-not-an-option"])
    assert r.returncode == 1
    assert "unknown option" in r.stderr


def test_launcher_status_reports_nothing_running(tmp_path):
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")
    stub(bindir, "fuser", "exit 1")
    stub(bindir, "curl", "echo 000; exit 0")
    r = run(LAUNCHER, ["status"], bindir)
    assert r.returncode == 0
    assert r.stdout.count("not responding") == 3, r.stdout


def test_launcher_finds_a_listener_when_lsof_is_blind_but_fuser_is_not(tmp_path):
    """The regression. lsof sees nothing; the PID must still be found."""
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")                       # blind, as in the bug
    stub(bindir, "fuser", 'echo "$2/tcp:" >&2; echo "  4242"; exit 0')
    stub(bindir, "curl", "echo 000; exit 0")
    r = run(LAUNCHER, ["status"], bindir)
    assert r.returncode == 0
    assert "4242" in r.stdout, (
        "fuser fallback did not run; a serving process would read as down\n"
        + r.stdout)


def test_launcher_status_health_is_independent_of_pid_lookup(tmp_path):
    """A service answering HTTP must read as serving even with no PID found."""
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")
    stub(bindir, "fuser", "exit 1")
    stub(bindir, "curl", "echo 200; exit 0")
    r = run(LAUNCHER, ["status"], bindir)
    assert "serving" in r.stdout
    assert "not responding" not in r.stdout, r.stdout


def test_launcher_stop_is_quiet_when_nothing_is_running(tmp_path):
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")
    stub(bindir, "fuser", "exit 1")
    stub(bindir, "curl", "echo 000; exit 0")
    r = run(LAUNCHER, ["stop"], bindir)
    assert r.returncode == 0
    assert "Nothing was running" in r.stdout


def test_launcher_stop_reaches_a_pid_only_the_fallback_can_see(tmp_path):
    """stop uses the same detector, so the fuser fallback must feed it.

    `kill` is a shell builtin, so it cannot be stubbed via PATH; the assertion
    is on the script naming the PID it is about to signal, which is what proves
    the detector reached stop at all.
    """
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")
    state = tmp_path / "seen"
    # Report the PID once, then nothing, so the port reads as released.
    stub(bindir, "fuser",
         f'if [ -f {state} ]; then exit 1; fi; : > {state};'
         f' echo "$2/tcp:" >&2; echo "  4242"; exit 0')
    stub(bindir, "curl", "echo 000; exit 0")
    r = run(LAUNCHER, ["stop"], bindir)
    assert r.returncode == 0
    assert "Stopping" in r.stdout
    assert "4242" in r.stdout, r.stdout
    assert "Nothing was running" not in r.stdout


def test_launcher_start_refuses_without_a_backend_venv(tmp_path):
    """Preflight must stop before serving anything.

    The script derives its paths from its own location, so this copies it into
    a bare tree where backend/.venv does not exist. Running the in-repo copy
    would find the real venv and genuinely try to boot a backend.
    """
    fake = tmp_path / "repo" / "tools"
    fake.mkdir(parents=True)
    shutil.copy2(LAUNCHER, fake / LAUNCHER.name)
    bindir = tmp_path / "bin"
    stub(bindir, "lsof", "exit 1")
    stub(bindir, "fuser", "exit 1")
    stub(bindir, "curl", "echo 000; exit 0")
    r = run(fake / LAUNCHER.name, ["start", "--skip-comfy"], bindir,
            env={"SOVEREIGN_LOG_DIR": str(tmp_path / "logs")}, timeout=60)
    assert r.returncode == 1
    assert "backend venv missing" in r.stderr, r.stderr
    # It must not have reached any service-start step.
    assert "[2/3]" not in r.stdout and "[3/3]" not in r.stdout


# --- diagnose-svm-oom.sh -----------------------------------------------------

EXPECTED_SECTIONS = [
    "WHEN AND WHERE", "MEMORY NOW", "ACTIVE CGROUP MEMORY LIMITS",
    "USER SLICE TREE LIMITS", "WHAT LAUNCHES COMFYUI IN A TRANSIENT SCOPE",
    "WHERE A 22 GiB CAP COULD COME FROM", "OOM EVENTS",
    "SVM RESTORE LOOP", "IS THE LOOP ACTIVE RIGHT NOW?", "GPU STATE",
    "END OF REPORT",
]


def test_diagnostic_completes_without_sudo_and_emits_every_section():
    r = run(DIAGNOSTIC, [], env={"SKIP_SUDO": "1", "SAMPLE_SECONDS": "0"})
    assert r.returncode == 0, r.stderr
    for section in EXPECTED_SECTIONS:
        assert section in r.stdout, f"missing section: {section}"
    # Sudo-dependent sections must degrade to a note, not vanish or crash.
    assert "skipped - needs sudo" in r.stdout


def test_diagnostic_does_not_hang_on_a_wedged_gpu(tmp_path):
    """The regression. rocminfo opening /dev/kfd must not stall the report."""
    bindir = tmp_path / "bin"
    stub(bindir, "rocminfo", "sleep 600")
    stub(bindir, "rocm-smi", "sleep 600")
    r = run(DIAGNOSTIC, [], bindir,
            env={"SKIP_SUDO": "1", "SAMPLE_SECONDS": "0",
                 "GPU_QUERY_TIMEOUT": "2"},
            timeout=90)
    assert r.returncode == 0
    assert "END OF REPORT" in r.stdout, "script did not finish"
    assert "rocm-smi TIMED OUT" in r.stdout
    assert "rocminfo TIMED OUT" in r.stdout
    assert "GPU is wedged" in r.stdout


def test_diagnostic_reports_a_responsive_gpu_normally(tmp_path):
    bindir = tmp_path / "bin"
    stub(bindir, "rocm-smi", 'echo "GPU[0] : Card series: Radeon AI PRO R9700"; exit 0')
    stub(bindir, "rocminfo", 'echo "  Name:                    gfx1201"; exit 0')
    r = run(DIAGNOSTIC, [], bindir,
            env={"SKIP_SUDO": "1", "SAMPLE_SECONDS": "0",
                 "GPU_QUERY_TIMEOUT": "10"})
    assert r.returncode == 0
    assert "TIMED OUT" not in r.stdout
    assert "gfx1201" in r.stdout


def test_diagnostic_closing_advice_warns_against_raising_the_cap():
    """The one conclusion that must survive edits to this script."""
    r = run(DIAGNOSTIC, [], env={"SKIP_SUDO": "1", "SAMPLE_SECONDS": "0"})
    assert "Do NOT raise the cgroup memory cap" in r.stdout
    assert "same size" in r.stdout


# --- start-comfyui-rocm.sh ---------------------------------------------------

def test_comfy_launcher_pins_the_discrete_gpu_and_refuses_a_bad_dir(tmp_path):
    script = TOOLS / "start-comfyui-rocm.sh"
    r = run(script, [], env={"COMFY_DIR": str(tmp_path / "nope")})
    assert r.returncode == 1
    assert "COMFY_DIR not found" in r.stderr

    # With a stub ComfyUI it must exec, pinning HIP_VISIBLE_DEVICES=0.
    comfy = tmp_path / "comfy"
    (comfy / ".venv" / "bin").mkdir(parents=True)
    py = comfy / ".venv" / "bin" / "python"
    py.write_text('#!/bin/sh\necho "ARGS: $*"\n'
                  'echo "HIP=$HIP_VISIBLE_DEVICES"\n'
                  'echo "SVM=${HSA_USERPTR_FOR_PAGED_MEM:-unset}"\n')
    py.chmod(0o755)
    (comfy / "main.py").touch()
    r = run(script, [], env={"COMFY_DIR": str(comfy)})
    assert r.returncode == 0, r.stderr
    assert "HIP=0" in r.stdout
    assert "--disable-smart-memory" in r.stdout
    assert "--reserve-vram" in r.stdout
    assert "SVM=unset" in r.stdout, "the SVM workaround must stay opt-in"


def test_comfy_launcher_svm_workaround_is_opt_in(tmp_path):
    script = TOOLS / "start-comfyui-rocm.sh"
    comfy = tmp_path / "comfy"
    (comfy / ".venv" / "bin").mkdir(parents=True)
    py = comfy / ".venv" / "bin" / "python"
    py.write_text('#!/bin/sh\necho "SVM=${HSA_USERPTR_FOR_PAGED_MEM:-unset}"\n')
    py.chmod(0o755)
    (comfy / "main.py").touch()
    r = run(script, [], env={"COMFY_DIR": str(comfy),
                             "COMFY_SVM_WORKAROUND": "1"})
    assert "SVM=0" in r.stdout
    assert "symptom mitigation" in r.stdout
