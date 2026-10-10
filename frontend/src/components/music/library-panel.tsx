"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useMemo, useState } from "react";
import { Download, Loader2, Monitor, Music, Pencil, Play, Search, Speaker, Star, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { assetUrl } from "@/lib/api/core";
import { musicApi, type Song } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import { SongArt } from "./song-art";
import type { MusicPlayer } from "./use-music-player";

type Filter = "all" | "favorites" | "vocals" | "instrumental";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "favorites", label: "Favorites" },
  { id: "vocals", label: "With vocals" },
  { id: "instrumental", label: "Instrumental" },
];

export function LibraryPanel({
  songs,
  loading,
  player,
  onChanged,
}: {
  songs: Song[];
  loading: boolean;
  player: MusicPlayer;
  onChanged: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return songs.filter((s) => {
      if (filter === "favorites" && !s.favorite) return false;
      if (filter === "vocals" && s.instrumental) return false;
      if (filter === "instrumental" && !s.instrumental) return false;
      return !q || `${s.title} ${s.style} ${s.lyrics}`.toLowerCase().includes(q);
    });
  }, [songs, query, filter]);

  const run = async (id: string, action: () => Promise<unknown>) => {
    setBusyId(id);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusyId(null);
    }
  };

  const commitRename = (song: Song) => {
    const next = draft.trim();
    setRenaming(null);
    if (next && next !== song.title) void run(song.id, () => musicApi.patchSong(song.id, { title: next }));
  };

  const remove = async (song: Song) => {
    if (!await confirmDialog(`Delete “${song.title}”? This removes the audio file.`)) return;
    if (player.song?.id === song.id) void player.stop();
    void run(song.id, () => musicApi.deleteSong(song.id));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search songs, styles or lyrics"
            className="pl-9"
            aria-label="Search songs"
          />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter songs">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm transition-colors",
                filter === f.id ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading your songs…
        </p>
      ) : shown.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border py-16 text-center">
          <Music className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="font-medium">{songs.length === 0 ? "No songs yet" : "Nothing matches"}</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            {songs.length === 0
              ? "Make your first song on the Create tab, or tell Jarvis to make one."
              : "Try a different search or filter."}
          </p>
        </div>
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {shown.map((song) => {
            const current = player.song?.id === song.id && player.source !== null;
            const busy = busyId === song.id;
            return (
              <li
                key={song.id}
                className={cn(
                  "flex gap-4 rounded-2xl border bg-card p-4 transition-colors",
                  current ? "border-primary/60" : "border-border hover:border-primary/30",
                )}
              >
                <button
                  type="button"
                  onClick={() => void player.playInBrowser(song)}
                  className="group relative shrink-0"
                  aria-label={`Play ${song.title} in the browser`}
                >
                  <SongArt seed={song.title + song.id} className="h-20 w-20" playing={current && player.playing} />
                  <span className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/40 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                    <Play className="h-7 w-7 fill-white text-white" aria-hidden="true" />
                  </span>
                </button>
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    {renaming === song.id ? (
                      <Input
                        autoFocus
                        value={draft}
                        maxLength={80}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => commitRename(song)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename(song);
                          if (e.key === "Escape") setRenaming(null);
                        }}
                        aria-label="Song title"
                        className="h-8"
                      />
                    ) : (
                      <h3 className="truncate font-semibold">{song.title}</h3>
                    )}
                    <button
                      type="button"
                      onClick={() => run(song.id, () => musicApi.patchSong(song.id, { favorite: !song.favorite }))}
                      aria-pressed={song.favorite}
                      aria-label={song.favorite ? "Remove from favorites" : "Add to favorites"}
                      disabled={busy}
                      className="shrink-0 text-muted-foreground transition-colors hover:text-amber-300"
                    >
                      <Star className={cn("h-5 w-5", song.favorite && "fill-amber-300 text-amber-300")} />
                    </button>
                  </div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">{song.style}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {song.instrumental ? <Badge variant="muted">Instrumental</Badge> : <Badge variant="default">Vocals</Badge>}
                    <span>{new Date(song.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                    <span>· made in {Math.round(song.generation_seconds)}s</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <Button size="sm" variant="outline" onClick={() => void player.playInBrowser(song)}>
                      <Monitor className="h-4 w-4" aria-hidden="true" /> Browser
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => run(song.id, () => player.playOnSpeakers(song))} disabled={busy}>
                      <Speaker className="h-4 w-4" aria-hidden="true" /> Speakers
                    </Button>
                    <a
                      href={assetUrl(song.audio_url) ?? song.audio_url}
                      download={`${song.title}.mp3`}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      aria-label={`Download ${song.title}`}
                    >
                      <Download className="h-4 w-4" />
                    </a>
                    <button
                      type="button"
                      onClick={() => {
                        setDraft(song.title);
                        setRenaming(song.id);
                      }}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      aria-label={`Rename ${song.title}`}
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(song)}
                      disabled={busy}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/15 hover:text-destructive"
                      aria-label={`Delete ${song.title}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
