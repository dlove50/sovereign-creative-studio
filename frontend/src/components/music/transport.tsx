"use client";

import { Pause, Play, Rewind, FastForward, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/api/music";
import { cn } from "@/lib/utils";

import type { MusicPlayer } from "./use-music-player";

const SKIP_SECONDS = 10;

/** Play / pause / stop with 10-second skips. Works the same for the browser and the speakers. */
export function TransportButtons({ player, size = "icon" }: { player: MusicPlayer; size?: "icon" | "lg" }) {
  const hasSong = player.song !== null;
  const running = player.source !== null && !player.paused;
  const skip = (delta: number) =>
    void player.seek(Math.max(0, Math.min(player.position + delta, Math.max(player.duration - 0.5, 0))));
  const big = size === "lg";
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Playback controls">
      <Button size="icon" variant="ghost" onClick={() => skip(-SKIP_SECONDS)} disabled={player.source === null} aria-label={`Back ${SKIP_SECONDS} seconds`}>
        <Rewind className="h-4 w-4" />
      </Button>
      <Button
        size="icon"
        variant="default"
        className={cn(big && "h-12 w-12 rounded-full")}
        onClick={() => void (running ? player.togglePause() : player.play())}
        disabled={!hasSong}
        aria-label={running ? "Pause" : "Play"}
      >
        {running ? <Pause className={big ? "h-5 w-5" : "h-4 w-4"} /> : <Play className={big ? "h-5 w-5" : "h-4 w-4"} />}
      </Button>
      <Button size="icon" variant="outline" onClick={() => void player.stop()} disabled={player.source === null} aria-label="Stop">
        <Square className="h-4 w-4" />
      </Button>
      <Button size="icon" variant="ghost" onClick={() => skip(SKIP_SECONDS)} disabled={player.source === null} aria-label={`Forward ${SKIP_SECONDS} seconds`}>
        <FastForward className="h-4 w-4" />
      </Button>
    </div>
  );
}

/** Click or drag to jump anywhere in the song, with elapsed and total time. */
export function SeekBar({ player }: { player: MusicPlayer }) {
  const max = Math.max(player.duration, 1);
  const pct = Math.min(100, (player.position / max) * 100);
  return (
    <div className="space-y-1.5">
      <input
        type="range"
        min={0}
        max={max}
        step={0.1}
        value={Math.min(player.position, max)}
        disabled={player.source === null}
        onChange={(e) => void player.seek(Number(e.target.value))}
        aria-label="Seek"
        className="seek-bar h-1.5 w-full cursor-pointer appearance-none rounded-full disabled:cursor-default"
        style={{ background: `linear-gradient(to right, hsl(var(--primary)) ${pct}%, hsl(var(--muted)) ${pct}%)` }}
      />
      <div className="flex justify-between text-xs tabular-nums text-muted-foreground">
        <span>{formatDuration(player.position)}</span>
        <span>{formatDuration(player.duration)}</span>
      </div>
    </div>
  );
}
