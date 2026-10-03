"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, Trash2, Upload } from "lucide-react";

import { api } from "@/lib/api";
import { batchRowsFromCsv, type BatchRowDraft } from "@/lib/csv";
import type { AvatarAsset, MovieOrientation, VoiceOption } from "@/lib/types";

const MAX_ROWS = 50;
const CREDITS_PER_VIDEO = 17; // voice 2 + avatar video 15 (see backend movies.cost_estimate)
const RENDER_SECONDS_PER_SECOND = 55;
const WORDS_PER_SECOND = 2.5;

export function BatchView() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [credits, setCredits] = useState<number | null>(null);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [orientation, setOrientation] = useState<MovieOrientation>("portrait");
  const [rows, setRows] = useState<BatchRowDraft[]>([]);
  const [busy, setBusy] = useState<"draft" | "render" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setAvatarId((cur) => cur || photos[0]?.id || "");
    }).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
    api.authMe().then((u) => setCredits(u.credits)).catch(() => setCredits(null));
  }, []);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    const parsed = batchRowsFromCsv(await file.text());
    if (parsed.length === 0) { setError("No scripts found. Use a column named “script”, with an optional “title” column."); return; }
    if (parsed.length > MAX_ROWS) setError(`Only the first ${MAX_ROWS} rows were kept.`);
    setRows(parsed.slice(0, MAX_ROWS));
  }

  function update(i: number, patch: Partial<BatchRowDraft>) {
    setRows((all) => all.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  const ready = rows.filter((r) => r.script.trim());
  const totalCredits = ready.length * CREDITS_PER_VIDEO;
  const totalWords = ready.reduce((n, r) => n + r.script.split(/\s+/).filter(Boolean).length, 0);
  const estMinutes = Math.max(1, Math.round(((totalWords / WORDS_PER_SECOND) * RENDER_SECONDS_PER_SECOND) / 60));
  const short = credits !== null && totalCredits > credits;

  async function create(render: boolean) {
    if (!avatarId || ready.length === 0) return;
    if (render && !window.confirm(`Render ${ready.length} videos now? This uses ${totalCredits} credits and takes about ${estMinutes} minutes of GPU time.`)) return;
    setBusy(render ? "render" : "draft");
    setError(null);
    try {
      await api.createBatch({ avatar_id: avatarId, tts_voice_id: voiceId || null, orientation, rows: ready, render });
      router.push("/projects");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The batch could not be created.");
      setBusy(null);
    }
  }

  const field = "mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Batch videos</h1>
      <p className="mx-auto mt-2 max-w-lg text-center text-sm text-muted-foreground">
        Make many talking-avatar videos at once. Upload a spreadsheet saved as CSV with a “script” column and an optional “title” column.
      </p>

      <section className="mt-7 grid gap-3 rounded-3xl border border-border bg-card/60 p-4 sm:grid-cols-3">
        <label className="text-xs font-medium text-muted-foreground">
          Avatar look
          <select value={avatarId} onChange={(e) => setAvatarId(e.target.value)} className={field}>
            {avatars.length === 0 ? <option value="">No avatars yet</option> : null}
            {avatars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Voice
          <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} className={field}>
            <option value="">Default voice</option>
            {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Shape
          <select value={orientation} onChange={(e) => setOrientation(e.target.value as MovieOrientation)} className={field}>
            <option value="portrait">Portrait 9:16</option>
            <option value="landscape">Landscape 16:9</option>
          </select>
        </label>
      </section>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={() => fileInput.current?.click()} className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised">
          <Upload className="h-4 w-4" /> Upload CSV
        </button>
        <button type="button" onClick={() => setRows((r) => (r.length < MAX_ROWS ? [...r, { title: "", script: "" }] : r))} className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised">
          <Plus className="h-4 w-4" /> Add a row
        </button>
        <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      {rows.length === 0 ? (
        <p className="py-14 text-center text-sm text-muted-foreground">No rows yet. Upload a CSV or add a row to start.</p>
      ) : (
        <>
          <ul className="mt-4 space-y-2" aria-label="Videos to make">
            {rows.map((row, i) => (
              <li key={i} className="grid gap-2 rounded-2xl border border-border bg-card/50 p-3 sm:grid-cols-[44px_220px_1fr_36px]">
                <span className="hidden text-sm text-muted-foreground sm:flex sm:items-center">{i + 1}</span>
                <input value={row.title} onChange={(e) => update(i, { title: e.target.value.slice(0, 200) })} placeholder={`Batch video ${i + 1}`} aria-label={`Title for video ${i + 1}`} className="h-10 rounded-xl border border-input bg-background px-3 text-sm" />
                <textarea value={row.script} onChange={(e) => update(i, { script: e.target.value.slice(0, 1500) })} rows={2} placeholder="What should the avatar say?" aria-label={`Script for video ${i + 1}`} className="rounded-xl border border-input bg-background px-3 py-2 text-sm" />
                <button type="button" onClick={() => setRows((all) => all.filter((_, idx) => idx !== i))} aria-label={`Remove video ${i + 1}`} className="flex h-10 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
          <div className="sticky bottom-3 mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-lg shadow-black/30">
            <span className="text-sm">
              <strong>{ready.length}</strong> videos · {totalCredits} credits{credits !== null ? ` (you have ${credits})` : ""} · about {estMinutes} min to render
              {short ? <span className="ml-2 text-destructive">Not enough credits to render them all.</span> : null}
            </span>
            <span className="flex gap-2">
              <button type="button" disabled={busy !== null || ready.length === 0 || !avatarId} onClick={() => create(false)} className="rounded-full border border-border px-4 py-2 text-sm hover:bg-raised disabled:opacity-60">
                {busy === "draft" ? "Creating…" : "Save as drafts"}
              </button>
              <button type="button" disabled={busy !== null || ready.length === 0 || !avatarId || short} onClick={() => create(true)} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                {busy === "render" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Create and render all
              </button>
            </span>
          </div>
        </>
      )}
    </div>
  );
}
