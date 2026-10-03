"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Loader2, Upload } from "lucide-react";

import { api } from "@/lib/api";
import type { AvatarAsset, MovieOrientation, VoiceOption } from "@/lib/types";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setAvatarId((cur) => cur || photos[0]?.id || "");
    }).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
  }, []);

  async function create() {
    if (!file || !avatarId) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("avatar_id", avatarId);
      form.append("tts_voice_id", voiceId);
      form.append("orientation", orientation);
      form.append("rewrite", String(rewrite));
      const made = await api.slidesToMovie(form);
      router.push(`/movies/${made.movie_id}`);
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
        Upload a PDF or PowerPoint deck. Each slide becomes a scene where your avatar presents its text. You review every scene before anything renders.
      </p>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-8 flex w-full flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-12 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {file ? <FileText className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a PDF or PowerPoint file"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "PDF or .pptx, up to 50 MB and 30 slides"}</span>
      </button>
      <input ref={input} type="file" accept=".pdf,.pptx,application/pdf" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />

      <section className="mt-5 grid gap-3 rounded-3xl border border-border bg-card/60 p-4 sm:grid-cols-3">
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
      </section>

      <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-2xl border border-border bg-card/60 p-4 hover:bg-card">
        <input type="checkbox" checked={rewrite} onChange={(e) => setRewrite(e.target.checked)} className="mt-1" />
        <span>
          <span className="block text-sm font-semibold">Rewrite slide text to sound natural</span>
          <span className="block text-xs text-muted-foreground">The local AI turns bullet points into spoken sentences. Slower; turn off to use the slide text as written.</span>
        </span>
      </label>

      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-5 flex justify-end">
        <button type="button" disabled={busy || !file || !avatarId} onClick={create} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {busy ? "Reading your slides…" : "Create scenes"}
        </button>
      </div>
    </div>
  );
}
