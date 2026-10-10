"use client";

import { PromptAssist } from "@/components/prompt-assist/prompt-assist";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ExternalLink, Loader2, Music2, Sparkles, Wand2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { musicApi, type MusicJob, type MusicStatus, type Song } from "@/lib/api/music";
import { LyricChat } from "./lyric-chat";
import { cn } from "@/lib/utils";

/** The average length of a commercial release: 3 minutes 30 seconds. */
const RADIO_SECONDS = 210;

/** Length of the instrumental style preview. Measured here: instrumentals take about 6 s of work per second of music, so 20 s is a few minutes. */
const PREVIEW_SECONDS = 20;
/** The default is 2 minutes: a 3:30 song can take an hour on this laptop, so long songs are an explicit choice. */
const DEFAULT_SECONDS = 120;

/** Honest time to make a song: typical and slow-case minutes (the server sends measured values). */
function makeTime(durationSeconds: number, limits?: MusicStatus["limits"]) {
  const minutes = durationSeconds / 60;
  const typical = Math.max(1, Math.round(minutes * (limits?.typical_minutes_per_song_minute ?? 6)));
  const slow = Math.max(typical + 1, Math.round(minutes * (limits?.slow_minutes_per_song_minute ?? 17)));
  return { typical, slow };
}

export type PlayTarget = "speakers" | "browser" | "none";

const GENRES = [
  "Reggae", "Pop", "Rock", "Hip hop", "Country", "Jazz", "Lo-fi", "EDM", "Folk", "R&B", "Latin",
  "Gospel", "Blues", "Metal", "Synthwave", "Ambient",
];
/** The style tags with the chosen genre first (unless the style already names it). */
function withGenre(style: string, genre: string | null): string {
  const trimmed = style.trim();
  if (!genre || trimmed.toLowerCase().includes(genre.toLowerCase())) return trimmed;
  return trimmed ? `${genre}, ${trimmed}` : genre;
}

function GenrePicker({ genre, onChange }: { genre: string | null; onChange: (genre: string | null) => void }) {
  return (
    <div className="space-y-2">
      <Label>Genre</Label>
      <div className="flex flex-wrap gap-2">
        {GENRES.map((g) => (
          <button
            key={g}
            type="button"
            aria-pressed={genre === g}
            onClick={() => onChange(genre === g ? null : g)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm transition-colors",
              genre === g
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
            )}
          >
            {g}
          </button>
        ))}
      </div>
    </div>
  );
}

const TAG_GROUPS: { label: string; tags: string[] }[] = [
  { label: "Mood", tags: ["uplifting", "melancholic", "dreamy", "energetic", "romantic", "dark", "chill"] },
  { label: "Instruments", tags: ["acoustic guitar", "piano", "synth", "drums", "bass", "strings", "brass"] },
  { label: "Vocals", tags: ["male vocal", "female vocal", "choir", "raspy vocal", "soft vocal"] },
  { label: "Tempo", tags: ["slow tempo", "mid tempo", "upbeat", "fast tempo"] },
];
const SECTIONS = ["[intro]", "[verse]", "[chorus]", "[bridge]", "[outro]"];
const STEPS: { stage: MusicJob["stage"][]; label: string }[] = [
  { stage: ["queued", "writing_lyrics"], label: "Writing lyrics" },
  { stage: ["starting_engine"], label: "Starting engine" },
  { stage: ["generating"], label: "Composing with YuE2" },
  { stage: ["saving", "done"], label: "Saving song" },
];

type Mode = "chat" | "describe" | "custom";
const MODE_LABELS: Record<Mode, string> = { chat: "Talk it through", describe: "Describe it", custom: "Custom" };

export function CreatePanel({
  status,
  onSongReady,
}: {
  status: MusicStatus | null;
  onSongReady: (song: Song, target: PlayTarget) => void;
}) {
  const limits = status?.limits;
  const [mode, setMode] = useState<Mode>("chat");
  const [idea, setIdea] = useState("");
  const [genre, setGenre] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [duration, setDuration] = useState(DEFAULT_SECONDS);
  const [quality, setQuality] = useState("V0");
  const [seed, setSeed] = useState("");
  const [target, setTarget] = useState<PlayTarget>("browser");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [job, setJob] = useState<MusicJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lyricsRef = useRef<HTMLTextAreaElement>(null);
  const poll = useRef<number | null>(null);

  // A running clock, so a long render never looks frozen.
  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const started = Date.now();
    const id = window.setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  useEffect(() => () => {
    if (poll.current) window.clearTimeout(poll.current);
  }, []);

  const ready = status?.engine.ready ?? false;
  const engineOffline = status ? !status.engine.online : false;
  const maxSeconds = limits?.max_seconds ?? 300;
  const minSeconds = Math.max(limits?.min_seconds ?? 10, 60);

  const follow = useCallback(
    (first: MusicJob, playTarget: PlayTarget) => {
      const tick = async () => {
        try {
          const next = await musicApi.job(first.id);
          setJob(next);
          if (next.status === "done" && next.song) {
            setBusy(false);
            onSongReady(next.song, playTarget);
            return;
          }
          if (next.status === "error") {
            setBusy(false);
            setError(next.message);
            return;
          }
        } catch (e) {
          setBusy(false);
          setError(e instanceof Error ? e.message : "Lost contact with the music engine.");
          return;
        }
        poll.current = window.setTimeout(tick, 1500);
      };
      poll.current = window.setTimeout(tick, 800);
    },
    [onSongReady],
  );

  const submit = async (preview = false) => {
    setError(null);
    setBusy(true);
    setJob(null);
    const auto_play = target === "speakers";
    try {
      const started = preview
        ? await musicApi.generate({
            // A short instrumental of the chosen style: a draft to approve before the long vocal render.
            title: `Preview: ${title.trim() || style.trim().slice(0, 40)}`.slice(0, 80),
            style: withGenre(style, genre),
            instrumental: true,
            duration: PREVIEW_SECONDS,
            quality,
            auto_play,
          })
        : mode === "describe"
          ? await musicApi.createFromIdea({
              idea: idea.trim(),
              genre: genre ?? undefined,
              instrumental,
              duration,
              quality,
              auto_play,
            })
          : await musicApi.generate({
              title: title.trim() || undefined,
              style: withGenre(style, genre),
              lyrics: instrumental ? undefined : lyrics.trim(),
              instrumental,
              duration,
              quality,
              seed: seed.trim() ? Number(seed) : undefined,
              auto_play,
            });
      setJob(started);
      follow(started, target);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "Could not start the song.");
    }
  };

  const insertSection = (tag: string) => {
    const el = lyricsRef.current;
    const start = el?.selectionStart ?? lyrics.length;
    const end = el?.selectionEnd ?? lyrics.length;
    const prefix = start > 0 && lyrics[start - 1] !== "\n" ? "\n" : "";
    const next = `${lyrics.slice(0, start)}${prefix}${tag}\n${lyrics.slice(end)}`;
    setLyrics(next);
    requestAnimationFrame(() => {
      el?.focus();
      const pos = start + prefix.length + tag.length + 1;
      el?.setSelectionRange(pos, pos);
    });
  };

  const addTag = (tag: string) => {
    const parts = style.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.some((p) => p.toLowerCase() === tag.toLowerCase())) return;
    setStyle([...parts, tag].join(", "));
  };

  const hasInput =
    mode === "describe"
      ? idea.trim().length > 0
      : withGenre(style, genre).length > 0 && (instrumental || lyrics.trim().length > 0);
  // An offline engine is fine: creating a song launches it.
  const canSubmit = hasInput && !busy && (ready || engineOffline);
  const stepIndex = job ? Math.max(0, STEPS.findIndex((s) => s.stage.includes(job.stage))) : -1;
  const skipsLyrics = mode !== "describe";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-border bg-background/40 p-0.5" role="tablist" aria-label="Creation mode">
          {(["chat", "describe", "custom"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={cn(
                "h-9 rounded-md px-4 text-sm font-medium transition-colors",
                mode === m ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Engine</span>
          <Badge variant="default">YuE2 · local · free</Badge>
          <Link href="/cloud-studio" className="inline-flex items-center gap-1 text-primary hover:underline">
            ElevenLabs (paid) <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </Link>
        </div>
      </div>

      {mode === "chat" ? (
        <div className="space-y-4">
          <GenrePicker genre={genre} onChange={setGenre} />
          <LyricChat
            song={{ title, style: withGenre(style, genre), lyrics }}
            duration={duration}
            onSong={(next) => { setTitle(next.title); setStyle(next.style); setLyrics(next.lyrics); }}
          />
        </div>
      ) : mode === "describe" ? (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="music-idea">What is the song about?</Label>
            <Textarea
              id="music-idea"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              maxLength={600}
              placeholder="A reggae song about a sunrise at the bay, easygoing and warm…"
              className="min-h-[110px]"
            />
              <PromptAssist value={idea} onChange={(t) => setIdea(t.slice(0, 600))} kind="song_idea" context="Music Lab: what the song is about" />
            <p className="text-xs text-muted-foreground">
              Sovereign writes original lyrics from your idea, then YuE2 composes and sings the full song.
            </p>
          </div>
          <GenrePicker genre={genre} onChange={setGenre} />
        </div>
      ) : (
        <div className="space-y-4">
          <GenrePicker genre={genre} onChange={setGenre} />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="music-title">Title <span className="text-muted-foreground">(optional)</span></Label>
              <Input id="music-title" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} placeholder="Harbor Morning" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="music-style">Style</Label>
              <Input
                id="music-style"
                value={style}
                maxLength={limits?.max_style_chars ?? 500}
                onChange={(e) => setStyle(e.target.value)}
                placeholder="indie folk, warm female vocal, acoustic guitar"
              />
                <PromptAssist value={style} onChange={(t) => setStyle(t.slice(0, 500))} kind="style" context="Music Lab: style tags for the song" />
            </div>
          </div>
          <div className="space-y-2">
            {TAG_GROUPS.map((group) => (
              <div key={group.label} className="flex flex-wrap items-center gap-1.5">
                <span className="w-24 text-xs text-muted-foreground">{group.label}</span>
                {group.tags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => addTag(tag)}
                    className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                  >
                    + {tag}
                  </button>
                ))}
              </div>
            ))}
          </div>
          {!instrumental ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="music-lyrics">Lyrics</Label>
                <div className="flex flex-wrap gap-1.5">
                  {SECTIONS.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => insertSection(tag)}
                      className="rounded-md border border-border px-2 py-0.5 font-mono text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
              <Textarea
                id="music-lyrics"
                ref={lyricsRef}
                value={lyrics}
                onChange={(e) => setLyrics(e.target.value)}
                maxLength={limits?.max_lyrics_chars ?? 3000}
                placeholder={"[verse]\nWrite your own words here…\n[chorus]\nThe part everyone sings along to…"}
                className="min-h-[220px] font-mono"
              />
                <PromptAssist value={lyrics} onChange={(t) => setLyrics(t.slice(0, 3000))} kind="lyrics" context={`Music Lab lyrics${style ? `, style: ${style}` : ""}`} />
              <p className="text-right text-xs tabular-nums text-muted-foreground">
                {lyrics.length} / {limits?.max_lyrics_chars ?? 3000}
              </p>
            </div>
          ) : null}
        </div>
      )}

      <div className="grid gap-5 rounded-xl border border-border bg-background/30 p-4 md:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="music-duration">Length</Label>
            <span className="text-sm tabular-nums text-muted-foreground">
              {Math.floor(duration / 60)}:{String(duration % 60).padStart(2, "0")} ({duration / 60} min)
            </span>
          </div>
          <input
            id="music-duration"
            type="range"
            min={minSeconds / 60}
            max={maxSeconds / 60}
            step={0.5}
            value={duration / 60}
            onChange={(e) => setDuration(Math.round(Number(e.target.value) * 2) * 30)}
            className="w-full accent-[hsl(var(--primary))]"
            aria-valuetext={`${duration / 60} minutes`}
          />
          <div className="flex justify-between text-[11px] tabular-nums text-muted-foreground" aria-hidden="true">
            {Array.from({ length: Math.round(maxSeconds / 60) - Math.round(minSeconds / 60) + 1 }, (_, i) => (
              <span key={i}>{Math.round(minSeconds / 60) + i} min</span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {([[60, "1 min"], [120, "2 min"], [RADIO_SECONDS, "3:30 radio length"], [300, "5 min"]] as const).map(([secs, label]) => (
              <button
                key={secs}
                type="button"
                onClick={() => setDuration(secs)}
                aria-pressed={duration === secs}
                className={cn(
                  "h-7 rounded-md px-2.5 text-xs font-medium transition-colors",
                  duration === secs ? "bg-primary/20 text-primary" : "bg-muted/50 text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Most commercial songs run about 3:30. On this computer a {Math.floor(duration / 60)}:{String(duration % 60).padStart(2, "0")} song usually takes about {makeTime(duration, limits).typical} minutes to make, and up to {makeTime(duration, limits).slow} if the graphics card is busy. The engine may end a little early.
          </p>
        </div>
        <div className="space-y-2">
          <Label>Play when ready</Label>
          <div className="inline-flex rounded-lg border border-border bg-background/40 p-0.5" role="group" aria-label="Play when ready">
            {([["browser", "In browser"], ["speakers", "Speakers"], ["none", "Don't play"]] as const).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-pressed={target === id}
                onClick={() => setTarget(id)}
                className={cn(
                  "h-9 rounded-md px-3 text-sm font-medium transition-colors",
                  target === id ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={instrumental}
            onChange={(e) => setInstrumental(e.target.checked)}
            className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]"
          />
          <span className="text-sm">
            Instrumental <Badge variant="muted" className="ml-1">experimental</Badge>
            <span className="block text-xs text-muted-foreground">No singing. Results can still contain vocal-like sounds.</span>
          </span>
        </label>
        <details className="text-sm md:col-span-1">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Advanced</summary>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="music-quality">MP3 quality</Label>
              <select
                id="music-quality"
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm"
              >
                {(limits?.qualities ?? ["V0", "128k", "320k"]).map((q) => (
                  <option key={q} value={q}>{q}</option>
                ))}
              </select>
            </div>
            {mode === "custom" ? (
              <div className="space-y-1.5">
                <Label htmlFor="music-seed">Seed</Label>
                <Input id="music-seed" inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))} placeholder="random" />
              </div>
            ) : null}
          </div>
        </details>
      </div>

      {!ready ? (
        <p role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {engineOffline
            ? "The music engine is waking up. It starts by itself when you open Music Lab or press Create song; the first song takes a few extra seconds."
            : status?.engine.detail ?? "Checking the music engine…"}
        </p>
      ) : null}
      {error ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <p className="min-w-0 flex-1">{error}</p>
          <Button size="sm" variant="outline" className="text-foreground" onClick={() => void submit(false)} disabled={!canSubmit}>
            Try again
          </Button>
          {duration > 120 ? (
            <Button size="sm" variant="outline" className="text-foreground" onClick={() => { setDuration(120); setError(null); }}>
              Switch to 2 min
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-4">
        <Button size="lg" onClick={() => void submit(false)} disabled={!canSubmit}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : mode === "describe" ? <Sparkles className="h-4 w-4" aria-hidden="true" /> : <Wand2 className="h-4 w-4" aria-hidden="true" />}
          {busy ? `${(job?.message ?? "Creating").replace(/\.+$/, "")}… ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}` : "Create song"}
        </Button>
        {mode !== "describe" && withGenre(style, genre) && !busy ? (
          <Button size="lg" variant="outline" onClick={() => void submit(true)} disabled={!(ready || engineOffline)} title="Makes a 20-second instrumental of this style so you can approve the sound before the long vocal render">
            <Music2 className="h-4 w-4" aria-hidden="true" />
            Preview the sound ({PREVIEW_SECONDS} s)
          </Button>
        ) : null}
        {busy ? (
          <p className="max-w-[60ch] text-sm text-muted-foreground">
            This song usually takes about {makeTime(duration, limits).typical} minutes, and up to {makeTime(duration, limits).slow} if the graphics card is busy.
            You can leave this page: the finished song is saved to your Library.
          </p>
        ) : null}
      </div>

      {job ? (
        <ol className="grid gap-2 sm:grid-cols-4" aria-label="Progress">
          {STEPS.map((step, i) => {
            const skipped = i === 0 && skipsLyrics;
            const done = skipped || i < stepIndex || job.status === "done";
            const current = !skipped && i === stepIndex && job.status !== "done" && job.status !== "error";
            return (
              <li
                key={step.label}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                  current ? "border-primary/60 bg-primary/10 text-foreground" : "border-border text-muted-foreground",
                  done && "text-foreground",
                )}
              >
                {current ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
                ) : done ? (
                  <Check className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                ) : (
                  <span className="h-4 w-4 rounded-full border border-border" aria-hidden="true" />
                )}
                {skipped ? "Your lyrics" : step.label}
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}
