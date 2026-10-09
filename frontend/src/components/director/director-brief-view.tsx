"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Clapperboard, Loader2, Mic, Music2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { directorApi, formatLength, type DirectorTemplate } from "@/lib/api/director";
import { musicApi } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import { templateIcon, useTemplates } from "./template-carousel";

const MIN_SHOT_SECONDS = 3;
const MAX_SHOT_SECONDS = 8;
const STEP_SECONDS = 5;

function Toggle({ on, onChange, icon: Icon, children }: { on: boolean; onChange: (v: boolean) => void; icon: typeof Mic; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={cn(
        "flex h-10 items-center gap-2 rounded-xl border px-3.5 text-sm font-medium transition-colors",
        on ? "border-primary/60 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {children}
    </button>
  );
}

export function DirectorBriefView() {
  const router = useRouter();
  const params = useSearchParams();
  const { templates, creditsPerClip } = useTemplates();
  const template: DirectorTemplate | undefined = useMemo(
    () => templates?.find((t) => t.id === params.get("template")),
    [templates, params],
  );
  const [brief, setBrief] = useState<Record<string, string>>({});
  const [seconds, setSeconds] = useState(30);
  const [music, setMusic] = useState(true);
  const [narration, setNarration] = useState(true);
  const [voiceId, setVoiceId] = useState("");
  const [planner, setPlanner] = useState<"fast" | "best">("fast");
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (template) setSeconds(template.seconds.default);
  }, [template]);

  useEffect(() => {
    musicApi.dubVoices().then((v) => setVoices(v.ready ? v.voices : [])).catch(() => setVoices([]));
  }, []);

  if (templates === null) return <div className="h-64 animate-pulse rounded-2xl bg-card/50" />;
  if (!template) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">That format was not found.</p>
        <Link href="/director" className="text-primary underline underline-offset-4">Back to all formats</Link>
      </div>
    );
  }

  const Icon = templateIcon(template.id);
  const clipsLow = Math.max(1, Math.ceil(seconds / MAX_SHOT_SECONDS));
  const clipsHigh = Math.max(clipsLow, Math.floor(seconds / MIN_SHOT_SECONDS));
  const missing = template.fields.filter((f) => f.required && !(brief[f.id] ?? "").trim());

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const project = await directorApi.start({
        template: template.id, brief, seconds, music: music && !!template.music,
        narration: narration && template.narration, voice_id: voiceId || null, planner,
      });
      router.push(`/director/watch?id=${project.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The video could not be started.");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link href="/director" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> All formats
      </Link>
      <div className="grid gap-6 md:grid-cols-[14rem_1fr]">
        <div className="relative overflow-hidden rounded-2xl border border-border">
          <img src={template.image} alt="" className="aspect-[4/5] h-full w-full object-cover" />
          <span className="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent" aria-hidden="true" />
          <span className="absolute inset-x-3 bottom-3 flex items-center gap-2 text-lg font-bold text-white">
            <Icon className="h-5 w-5" aria-hidden="true" /> {template.label}
          </span>
        </div>

        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (!busy && missing.length === 0) void start();
          }}
        >
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight">{template.label}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {template.tagline} {template.orientation === "portrait" ? "Vertical (9:16)." : "Widescreen (16:9)."}
            </p>
          </div>

          {template.fields.map((field) => (
            <div key={field.id} className="space-y-1.5">
              <Label htmlFor={`brief-${field.id}`}>
                {field.label}
                {field.required ? null : <span className="ml-1 text-xs font-normal text-muted-foreground">(optional)</span>}
              </Label>
              {field.long ? (
                <Textarea
                  id={`brief-${field.id}`} rows={3} maxLength={600} placeholder={field.placeholder}
                  value={brief[field.id] ?? ""} onChange={(e) => setBrief((b) => ({ ...b, [field.id]: e.target.value }))}
                />
              ) : (
                <Input
                  id={`brief-${field.id}`} maxLength={600} placeholder={field.placeholder}
                  value={brief[field.id] ?? ""} onChange={(e) => setBrief((b) => ({ ...b, [field.id]: e.target.value }))}
                />
              )}
            </div>
          ))}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="director-length">Length</Label>
              <span className="text-sm tabular-nums text-muted-foreground">{formatLength(seconds)}</span>
            </div>
            <input
              id="director-length" type="range" min={template.seconds.min} max={template.seconds.max} step={STEP_SECONDS}
              value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}
              className="w-full accent-[hsl(var(--primary))]"
            />
            <div className="flex justify-between text-[11px] tabular-nums text-muted-foreground" aria-hidden="true">
              <span>{formatLength(template.seconds.min)}</span>
              <span>{formatLength(template.seconds.max)}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {template.narration ? <Toggle on={narration} onChange={setNarration} icon={Mic}>Voice-over</Toggle> : null}
            {template.music ? <Toggle on={music} onChange={setMusic} icon={Music2}>Soundtrack (Music Lab)</Toggle> : null}
            {template.narration && narration && voices.length > 0 ? (
              <select
                value={voiceId} onChange={(e) => setVoiceId(e.target.value)} aria-label="Narrator voice"
                className="h-10 rounded-xl border border-border bg-background px-3 text-sm"
              >
                <option value="">Default voice</option>
                {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label htmlFor="director-planner" className="text-xs font-medium">Story planning</label>
            <select
              id="director-planner" value={planner} onChange={(e) => setPlanner(e.target.value as "fast" | "best")}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm"
            >
              <option value="fast">Fast (about 30 seconds)</option>
              <option value="best">Best (a few minutes, larger model)</option>
            </select>
          </div>

          <div className="rounded-xl border border-border bg-card/60 p-3 text-xs text-muted-foreground">
            About {clipsLow} to {clipsHigh} shots at {creditsPerClip} credits each: {clipsLow * creditsPerClip} to {clipsHigh * creditsPerClip} credits,
            only charged for clips that finish. Each shot takes a minute or two on your GPU, so a {formatLength(seconds)} video can take a while.
            You can leave the page; it keeps going.
          </div>

          {error ? <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
          <Button type="submit" disabled={busy || missing.length > 0} className="h-11 px-6">
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Clapperboard className="mr-2 h-4 w-4" aria-hidden="true" />}
            Start directing
          </Button>
          {missing.length > 0 ? <p className="text-xs text-muted-foreground">Fill in: {missing.map((f) => f.label).join(", ")}</p> : null}
        </form>
      </div>
    </div>
  );
}
