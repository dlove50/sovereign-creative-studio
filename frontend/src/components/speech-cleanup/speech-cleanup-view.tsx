"use client";

import { useRef, useState } from "react";
import { Download, FileAudio, Loader2, Scissors, Upload } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

type Result = Awaited<ReturnType<typeof api.cleanSpeech>>;
const ACCEPT = "video/mp4,video/quicktime,video/webm,video/x-matroska,audio/mpeg,audio/wav,audio/mp4,.mkv,.m4v,.m4a";

function fmt(seconds: number) {
  const m = Math.floor(seconds / 60);
  return m ? `${m}m ${Math.round(seconds % 60)}s` : `${seconds.toFixed(1)}s`;
}

export function SpeechCleanupView() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pauses, setPauses] = useState(true);
  const [fillers, setFillers] = useState(true);
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
      form.append("remove_pauses", String(pauses));
      form.append("remove_fillers", String(fillers));
      setResult(await api.cleanSpeech(form));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The file could not be cleaned.");
    } finally {
      setBusy(false);
    }
  }

  const src = result ? assetUrl(result.output_url) : null;
  const toggle = "flex cursor-pointer items-start gap-3 rounded-2xl border border-border bg-card/60 p-4 hover:bg-card";
  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Speech cleanup</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">
        Upload a video or recording and get a tighter version without long pauses or “um” and “uh”. It runs on this computer.
      </p>

      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-8 flex w-full flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-12 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {file ? <FileAudio className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a video or audio file"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "MP4, MOV, WEBM, MKV, MP3, WAV or M4A"}</span>
      </button>
      <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); }} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className={toggle}>
          <input type="checkbox" checked={pauses} onChange={(e) => setPauses(e.target.checked)} className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]" />
          <span><span className="block text-sm font-semibold">Long pauses</span><span className="text-xs text-muted-foreground">Shortens silences over 0.6 seconds and keeps a natural beat.</span></span>
        </label>
        <label className={toggle}>
          <input type="checkbox" checked={fillers} onChange={(e) => setFillers(e.target.checked)} className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]" />
          <span><span className="block text-sm font-semibold">Filler words</span><span className="text-xs text-muted-foreground">Removes “um”, “uh”, “er” and “hmm”. Needs a minute of listening time.</span></span>
        </label>
      </div>

      <div className="mt-5 flex justify-center">
        <button
          type="button"
          onClick={run}
          disabled={!file || busy || (!pauses && !fillers)}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scissors className="h-4 w-4" />}
          {busy ? "Cleaning…" : "Clean up speech"}
        </button>
      </div>
      {error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      {result && src ? (
        <section className="mt-8 rounded-3xl border border-border bg-card/60 p-5" aria-live="polite">
          <p className="text-sm">
            <strong>{fmt(result.original_seconds)}</strong> → <strong className="text-primary">{fmt(result.new_seconds)}</strong>
            <span className="text-muted-foreground"> · removed {fmt(result.seconds_removed)} ({result.pauses_removed} pauses, {result.fillers_removed} fillers)</span>
          </p>
          {result.seconds_removed === 0 ? <p className="mt-1 text-xs text-muted-foreground">Nothing needed cutting, so this is the original.</p> : null}
          <div className={cn("mt-4", result.has_video ? "" : "max-w-md")}>
            {result.has_video ? <video controls src={src} className="max-h-[420px] w-full rounded-2xl border border-border bg-black" /> : <audio controls src={src} className="w-full" />}
          </div>
          <a href={src} download className="mt-4 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground">
            <Download className="h-4 w-4" /> Download
          </a>
        </section>
      ) : null}
    </div>
  );
}
