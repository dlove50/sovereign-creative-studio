"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Download, Loader2, Monitor, Plus, Smartphone, Sparkles, Trash2, UserRound, Wand2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, Movie, MovieOrientation, MovieScene, VoiceOption } from "@/lib/types";
import { cn } from "@/lib/utils";

const SAVE_DELAY_MS = 800;
const POLL_MS = 4000;
const WORDS_PER_SECOND = 2.5;


const STATUS_LABEL: Record<NonNullable<MovieScene["status"]>, string> = {
  draft: "", voice: "Recording voice…", video: "Animating…", completed: "Done", failed: "Failed",
};

function newScene(from?: MovieScene): MovieScene {
  return { id: Math.random().toString(36).slice(2, 14), avatar_id: from?.avatar_id ?? null, tts_voice_id: from?.tts_voice_id ?? null, script: "" };
}

export function MovieEditorView({ movieId }: { movieId: string }) {
  const [movie, setMovie] = useState<Movie | null>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [selected, setSelected] = useState(0);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const [improving, setImproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const latest = useRef<Movie | null>(null);
  const pending = useRef<Movie | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);
  const startingRef = useRef(false);
  const mounted = useRef(true);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.getMovie(movieId).then((value) => { latest.current = value; setMovie(value); }).catch((e) => setError(e instanceof Error ? e.message : "This video could not be opened."));
    api.listAvatars().then((all) => setAvatars(all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path))).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
  }, [movieId]);

  const rendering = movie?.status === "rendering";

  const locked = rendering || starting;

  // Serialize saves: an older request must never overwrite a newer edit.
  const flushSave = useCallback(async (): Promise<void> => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    if (inFlight.current) {
      await inFlight.current;
      if (pending.current) return flushSave();
      return;
    }
    const operation = (async () => {
      while (pending.current) {
        const next = pending.current;
        pending.current = null;
        try {
          const saved = await api.updateMovie(next.id, { title: next.title, orientation: next.orientation, scenes: next.scenes });
          if (mounted.current && !pending.current) {
            latest.current = saved;
            setMovie(saved);
            setSaving("saved");
          }
        } catch (e) {
          pending.current ??= next;
          if (mounted.current) {
            setError(e instanceof Error ? e.message : "Changes could not be saved. Try saving again.");
            setSaving("idle");
          }
          throw e;
        }
      }
    })();
    inFlight.current = operation;
    try { await operation; } finally { inFlight.current = null; }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (pending.current || inFlight.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      mounted.current = false;
      window.removeEventListener("beforeunload", beforeUnload);
      // Internal navigation still sends the latest pending draft.
      void flushSave().catch(() => undefined);
    };
  }, [flushSave]);

  useEffect(() => {
    if (!rendering) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await api.getMovie(movieId);
        if (!cancelled) { latest.current = value; setMovie(value); setError(null); }
      } catch {
        if (!cancelled) setError("Render progress is temporarily unavailable. Reconnecting…");
      }
      if (!cancelled) timer = setTimeout(poll, POLL_MS);
    };
    timer = setTimeout(poll, POLL_MS);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [rendering, movieId]);

  function change(update: Partial<Movie>) {
    const current = latest.current;
    if (!current || current.status === "rendering" || startingRef.current) return;
    const next = { ...current, ...update, status: "draft" as const, error_message: null };
    latest.current = next;
    pending.current = next;
    setMovie(next);
    setSaving("saving");
    setError(null);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { void flushSave().catch(() => undefined); }, SAVE_DELAY_MS);
  }

  function changeScene(index: number, update: Partial<MovieScene>) {
    const current = latest.current;
    if (!current) return;
    change({ scenes: current.scenes.map((s, i) => (i === index ? { ...s, ...update, status: "draft", error: null } : s)) });
  }

  if (error && !movie) {
    return (
      <div className="py-16 text-center">
        <p className="font-semibold">{error}</p>
        <Link href="/projects" className="mt-2 inline-block text-sm text-primary hover:underline">Back to projects</Link>
      </div>
    );
  }
  if (!movie) return <p className="py-16 text-center text-sm text-muted-foreground">Opening your video…</p>;

  const selectedIndex = Math.max(0, Math.min(selected, movie.scenes.length - 1));
  const scene = movie.scenes[selectedIndex];
  const look = avatars.find((a) => a.id === scene?.avatar_id);
  const lookSrc = assetUrl(look?.thumbnail_path || look?.source_file_path || null);
  const words = (s: MovieScene) => s.script.split(/\s+/).filter(Boolean).length;
  const totalSeconds = Math.round(movie.scenes.reduce((n, s) => n + words(s), 0) / WORDS_PER_SECOND);
  const hasScript = movie.scenes.some((s) => s.script.trim());
  const missingLook = movie.scenes.some((s) => s.script.trim() && !s.avatar_id);
  const portrait = movie.orientation === "portrait";

  async function generate() {
    if (startingRef.current || latest.current?.status === "rendering") return;
    startingRef.current = true;
    setStarting(true);
    setError(null);
    try {
      await flushSave();
      const current = latest.current;
      if (!current) return;
      const value = await api.renderMovie(current.id);
      latest.current = value;
      setMovie(value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The video could not be started.");
    } finally { startingRef.current = false; setStarting(false); }
  }

  async function improve() {
    if (!scene || scene.script.trim().length < 3) return;
    const targetId = scene.id;
    const originalScript = scene.script;
    setImproving(true);
    setError(null);
    try {
      const out = await api.improveDelivery(originalScript);
      if (!mounted.current) return;
      const current = latest.current;
      const index = current?.scenes.findIndex((s) => s.id === targetId) ?? -1;
      if (!current || index < 0 || current.scenes[index].script !== originalScript || current.status === "rendering" || startingRef.current) {
        setError("The scene changed while delivery was improving. Your edits were kept; try again when ready.");
        return;
      }
      changeScene(index, { script: out.script.slice(0, 1500) });
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : "Improve delivery failed.");
    } finally {
      if (mounted.current) setImproving(false);
    }
  }

  return (
    <div className="mx-auto max-w-[1240px]">
      <header className="flex flex-wrap items-center gap-3 border-b border-border pb-4">
        <Link href="/projects" aria-label="Back to projects" className="flex h-9 w-9 items-center justify-center rounded-full border border-border hover:bg-raised"><ArrowLeft className="h-4 w-4" /></Link>
        <input
          value={movie.title}
          onChange={(e) => change({ title: e.target.value.slice(0, 200) })}
          disabled={locked}
          aria-label="Video title"
          placeholder="Untitled video"
          className="min-w-0 flex-1 bg-transparent text-xl font-extrabold tracking-[-0.02em] focus:outline-none"
        />
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : movie.status === "draft" ? "Draft" : ""}
        </span>
        <div className="flex rounded-full border border-border bg-card/60 p-1" role="group" aria-label="Orientation">
          {(["portrait", "landscape"] as MovieOrientation[]).map((o) => (
            <button
              key={o}
              type="button"
              aria-pressed={movie.orientation === o}
              disabled={locked}
              onClick={() => change({ orientation: o })}
              className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-xs", movie.orientation === o ? "bg-raised text-foreground" : "text-muted-foreground")}
            >
              {o === "portrait" ? <Smartphone className="h-3.5 w-3.5" /> : <Monitor className="h-3.5 w-3.5" />}
              {o === "portrait" ? "Portrait 9:16" : "Landscape 16:9"}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={locked || !hasScript || missingLook || improving}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {locked ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {locked ? "Generating…" : `Generate · ${movie.credits_estimate} credits`}
        </button>
      </header>

      {missingLook ? <p className="mt-3 text-sm text-muted-foreground">Choose a look for each scene with a script before generating.</p> : null}
      {error ? <p role="alert" className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}{pending.current ? <button type="button" className="ml-3 underline" onClick={() => { setSaving("saving"); setError(null); void flushSave().catch(() => undefined); }}>Save again</button> : null}</p> : null}
      {movie.status === "failed" && movie.error_message ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{movie.error_message}</p> : null}
      {rendering ? (
        <p className="mt-3 rounded-xl bg-primary/10 px-3 py-2 text-sm">Rendering {movie.scenes.length} scenes, with the selected looks and voices. You can leave this page; it keeps going.</p>
      ) : null}
      {movie.status === "completed" && movie.output_video_path ? (
        <div className="mt-4 flex flex-wrap items-end gap-4 rounded-3xl border border-border bg-card/60 p-4">
          <video controls src={assetUrl(movie.output_video_path) ?? undefined} className={cn("rounded-2xl border border-border bg-black", portrait ? "max-h-[420px]" : "max-h-[340px]")} />
          <a href={assetUrl(movie.output_video_path) ?? "#"} download className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground">
            <Download className="h-4 w-4" /> Download video
          </a>
        </div>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-[200px_minmax(0,1fr)_300px]">
        <aside aria-label="Scenes">
          <ol className="space-y-2">
            {movie.scenes.map((s, i) => {
              const thumb = avatars.find((a) => a.id === s.avatar_id)?.thumbnail_path;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(i)}
                    className={cn("flex w-full items-center gap-3 rounded-2xl border p-2 text-left", i === selectedIndex ? "border-primary bg-card" : "border-border bg-card/40 hover:bg-card")}
                  >
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-raised">
                      {thumb ? <img src={assetUrl(thumb) ?? undefined} alt="" className="h-full w-full object-cover" /> : <UserRound className="h-4 w-4 text-muted-foreground" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold">Scene {i + 1}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">{s.script || "No script yet"}</span>
                      {s.status && s.status !== "draft" ? (
                        <span className={cn("mt-0.5 flex items-center gap-1 text-[11px]", s.status === "failed" ? "text-destructive" : "text-primary")}>
                          {s.status === "completed" ? <Check className="h-3 w-3" /> : s.status === "failed" ? null : <Loader2 className="h-3 w-3 animate-spin" />}
                          {STATUS_LABEL[s.status]}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          <button
            type="button"
            disabled={locked || movie.scenes.length >= 30}
            onClick={() => { change({ scenes: [...movie.scenes, newScene(movie.scenes[movie.scenes.length - 1])] }); setSelected(movie.scenes.length); }}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-border py-3 text-sm text-muted-foreground hover:bg-card hover:text-foreground disabled:opacity-60"
          >
            <Plus className="h-4 w-4" /> Add scene
          </button>
          <p className="mt-3 text-[11px] text-muted-foreground">{movie.scenes.length} scenes · about {totalSeconds} s total</p>
        </aside>

        <section aria-label="Scene preview" className="flex items-start justify-center rounded-3xl border border-border bg-background/60 p-4">
          <div className={cn("flex items-center justify-center overflow-hidden rounded-2xl bg-raised", portrait ? "aspect-[9/16] w-full max-w-[292px]" : "aspect-video w-full")}>
            {lookSrc ? <img src={lookSrc} alt={look?.name ?? ""} className="h-full w-full object-cover" /> : <span className="px-6 text-center text-sm text-muted-foreground">Pick a look for this scene</span>}
          </div>
        </section>

        {scene ? (
          <section aria-label={`Scene ${selectedIndex + 1} settings`} className="space-y-4 rounded-3xl border border-border bg-card/60 p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Scene {selectedIndex + 1}</h2>
              {movie.scenes.length > 1 ? (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => { change({ scenes: movie.scenes.filter((_, i) => i !== selectedIndex) }); setSelected(Math.max(0, selectedIndex - 1)); }}
                  aria-label="Delete scene"
                  className="rounded-full p-1.5 text-muted-foreground hover:bg-raised hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              ) : null}
            </div>
            <label className="block text-xs font-medium text-muted-foreground">
              Avatar look
              <select
                value={scene.avatar_id ?? ""}
                disabled={locked}
                onChange={(e) => changeScene(selectedIndex, { avatar_id: e.target.value || null })}
                className="mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground"
              >
                <option value="">Choose a look…</option>
                {avatars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium text-muted-foreground">
              Voice
              <select
                value={scene.tts_voice_id ?? ""}
                disabled={locked}
                onChange={(e) => changeScene(selectedIndex, { tts_voice_id: e.target.value || null })}
                className="mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground"
              >
                <option value="">Default voice</option>
                {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
            </label>
            <div>
              <label htmlFor="scene-script" className="text-xs font-medium text-muted-foreground">Script</label>
              <textarea
                id="scene-script"
                value={scene.script}
                disabled={locked}
                onChange={(e) => changeScene(selectedIndex, { script: e.target.value.slice(0, 1500) })}
                rows={8}
                placeholder="What should your avatar say in this scene?"
                className="mt-1 w-full rounded-2xl border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">{words(scene)} words · about {Math.round(words(scene) / WORDS_PER_SECOND)} s</span>
                <button
                  type="button"
                  onClick={improve}
                  disabled={locked || improving || scene.script.trim().length < 3}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs hover:bg-raised disabled:opacity-60"
                >
                  {improving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                  {improving ? "Improving… (about a minute)" : "Improve delivery"}
                </button>
              </div>
            </div>
            {scene.status === "failed" && scene.error ? <p className="text-xs text-destructive">{scene.error}</p> : null}
          </section>
        ) : null}
      </div>
    </div>
  );
}
