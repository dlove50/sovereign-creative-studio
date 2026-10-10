"""Keep Windows from throttling the heavy engines that Sovereign starts.

Windows marks background processes with no visible window as "efficiency" (EcoQoS) work and moves them to slow cores
at low clocks. The music engine's step loop is CPU-bound, so on this laptop that made songs 7 to 9 times slower
(measured 2026-10-09: the same 20 s preview took 1,056 s and 1,173 s throttled, 162 s with throttling switched off).
This only sets a flag on a process Sovereign started itself. It changes no Windows setting.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_POWER_THROTTLING = 4
_EXECUTION_SPEED = 0x1


class _Throttling(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def disable_power_throttling(pid: int) -> bool:
    """Tell Windows never to throttle process ``pid``. Returns True on success; never raises."""
    if sys.platform != "win32":
        return False
    try:
        k = _kernel32()
        handle = k.OpenProcess(_PROCESS_SET_INFORMATION | _PROCESS_QUERY_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            state = _Throttling(1, _EXECUTION_SPEED, 0)  # control the execution-speed bit, state 0 = do not throttle
            return bool(k.SetProcessInformation(handle, _PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state)))
        finally:
            k.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - a speed-up, never a reason to fail starting an engine
        return False


def throttling_forced_off(pid: int) -> bool:
    """True when ``pid`` has been explicitly marked never-throttle (used by the tests)."""
    if sys.platform != "win32":
        return False
    k = _kernel32()
    handle = k.OpenProcess(_PROCESS_QUERY_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        state = _Throttling(1, 0, 0)
        ok = k.GetProcessInformation(handle, _PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state))
        return bool(ok) and bool(state.ControlMask & _EXECUTION_SPEED) and not (state.StateMask & _EXECUTION_SPEED)
    finally:
        k.CloseHandle(handle)
