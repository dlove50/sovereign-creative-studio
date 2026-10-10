"use client";

import { useState } from "react";
import { Loader2, PenLine, Sparkles, Undo2 } from "lucide-react";

import { VoiceInputButton } from "@/components/chain/VoiceInputButton";
import { promptAssistApi, type PromptKind } from "@/lib/api/prompt-assist";
import { cn } from "@/lib/utils";

/**
 * Optional helpers under any prompt box: speak instead of typing, tidy what you said, or have the whole thing written
 * from your idea. Nothing changes unless you press a button, and Undo puts your own words back.
 */
export function PromptAssist({
  value, onChange, kind = "general", context = "", movieSeconds, className, writeLabel = "Write it for me",
}: {
  value: string;
  onChange: (text: string) => void;
  kind?: PromptKind;
  context?: string;
  movieSeconds?: number;
  className?: string;
  writeLabel?: string;
}) {
  const [busy, setBusy] = useState<"clean" | "write" | null>(null);
  const [previous, setPrevious] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(mode: "clean" | "write") {
    const text = value.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(mode);
    try {
      const out = mode === "clean"
        ? await promptAssistApi.clean(text, kind === "movie" ? "story" : kind, context)
        : kind === "movie"
          ? await promptAssistApi.movie(text, movieSeconds ?? 60, context)
          : await promptAssistApi.write(text, kind, context);
      setPrevious(value);
      onChange(out.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The writing model did not answer.");
    } finally {
      setBusy(null);
    }
  }

  const empty = !value.trim();
  const button = "inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground disabled:pointer-events-none disabled:opacity-45";

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)} role="group" aria-label="Prompt helpers">
      <VoiceInputButton disabled={!!busy} onTranscript={(spoken) => onChange(value.trim() ? `${value.trim()} ${spoken}` : spoken)} />
      <button type="button" className={button} disabled={empty || !!busy} onClick={() => void run("clean")}
        title="Fix grammar, drop the ums and repeats, and organise it. Keeps every idea you gave.">
        {busy === "clean" ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
        Clean it up
      </button>
      <button type="button" className={button} disabled={empty || !!busy} onClick={() => void run("write")}
        title="Treat what is in the box as your idea and write the whole thing for you.">
        {busy === "write" ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <PenLine className="h-3.5 w-3.5" aria-hidden="true" />}
        {busy === "write" ? "Writing…" : writeLabel}
      </button>
      {previous !== null && !busy ? (
        <button type="button" className={button} onClick={() => { onChange(previous); setPrevious(null); }} title="Put your own words back">
          <Undo2 className="h-3.5 w-3.5" aria-hidden="true" /> Undo
        </button>
      ) : null}
      {error ? <p role="alert" className="w-full text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
