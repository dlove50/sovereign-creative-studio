import { cn } from "@/lib/utils";

/** A grey placeholder shaped like the content that is loading. Pulses only when motion is allowed. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-xl bg-raised/70", className)} />;
}

/** A grid of placeholder cards for list pages while their data loads. */
export function SkeletonGrid({ count = 8, aspect = "aspect-square", className }: { count?: number; aspect?: string; className?: string }) {
  return (
    <div role="status" aria-label="Loading" className={className ?? "grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-card">
          <Skeleton className={cn("w-full rounded-none", aspect)} />
          <div className="space-y-2 p-3">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
