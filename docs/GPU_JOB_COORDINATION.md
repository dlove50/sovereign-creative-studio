# GPU job coordination

The single Sovereign backend process shares one reentrant production lock across
music, stem separation, performance renders, model-based enhancement and the
image/product-scene/video/avatar job workers. This prevents a model enhancement
from loading alongside another production job, or music from unloading models
between chunks of an independent performance. Nested production helpers can
re-enter the lock on the same worker thread.

Queued enhancement retains its queued status while waiting. Cancellation is
checked again after admission, before a model starts. CPU-only FFmpeg and WPE
enhancements bypass the GPU lock. The enhancement's terminal state is saved
before removing its active-worker marker so polling cannot briefly report a
completed job as interrupted.

This is application-process coordination, not a machine-wide GPU reservation.
It does not stop an external ComfyUI client or LLM from loading another model.
Run one backend process, preserve GPU ownership across tools, and retain the
queue/free-memory preflight before the separate upscaler. It serializes the
listed generation workers, including a configured cloud provider reached through
those workers; CPU-only enhancement remains independent.

Verification: contention tests hold the real music admission lock, start a
model-enhancement job and a CPU job, and establish that only CPU work can enter
until the production releases the lock. A second test cancels a queued
enhancement and establishes that its model runner never starts. The affected
modules passed 52 targeted tests; the full backend suite passed 931 tests with
2 skips after the change. External-client stress and multi-process scheduling
are not established by these tests.
