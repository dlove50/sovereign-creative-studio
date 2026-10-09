"use client";

import { useEffect, useRef, useState } from "react";

type Ask = { message: string; confirmLabel: string; resolve: (ok: boolean) => void };

let show: ((ask: Ask) => void) | null = null;

/**
 * An in-page replacement for window.confirm. Resolves true on Confirm, false on Cancel, Escape or a click outside.
 * Falls back to the browser prompt if the host is not mounted (it is mounted once in the root layout).
 */
export function confirmDialog(message: string, confirmLabel = "Delete"): Promise<boolean> {
  if (!show) return Promise.resolve(window.confirm(message));
  return new Promise((resolve) => show?.({ message, confirmLabel, resolve }));
}

export function ConfirmHost() {
  const [ask, setAsk] = useState<Ask | null>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    show = (next) => setAsk(next);
    return () => { show = null; };
  }, []);

  useEffect(() => { if (ask) confirmButton.current?.focus(); }, [ask]);

  function close(ok: boolean) {
    ask?.resolve(ok);
    setAsk(null);
  }

  if (!ask) return null;
  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-label="Please confirm"
      data-lenis-prevent
      onClick={() => close(false)}
      onKeyDown={(e) => { if (e.key === "Escape") close(false); }}
    >
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <p className="text-[15px] leading-relaxed">{ask.message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => close(false)} className="rounded-xl px-4 py-2 text-sm font-medium text-muted-foreground transition duration-200 hover:bg-raised hover:text-foreground motion-safe:active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Cancel
          </button>
          <button ref={confirmButton} type="button" onClick={() => close(true)} className="rounded-xl bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground transition duration-200 hover:bg-destructive/90 motion-safe:active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {ask.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
