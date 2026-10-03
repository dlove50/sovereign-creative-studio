"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Monitor, Plus, Search, Smartphone } from "lucide-react";

import { api } from "@/lib/api";
import { defaultVoiceFor } from "@/lib/avatar-voice";
import { MOVIE_TEMPLATES, MOVIE_TEMPLATE_CATEGORIES, type MovieTemplate, type MovieTemplateCategory } from "@/lib/movie-templates";
import type { AvatarAsset, Movie, MovieOrientation, VoiceOption } from "@/lib/types";
import { cn } from "@/lib/utils";

type Filter = "All" | MovieTemplateCategory;
const RECENT_LIMIT = 5;

function OrientationToggle({ value, onChange }: { value: MovieOrientation; onChange: (v: MovieOrientation) => void }) {
  const option = (v: MovieOrientation, Icon: typeof Monitor, label: string) => (
    <button type="button" role="radio" aria-checked={value === v} aria-label={label} onClick={() => onChange(v)}
      className={cn("flex h-8 w-8 items-center justify-center rounded-full", value === v ? "bg-raised text-foreground" : "text-muted-foreground hover:text-foreground")}>
      <Icon className="h-4 w-4" />
    </button>
  );
  return <div role="radiogroup" aria-label="Video shape" className="flex rounded-full border border-border p-0.5">{option("landscape", Monitor, "Landscape")}{option("portrait", Smartphone, "Portrait")}</div>;
}

export function MoviesHomeView() {
  const router = useRouter();
  const [movies, setMovies] = useState<Movie[] | null>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [orientation, setOrientation] = useState<MovieOrientation>("landscape");
  const [filter, setFilter] = useState<Filter>("All");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listMovies().then(setMovies).catch(() => setMovies([]));
    api.listAvatars().then((all) => setAvatars(all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path))).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
  }, []);

  // New videos start with the avatar you made most recently, and the voice saved on it.
  const starter = useMemo(() => {
    const avatar = avatars.find((a) => !a.group_id) ?? avatars[0];
    return { avatar_id: avatar?.id ?? null, tts_voice_id: defaultVoiceFor(avatar, avatars, voices) };
  }, [avatars, voices]);

  const recent = (movies ?? []).filter((m) => m.status !== "completed").slice(0, RECENT_LIMIT);
  const templates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return MOVIE_TEMPLATES.filter((t) => (filter === "All" || t.category === filter) && (!q || `${t.title} ${t.blurb} ${t.category}`.toLowerCase().includes(q)));
  }, [filter, query]);

  async function create(key: string, title: string, scripts: string[] | null) {
    setBusy(key);
    setError(null);
    try {
      const scenes = (scripts ?? [""]).map((script) => ({ ...starter, script }));
      const movie = await api.createMovie({ title, orientation, scenes });
      router.push(`/movies/${movie.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Your video could not be created.");
      setBusy(null);
    }
  }

  const chip = (c: Filter) => cn("rounded-full px-3.5 py-1.5 text-sm font-medium", filter === c ? "bg-raised text-foreground" : "text-muted-foreground hover:text-foreground");
  return (
    <div className="mx-auto max-w-[1040px]">
      <h1 className="pt-6 text-center text-4xl font-extrabold tracking-[-0.03em]">Video editor</h1>
      <p className="mx-auto mt-2 max-w-md text-center text-sm text-muted-foreground">Build a video scene by scene, with your avatar and voice in each one.</p>
      {error ? <p className="mx-auto mt-4 max-w-md rounded-xl bg-destructive/15 px-3 py-2 text-center text-sm text-destructive">{error}</p> : null}

      <section className="mt-8" aria-labelledby="start-heading">
        <div className="flex items-center justify-between">
          <h2 id="start-heading" className="text-sm font-semibold">Get started</h2>
          <OrientationToggle value={orientation} onChange={setOrientation} />
        </div>
        <ul className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <li>
            <button type="button" disabled={busy !== null} onClick={() => create("new", "Untitled video", null)} className="group flex aspect-[16/10] w-full flex-col items-center justify-center gap-2 rounded-2xl border border-border bg-card/60 hover:border-primary/60 disabled:opacity-60">
              {busy === "new" ? <Loader2 className="h-6 w-6 animate-spin" /> : <Plus className="h-7 w-7 text-muted-foreground group-hover:text-foreground" />}
              <span className="text-sm font-semibold">New video</span>
              <span className="text-xs text-muted-foreground">Start in {orientation}</span>
            </button>
          </li>
          {recent.map((m) => (
            <li key={m.id}>
              <Link href={`/movies/${m.id}`} className="block rounded-2xl border border-border bg-card/40 p-4 hover:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <span className="inline-block rounded-full bg-raised px-2 py-0.5 text-[10px] font-medium text-muted-foreground">{m.status === "rendering" ? "Rendering" : m.status === "failed" ? "Failed" : "Draft"}</span>
                <span className="mt-3 block truncate text-sm font-semibold">{m.title}</span>
                <span className="text-xs text-muted-foreground">{m.scenes.length} {m.scenes.length === 1 ? "scene" : "scenes"} · {m.orientation}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10 rounded-3xl border border-border bg-card/40 p-5" aria-labelledby="templates-heading">
        <h2 id="templates-heading" className="text-2xl font-extrabold tracking-tight">Use a template</h2>
        <label className="mt-4 flex items-center gap-2 rounded-full border border-border bg-background px-4 py-2">
          <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search templates" aria-label="Search templates" className="w-full bg-transparent text-sm focus:outline-none" />
        </label>
        <div className="mt-3 flex flex-wrap gap-1" role="group" aria-label="Template category">
          {(["All", ...MOVIE_TEMPLATE_CATEGORIES] as Filter[]).map((c) => <button key={c} type="button" aria-pressed={filter === c} onClick={() => setFilter(c)} className={chip(c)}>{c}</button>)}
        </div>
        {templates.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">No templates match.</p> : null}
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t: MovieTemplate) => (
            <li key={t.id}>
              <button type="button" disabled={busy !== null} onClick={() => create(t.id, t.title, t.scenes)} className="flex h-full w-full flex-col rounded-2xl border border-border bg-background/60 p-4 text-left hover:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60">
                <span className="text-xs font-medium text-primary">{t.category}</span>
                <span className="mt-1 flex items-center gap-2 text-base font-bold">{t.title}{busy === t.id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}</span>
                <span className="mt-1 flex-1 text-sm text-muted-foreground">{t.blurb}</span>
                <span className="mt-3 text-xs text-muted-foreground">{t.scenes.length} scenes</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
