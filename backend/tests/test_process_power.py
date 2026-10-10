"""Windows power-throttling flag on engine processes Sovereign starts."""
import subprocess
import sys

import pytest

from app.services import process_power

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@windows_only
def test_a_started_process_can_be_marked_never_throttle():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert process_power.disable_power_throttling(child.pid) is True
        assert process_power.throttling_forced_off(child.pid) is True
    finally:
        child.kill()
        child.wait()


def test_a_missing_process_is_reported_not_raised():
    assert process_power.disable_power_throttling(2_000_000_000) is False


@windows_only
def test_children_are_found_and_marked_too():
    # a launcher that starts a child, like the venv python.exe does for the real engine
    parent = subprocess.Popen([sys.executable, "-c",
                               "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"])
    try:
        import time

        children = []
        for _ in range(40):
            children = process_power.descendants(parent.pid)
            if children:
                break
            time.sleep(0.25)
        assert children, "child process not found"
        done = process_power.disable_power_throttling_tree(parent.pid)
        assert parent.pid in done and set(children) <= set(done)
        assert all(process_power.throttling_forced_off(p) for p in done)
    finally:
        for child in process_power.descendants(parent.pid):
            subprocess.run(["taskkill", "/F", "/PID", str(child)], capture_output=True)
        parent.kill()
        parent.wait()
