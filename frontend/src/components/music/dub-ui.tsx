"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A titled panel used across the dub plate studio. */
export function Panel({ title, hint, children, className }: { title: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-2xl border border-border bg-card p-4", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
        {hint ? <span className="text-xs text-muted-foreground/80">{hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

/** Labelled range input. Double-click the label to reset to the default. */
export function Fader({
  label, value, min, max, step = 1, unit = "", reset = 0, onChange, format,
}: {
  label: string; value: number; min: number; max: number; step?: number; unit?: string; reset?: number;
  onChange: (v: number) => void; format?: (v: number) => string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <label className="block space-y-1.5">
      <span className="flex items-baseline justify-between text-xs">
        <span className="font-medium text-foreground" onDoubleClick={() => onChange(reset)} title="Double-click to reset">{label}</span>
        <span className="tabular-nums text-muted-foreground">{format ? format(value) : `${value}${unit}`}</span>
      </span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="seek-bar h-1.5 w-full cursor-pointer appearance-none rounded-full"
        style={{ background: `linear-gradient(to right, hsl(var(--primary)) ${pct}%, hsl(var(--muted)) ${pct}%)` }}
      />
    </label>
  );
}

export function Segmented<T extends string>({
  value, options, onChange, label,
}: { value: T; options: { id: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="flex rounded-lg border border-border bg-background/40 p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.id} type="button" aria-pressed={value === o.id} onClick={() => onChange(o.id)}
          className={cn(
            "h-8 flex-1 rounded-md px-2.5 text-xs font-medium transition-colors",
            value === o.id ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <button
      type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)}
      className={cn(
        "flex h-8 items-center gap-2 rounded-lg border px-3 text-xs font-medium transition-colors",
        on ? "border-primary/60 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      <span className={cn("h-2 w-2 rounded-full", on ? "bg-primary" : "bg-muted-foreground/50")} aria-hidden="true" />
      {children}
    </button>
  );
}
