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


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def descendants(pid: int) -> list[int]:
    """Every child, grandchild and so on of ``pid`` (the Python launcher starts the real engine as a child)."""
    if sys.platform != "win32":
        return []
    k = _kernel32()
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = k.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return []
    parents: dict[int, list[int]] = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents.setdefault(int(entry.th32ParentProcessID), []).append(int(entry.th32ProcessID))
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    found: list[int] = []
    queue = [int(pid)]
    while queue:
        for child in parents.get(queue.pop(), []):
            if child not in found:
                found.append(child)
                queue.append(child)
    return found


def disable_power_throttling_tree(pid: int) -> list[int]:
    """Mark ``pid`` and everything it started as never-throttle. Returns the pids that were set."""
    done = [p for p in [int(pid), *descendants(pid)] if disable_power_throttling(p)]
    return done
