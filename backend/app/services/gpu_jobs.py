"""One GPU production job at a time in the single backend process.

Generation jobs may invoke nested tools such as stem separation, so this lock is
reentrant. CPU-only enhancement keeps running while a GPU job owns the slot.
External ComfyUI clients and separately launched LLMs are outside this boundary;
the renderer's queue/free-memory preflight remains necessary.
"""
import threading

GPU_JOB_LOCK = threading.RLock()
