"use client";

import { Monitor, Speaker } from "lucide-react";

import { formatDuration } from "@/lib/api/music";

import { SongArt } from "./song-art";
import { TransportButtons } from "./transport";
import type { MusicPlayer } from "./use-music-player";

/** Persistent now-playing bar, shown whenever a song is playing in the browser or on the speakers. */
export function PlayerDock({ player, onOpenStage }: { player: MusicPlayer; onOpenStage: () => void }) {
  const { song, source } = player;
  if (!song || !source) return null;
  const progress = player.duration > 0 ? (player.position / player.duration) * 100 : 0;
  const fromBrowser = source === "browser";

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80"
      role="region"
      aria-label="Now playing"
    >
      <div className="relative h-0.5 bg-muted">
        <div className="h-full bg-gradient-to-r from-primary to-accent" style={{ width: `${progress}%` }} />
      </div>
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
        <button type="button" onClick={onOpenStage} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-label="Open the display">
          <SongArt seed={song.title + song.id} className="h-11 w-11" playing={player.playing} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{song.title}</span>
            <span className="block truncate text-xs text-muted-foreground">{song.style}</span>
          </span>
        </button>
        <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
          {fromBrowser ? <Monitor className="h-3.5 w-3.5" aria-hidden="true" /> : <Speaker className="h-3.5 w-3.5" aria-hidden="true" />}
          {fromBrowser ? "Browser" : "Speakers"}
        </span>
        <span className="hidden text-xs tabular-nums text-muted-foreground sm:block">
          {formatDuration(player.position)} / {formatDuration(player.duration)}
        </span>
        <TransportButtons player={player} />
      </div>
    </div>
  );
}
