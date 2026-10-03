"use client";

import { useRef, useState } from "react";
import { Download, FileVideo, Loader2, Scissors, Upload } from "lucide-react";

import { api, assetUrl } from "@/lib/api";

type Result = Awaited<ReturnType<typeof api.makeAutoClips>>;
const ACCEPT = "video/mp4,video/quicktime,video/webm,video/x-matroska,audio/mpeg,audio/wav,audio/mp4,.mkv,.m4v,.m4a";

function stamp(seconds: number) {
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export function AutoClipsView() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [count, setCount] = useState(3);
  const [seconds, setSeconds] = useState(30);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("clip_count", String(count));
      form.append("clip_seconds", String(seconds));
      setResult(await api.makeAutoClips(form));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clips could not be made.");
    } finally {
      setBusy(false);
    }
  }

  const select = "mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <div className="mx-auto max-w-[900px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Auto clips</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">
        Upload a longer video and local AI finds its best moments and cuts them into short clips. Nothing leaves this computer.
      </p>

      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-8 flex w-full flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-12 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {file ? <FileVideo className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a video or audio file"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "Works best with people talking. MP4, MOV, WEBM, MKV, MP3, WAV or M4A"}</span>
      </button>
      <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); }} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-muted-foreground">
          How many clips
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} className={select}>
            {[1, 2, 3, 4, 5, 6, 8].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          About how long
          <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} className={select}>
            {[15, 30, 45, 60, 90].map((n) => <option key={n} value={n}>{n} seconds</option>)}
          </select>
        </label>
      </div>

      <div className="mt-5 flex flex-col items-center gap-2">
        <button
          type="button"
          onClick={run}
          disabled={!file || busy}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scissors className="h-4 w-4" />}
          {busy ? "Finding the best moments…" : "Make clips"}
        </button>
        {busy ? <p className="text-xs text-muted-foreground">Listening to the video, then choosing moments. A 10-minute video takes a few minutes. You can leave this page open.</p> : null}
      </div>
      {error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      {result ? (
        <section className="mt-8" aria-live="polite">
          <p className="mb-3 text-sm text-muted-foreground">
            {result.clips.length} {result.clips.length === 1 ? "clip" : "clips"} from {stamp(result.duration)}
            {result.method === "fallback" ? " · picked by speech density because the AI model wasn't available" : ""}
          </p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {result.clips.map((clip) => {
              const src = assetUrl(clip.url);
              return (
                <li key={clip.url} className="overflow-hidden rounded-2xl border border-border bg-card/60">
                  {result.has_video ? <video controls src={src ?? undefined} className="aspect-video w-full bg-black" /> : <audio controls src={src ?? undefined} className="w-full p-3" />}
                  <div className="flex items-start justify-between gap-3 p-3">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">{clip.title || "Clip"}</span>
                      <span className="text-xs text-muted-foreground">{stamp(clip.start)}–{stamp(clip.end)} · {Math.round(clip.seconds)} s</span>
                    </span>
                    <a href={src ?? "#"} download className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs hover:bg-raised">
                      <Download className="h-3.5 w-3.5" /> Download
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
