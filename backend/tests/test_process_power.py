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
