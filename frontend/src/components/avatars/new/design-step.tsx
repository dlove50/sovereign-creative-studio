"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, RefreshCw, Pencil } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import {
  AGES, EMPTY_DESIGN, ETHNICITIES, GENDERS, ORIENTATIONS, POSES, SAMPLE_DESCRIPTIONS, STYLES,
  buildAvatarPrompt, isDesignReady, type DesignForm,
} from "@/lib/avatar-design";
import type { AvatarAsset } from "@/lib/types";
import { cn } from "@/lib/utils";

const PREVIEW_COUNT = 4;
const POLL_MS = 3000;
const MAX_WAIT_MS = 20 * 60 * 1000; // four previews on a busy 8 GB card can take a while, but not forever
type Preview = { id: string; url: string | null; failed: boolean };

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly T[]; onChange: (v: T) => void }) {
  return (
    <div>
      <p className="text-sm font-semibold">{label}</p>
      <div role="radiogroup" aria-label={label} className="mt-2 flex rounded-full bg-raised p-1">
        {options.map((o) => (
          <button key={o} type="button" role="radio" aria-checked={value === o} onClick={() => onChange(o)}
            className={cn("flex-1 rounded-full px-3 py-2 text-sm font-medium", value === o ? "bg-background text-foreground shadow" : "text-muted-foreground hover:text-foreground")}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

function Select<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly T[]; onChange: (v: T) => void }) {
  return (
    <label className="block text-sm font-semibold">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value as T)} className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm font-normal">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

export function DesignStep({ onCancel, onSaved }: { onCancel: () => void; onSaved: (avatar: AvatarAsset) => void }) {
  const [form, setForm] = useState<DesignForm>(EMPTY_DESIGN);
  const [phase, setPhase] = useState<"form" | "generating" | "pick">("form");
  const [previews, setPreviews] = useState<Preview[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runId = useRef(0);
  const sampleIndex = useRef(0);
  const set = <K extends keyof DesignForm>(key: K, value: DesignForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  // Leaving the page must stop the polling loop; otherwise it keeps asking the server until every preview finishes.
  useEffect(() => () => { runId.current++; }, []);

  async function generate() {
    const run = ++runId.current;
    setPhase("generating");
    setError(null);
    setChosen(null);
    setPreviews([]);
    const prompt = buildAvatarPrompt(form);
    try {
      const jobs = await Promise.all(
        Array.from({ length: PREVIEW_COUNT }, () =>
          api.createGeneration({ prompt, media_type: "image", provider: "local_comfyui", mode: "text_to_image", quality_preset: "krea2_turbo_fp8" })),
      );
      const done = new Map<string, Preview>();
      const startedAt = Date.now();
      while (done.size < jobs.length) {
        if (run !== runId.current) return; // cancelled, restarted or the page was left
        if (Date.now() - startedAt > MAX_WAIT_MS) throw new Error("This is taking much longer than expected. Check that the image engine is running, then try again.");
        await new Promise((r) => setTimeout(r, POLL_MS));
        for (const job of jobs) {
          if (done.has(job.id)) continue;
          const gen = await api.getGeneration(job.id);
          if (gen.status === "completed" && gen.file_url) done.set(job.id, { id: job.id, url: gen.file_url, failed: false });
          else if (gen.status === "failed") done.set(job.id, { id: job.id, url: null, failed: true });
        }
      }
      if (run !== runId.current) return;
      const all = jobs.map((j) => done.get(j.id)!);
      if (all.every((p) => p.failed)) throw new Error("No picture could be made. Check that the image engine is running and try again.");
      setPreviews(all.filter((p) => !p.failed));
      setPhase("pick");
    } catch (e) {
      if (run !== runId.current) return;
      setError(e instanceof Error ? e.message : "The avatar could not be designed.");
      setPhase("form");
    }
  }

  async function save() {
    const pick = previews.find((p) => p.id === chosen);
    if (!pick?.url) return;
    setSaving(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("name", form.name.trim());
      body.append("source_url", pick.url);
      onSaved(await api.createPhotoAvatar(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the avatar.");
      setSaving(false);
    }
  }

  function cancel() {
    runId.current++;
    onCancel();
  }

  if (phase === "generating") {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center gap-4 text-center" role="status">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
        <p className="text-xl font-bold">Generating your avatar…</p>
        <p className="max-w-sm text-sm text-muted-foreground">Four avatar previews are being generated. Timing depends on the render queue and selected model. Please stay on this page.</p>
        <button type="button" onClick={() => { runId.current++; setPhase("form"); }} className="mt-2 rounded-full border border-border px-5 py-2 text-sm hover:bg-raised">Cancel</button>
      </div>
    );
  }

  if (phase === "pick") {
    return (
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight">Pick a photo for your avatar</h2>
        <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {previews.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => setChosen(p.id)} aria-pressed={chosen === p.id}
                className={cn("relative block aspect-[3/4] w-full overflow-hidden rounded-2xl border-2 bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", chosen === p.id ? "border-primary" : "border-transparent hover:border-border")}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={assetUrl(p.url) ?? undefined} alt="Avatar option" className="h-full w-full object-cover" />
                <span className={cn("absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-md border", chosen === p.id ? "border-primary bg-primary text-primary-foreground" : "border-white/70 bg-black/40")}>
                  {chosen === p.id ? <Check className="h-4 w-4" /> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={generate} className="inline-flex items-center justify-center gap-2 rounded-xl bg-raised py-3 text-sm font-semibold hover:bg-raised/70"><RefreshCw className="h-4 w-4" /> Generate again</button>
          <button type="button" onClick={() => setPhase("form")} className="inline-flex items-center justify-center gap-2 rounded-xl bg-raised py-3 text-sm font-semibold hover:bg-raised/70"><Pencil className="h-4 w-4" /> Edit prompt</button>
        </div>
        <div className="mt-6 flex justify-between">
          <button type="button" onClick={cancel} className="rounded-full bg-raised px-6 py-3 text-sm font-semibold hover:bg-raised/70">Cancel</button>
          <button type="button" disabled={!chosen || saving} onClick={save} className="inline-flex items-center gap-2 rounded-full bg-primary px-8 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-3xl font-extrabold tracking-tight">Describe your avatar&apos;s look</h2>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-semibold">
          Name *
          <input value={form.name} onChange={(e) => set("name", e.target.value.slice(0, 60))} className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm font-normal" />
        </label>
        <Select label="Age *" value={form.age} options={AGES} onChange={(v) => set("age", v)} />
        <Select label="Gender *" value={form.gender} options={GENDERS} onChange={(v) => set("gender", v)} />
        <Select label="Ethnicity" value={form.ethnicity} options={ETHNICITIES} onChange={(v) => set("ethnicity", v)} />
      </div>
      <div className="mt-5">
        <div className="flex items-center justify-between">
          <label htmlFor="avatar-description" className="text-sm font-semibold">Describe your avatar *</label>
          <button type="button" onClick={() => { set("description", SAMPLE_DESCRIPTIONS[sampleIndex.current++ % SAMPLE_DESCRIPTIONS.length]); }} className="text-sm font-semibold hover:underline">Try a sample</button>
        </div>
        <textarea id="avatar-description" value={form.description} onChange={(e) => set("description", e.target.value.slice(0, 400))} rows={3}
          placeholder="Hair, clothes, manner, anything that makes them recognisable" className="mt-2 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm" />
      </div>
      <div className="mt-5 space-y-4">
        <Segmented label="Orientation" value={form.orientation} options={ORIENTATIONS} onChange={(v) => set("orientation", v)} />
        <Segmented label="Pose" value={form.pose} options={POSES} onChange={(v) => set("pose", v)} />
        <Select label="Style" value={form.style} options={STYLES} onChange={(v) => set("style", v)} />
        <p className="text-sm text-muted-foreground">Choose a photographic, illustrated, or animated-film look for your preview image. Unspecified follows your description without adding a style.</p>
      </div>
      {error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-6 flex justify-between border-t border-border pt-5">
        <button type="button" onClick={cancel} className="rounded-full bg-raised px-6 py-3 text-sm font-semibold hover:bg-raised/70">Cancel</button>
        <button type="button" disabled={!isDesignReady(form)} onClick={generate} className="rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">Generate preview</button>
      </div>
    </div>
  );
}
