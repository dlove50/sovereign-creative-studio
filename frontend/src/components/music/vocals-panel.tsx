"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Loader2, Mic, Music2, Scissors } from "lucide-react";

import { Button } from "@/components/ui/button";
import { musicApi, type LyricsJob, type Song, type SongVersion, type VocalWaveform } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import type { MusicPlayer } from "./use-music-player";

const VERSIONS: { id: SongVersion; label: string }[] = [
  { id: "full", label: "Full song" },
  { id: "vocals", label: "Vocals" },
  { id: "instrumental", label: "Instrumental" },
];

function decodePeaks(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** The isolated vocal as a waveform: the sung parts stand out, the played part is lit, a click jumps there. */
function VocalWave({ peaks, duration, position, onSeek }: {
  peaks: string; duration: number; position: number; onSeek: (seconds: number) => void;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const data = useMemo(() => decodePeaks(peaks), [peaks]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ratio = window.devicePixelRatio || 1;
    const width = el.clientWidth;
    const height = el.clientHeight;
    el.width = width * ratio;
    el.height = height * ratio;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    ctx.scale(ratio, ratio);
    const styles = getComputedStyle(el);
    const lit = `hsl(${styles.getPropertyValue("--primary").trim() || "199 89% 48%"})`;
    const dim = `hsl(${styles.getPropertyValue("--muted-foreground").trim() || "215 16% 47%"} / 0.45)`;
    const played = duration > 0 ? position / duration : 0;
    const bars = Math.max(1, Math.floor(width / 3));
    const mid = height / 2;
    for (let i = 0; i < bars; i++) {
      const from = Math.floor((i / bars) * data.length);
      const to = Math.max(from + 1, Math.floor(((i + 1) / bars) * data.length));
      let peak = 0;
      for (let j = from; j < to; j++) peak = Math.max(peak, data[j]);
      const h = Math.max(1, (peak / 255) * (height - 4));
      ctx.fillStyle = i / bars <= played ? lit : dim;
      ctx.fillRect(i * 3, mid - h / 2, 2, h);
    }
  }, [data, duration, position]);

  return (
    <canvas
      ref={canvas}
      role="slider"
      aria-label="Vocal waveform: click to jump to that part of the song"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(position)}
      tabIndex={0}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        onSeek(((e.clientX - box.left) / box.width) * duration);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") onSeek(Math.min(duration, position + 5));
        if (e.key === "ArrowLeft") onSeek(Math.max(0, position - 5));
      }}
      className="h-24 w-full cursor-pointer rounded-lg bg-background/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    />
  );
}

export function VocalsPanel({ player, onSongChanged }: { player: MusicPlayer; onSongChanged: (song: Song) => void }) {
  const { song } = player;
  const [wave, setWave] = useState<VocalWaveform | null>(null);
  const [splitting, setSplitting] = useState(false);
  const [job, setJob] = useState<LyricsJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const songId = song?.id ?? null;

  const loadWave = useCallback(async (id: string) => {
    try {
      setWave(await musicApi.vocals(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the vocal.");
    }
  }, []);

  useEffect(() => {
    setWave(null);
    setJob(null);
    setError(null);
    if (songId) void loadWave(songId);
  }, [songId, loadWave]);

  // Follow a lyrics job until it finishes.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "error") return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await musicApi.lyricsJob(job.id);
        setJob(next);
        if (next.status === "done" && next.song) {
          onSongChanged(next.song);
          void loadWave(next.song.id);
        }
        if (next.status === "error") setError(next.error ?? "Writing down the lyrics failed.");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Lost track of the lyrics job.");
        setJob(null);
      }
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [job, onSongChanged, loadWave]);

  if (!song) return null;

  const hasStems = Boolean(wave?.has_stems);
  const working = splitting || (job !== null && job.status !== "done" && job.status !== "error");
  const timedLines = song.lyric_lines?.length ?? 0;

  const split = async () => {
    setError(null);
    setSplitting(true);
    try {
      await musicApi.splitStems(song.id);
      await loadWave(song.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Splitting the vocal failed.");
    } finally {
      setSplitting(false);
    }
  };

  const transcribe = async () => {
    setError(null);
    try {
      setJob(await musicApi.transcribe(song.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start writing down the lyrics.");
    }
  };

  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card p-5" aria-label="Vocals">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold"><Mic className="h-4 w-4 text-primary" aria-hidden="true" /> Vocals</h3>
          <p className="text-sm text-muted-foreground">
            {hasStems
              ? "Listen to the singing alone or the music without it. Click the waveform to jump."
              : "Split the song to hear the singing alone and see where it is."}
          </p>
        </div>
        <div className="flex rounded-lg border border-border bg-background/40 p-0.5" role="group" aria-label="What to hear">
          {VERSIONS.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={player.version === v.id}
              disabled={v.id !== "full" && !hasStems}
              onClick={() => void player.setVersion(v.id)}
              className={cn(
                "flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                player.version === v.id ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {v.id === "vocals" ? <Mic className="h-3.5 w-3.5" aria-hidden="true" /> : <Music2 className="h-3.5 w-3.5" aria-hidden="true" />}
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {hasStems && wave?.peaks ? (
        <VocalWave peaks={wave.peaks} duration={wave.duration} position={player.position} onSeek={(s) => void player.seek(s)} />
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {!hasStems ? (
          <Button size="sm" variant="outline" onClick={split} disabled={working}>
            {splitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Scissors className="h-4 w-4" aria-hidden="true" />}
            {splitting ? "Separating the vocal…" : "Split the vocal"}
          </Button>
        ) : null}
        <Button size="sm" variant={timedLines ? "outline" : "default"} onClick={transcribe} disabled={working}>
          {job && working ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileText className="h-4 w-4" aria-hidden="true" />}
          {timedLines ? "Write down the lyrics again" : "Write down the lyrics"}
        </Button>
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {job && working
            ? job.message
            : splitting
              ? "This takes a minute or two."
              : timedLines
                ? `${timedLines} lines, timed to the song.`
                : "Whisper listens to the vocal on this computer; nothing leaves it."}
        </span>
      </div>

      {error ? (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>
      ) : null}
    </section>
  );
}
