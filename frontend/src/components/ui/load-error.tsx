"use client";

import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * A failed load. Say so plainly and offer a retry, instead of passing an outage off as an empty list or a zero balance.
 * `what` completes "Couldn't load ...", e.g. "your gallery".
 */
export function LoadError({ what, message, onRetry }: { what: string; message?: string | null; onRetry?: () => void }) {
  return (
    <div role="alert" aria-live="assertive" className="mx-auto flex max-w-[460px] flex-col items-center gap-2 rounded-2xl border border-destructive/40 bg-destructive/10 px-6 py-10 text-center shadow-card">
      <AlertTriangle className="mb-1 h-7 w-7 text-destructive" aria-hidden="true" />
      <p className="text-base font-semibold">Couldn&apos;t load {what}</p>
      <p className="max-w-[44ch] text-sm leading-relaxed text-muted-foreground">
        {message ? `${message} ` : ""}This is a loading problem, not an empty library.
      </p>
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
