/**
 * setInterval for async polling.
 * - A failed tick is swallowed (the next tick simply tries again) instead of becoming an unhandled rejection.
 * - Ticks never overlap: a slow response is not followed by a second request on top of it.
 * - Nothing runs while the tab is hidden.
 * Returns a function that stops the polling; use it as the effect cleanup.
 */
export function safeInterval(tick: () => Promise<void> | void, ms: number): () => void {
  let running = false;
  let stopped = false;
  const id = window.setInterval(async () => {
    if (running || stopped || document.hidden) return;
    running = true;
    try {
      await tick();
    } catch {
      /* transient failure: keep the last state shown and try again on the next tick */
    } finally {
      running = false;
    }
  }, ms);
  return () => {
    stopped = true;
    window.clearInterval(id);
  };
}
