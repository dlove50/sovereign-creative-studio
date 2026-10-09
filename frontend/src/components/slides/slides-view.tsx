"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Loader2, Upload } from "lucide-react";

import { api } from "@/lib/api";
import type { AvatarAsset, MovieOrientation, VoiceOption, Project } from "@/lib/types";

export function SlidesView() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [orientation, setOrientation] = useState<MovieOrientation>("landscape");
  const [rewrite, setRewrite] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"upload" | "generate">("upload");
  const [prompt, setPrompt] = useState("");
  const [slideCount, setSlideCount] = useState(4);
  const [brands, setBrands] = useState<Project[]>([]);
  const [brandId, setBrandId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ movie_id: string; warnings: string[] } | null>(null);
  const docInput = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const [docNote, setDocNote] = useState<string | null>(null);

  // Fill the brief from a whole document (PDF, PowerPoint, Word, text). The user can edit it before creating.
  async function readDocument(chosen: File | undefined) {
    if (!chosen) return;
    setReading(true);
    setError(null);
    setDocNote(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", chosen);
      const made = await api.documentBrief(form);
      setPrompt(made.brief.slice(0, 8000));
      setSlideCount(Math.min(10, Math.max(2, made.suggested_slides)));
      const scanned = made.ocr_pages > 0 ? ` ${made.ocr_pages} scanned page${made.ocr_pages === 1 ? " was" : "s were"} read with OCR, so check the text for mistakes.` : "";
      setDocNote(`${made.name}: ${made.condensed ? `condensed from ${made.source_chars.toLocaleString()} characters` : `${made.source_chars.toLocaleString()} characters`}.${scanned} Review the brief, then create the scenes.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That document could not be read.");
    } finally {
      setReading(false);
    }
  }

  useEffect(() => {
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setAvatarId((cur) => cur || photos[0]?.id || "");
    }).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
    api.listProjects().then(setBrands).catch(() => setBrands([]));
  }, []);

  async function create() {
    if (!avatarId || (mode === "upload" ? !file : prompt.trim().length < 10)) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      form.append("avatar_id", avatarId);
      form.append("tts_voice_id", voiceId);
      form.append("orientation", orientation);
      form.append("rewrite", String(rewrite));
      const made = mode === "upload" ? await api.slidesToMovie(form) : await api.generatePresentation({ prompt, slide_count: slideCount, avatar_id: avatarId, tts_voice_id: voiceId, orientation, brand_project_id:brandId || null });
      if (made.warnings.length) { setResult(made); setBusy(false); }
      else router.push(`/movies/${made.movie_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The deck could not be turned into a video.");
      setBusy(false);
    }
  }

  const field = "mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Slides to video</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">
        Upload a PDF to keep each slide’s visuals beside your presenter. PowerPoint imports slide text; export it as PDF to keep the layout. Review the scenes before rendering.
      </p>
      <div role="group" aria-label="Presentation source" className="mt-6 flex justify-center gap-2">
        {(["upload", "generate"] as const).map((value) => <button key={value} type="button" disabled={busy} aria-pressed={mode === value} onClick={() => { setMode(value); setResult(null); setError(null); }} className={`rounded-full border border-border px-4 py-2 text-sm ${mode === value ? "bg-primary text-primary-foreground" : "hover:bg-raised"}`}>{value === "upload" ? "Import a deck" : "Create from a prompt"}</button>)}
      </div>
      {mode === "generate" ? <fieldset disabled={busy} className="mt-6 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" disabled={busy || reading} onClick={() => docInput.current?.click()} className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised disabled:opacity-60">
            {reading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            {reading ? "Reading your document…" : "Start from a document"}
          </button>
          <span className="text-xs text-muted-foreground">PDF, PowerPoint, Word, .txt, .md or a picture of a page, up to 50 MB. Scanned pages are read with built-in OCR. Long documents are summarised by the local model, which can take a few minutes.</span>
          <input ref={docInput} type="file" accept=".pdf,.pptx,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" className="hidden" onChange={(e) => { readDocument(e.target.files?.[0]); e.target.value = ""; }} />
        </div>
        {docNote ? <p role="status" className="rounded-xl bg-card/60 px-3 py-2 text-sm text-muted-foreground">{docNote}</p> : null}
        <label className="block text-sm font-medium">Presentation brief<textarea value={prompt} maxLength={8000} onChange={e => { setPrompt(e.target.value); setResult(null); }} rows={5} className="mt-2 w-full rounded-xl border border-input bg-background p-3 text-foreground" placeholder="Describe the topic, audience, and key points to cover…" /></label>
        <label className="block text-sm font-medium">Number of slides<select value={slideCount} onChange={e => { setSlideCount(Number(e.target.value)); setResult(null); }} className={field}>{Array.from({length:9}, (_, i) => i + 2).map(count => <option key={count} value={count}>{count}</option>)}</select></label>
        <p className="text-sm text-muted-foreground">The local model creates slide images and narration. Review the draft before rendering. Longer decks can take several minutes.</p>
        <label className="block text-sm font-medium">Brand visuals<select value={brandId} onChange={e=>{setBrandId(e.target.value);setResult(null);}} className={field}><option value="">Sovereign default</option>{brands.map(brand=><option key={brand.id} value={brand.id}>{brand.name}</option>)}</select></label>
        {brandId && <p className="text-xs text-muted-foreground">Uses saved Background, Main text, Accent, first logo, and Heading/Body font preferences. Supported installed fonts: Arial, Georgia, Times New Roman, Calibri; others use a system fallback.</p>}
      </fieldset> : <>
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className="mt-8 flex w-full flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-12 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {file ? <FileText className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a PDF or PowerPoint file"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "PDF or .pptx, up to 50 MB and 30 slides. Scanned pages are read with OCR."}</span>
      </button>
      <input ref={input} type="file" accept=".pdf,.pptx,application/pdf" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); e.target.value = ""; }} />
      </>}

      <fieldset disabled={busy} className="mt-5 grid gap-3 rounded-3xl border border-border bg-card/60 p-4 sm:grid-cols-3">
        <label className="text-xs font-medium text-muted-foreground">
          Presenter
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
            <option value="landscape">Landscape 16:9</option>
            <option value="portrait">Portrait 9:16</option>
          </select>
        </label>
      </fieldset>

      {mode === "upload" ? <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-2xl border border-border bg-card/60 p-4 hover:bg-card">
        <input type="checkbox" disabled={busy} checked={rewrite} onChange={(e) => setRewrite(e.target.checked)} className="mt-1" />
        <span>
          <span className="block text-sm font-semibold">Rewrite slide text to sound natural</span>
          <span className="block text-xs text-muted-foreground">The local AI turns bullet points into spoken sentences. Slower; turn off to use the slide text as written.</span>
        </span>
      </label> : null}

      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {result ? <section aria-label="Import result" role="status" className="mt-4 rounded-xl border border-border p-4">
        <p className="font-semibold">Your scenes are ready to review</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{result.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
        <button type="button" onClick={() => router.push(`/movies/${result.movie_id}`)} className="mt-3 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Review scenes</button>
      </section> : null}
      <div className="mt-5 flex justify-end">
        <button type="button" disabled={busy || (mode === "upload" ? !file : prompt.trim().length < 10) || !avatarId || !!result} onClick={create} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {busy ? (mode === "upload" ? "Reading your slides…" : "Creating your presentation…") : "Create scenes"}
        </button>
      </div>
    </div>
  );
}
