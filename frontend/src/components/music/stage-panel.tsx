"use client";

import { useMemo, useState } from "react";
import { AudioLines, CircleDot, Waves } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { SongArt } from "./song-art";
import { SpectrumCanvas, type VisualStyle } from "./spectrum-canvas";
import { SeekBar, TransportButtons } from "./transport";
import type { MusicPlayer } from "./use-music-player";
import { useViz } from "./use-viz";

const VISUALS: { id: VisualStyle; label: string; icon: typeof AudioLines }[] = [
  { id: "bars", label: "Spectrum", icon: AudioLines },
  { id: "radial", label: "Halo", icon: CircleDot },
  { id: "wave", label: "Waves", icon: Waves },
];

/** Split lyrics into sections so the current part of the song can be highlighted. */
function parseSections(lyrics: string): { tag: string; lines: string[] }[] {
  const sections: { tag: string; lines: string[] }[] = [];
  for (const raw of lyrics.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const tag = line.match(/^\[(.+)\]$/);
    if (tag) sections.push({ tag: tag[1], lines: [] });
    else if (sections.length) sections[sections.length - 1].lines.push(line);
    else sections.push({ tag: "", lines: [line] });
  }
  return sections;
}

export function StagePanel({ player }: { player: MusicPlayer }) {
  const [visual, setVisual] = useState<VisualStyle>("bars");
  const { song } = player;
  const viz = useViz(song?.id ?? null);
  const sections = useMemo(() => (song ? parseSections(song.lyrics) : []), [song]);
  const progress = player.duration > 0 ? Math.min(1, player.position / player.duration) : 0;
  // Lyrics carry no timestamps, so the highlight follows song progress by line count.
  const totalLines = sections.reduce((n, s) => n + s.lines.length, 0);
  const activeLine = totalLines ? Math.min(totalLines - 1, Math.floor(progress * totalLines)) : -1;
  let lineCursor = 0;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <section className="relative overflow-hidden rounded-2xl border border-border bg-card">
        <div className="pointer-events-none absolute inset-0 welcome-glow opacity-70" aria-hidden="true" />
        <div className="relative flex items-center justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            {song ? <SongArt seed={song.title + song.id} className="h-14 w-14" playing={player.playing} /> : null}
            <div className="min-w-0">
              <h2 className="truncate text-lg font-semibold">{song ? song.title : "Nothing playing yet"}</h2>
              <p className="truncate text-sm text-muted-foreground">
                {song ? song.style : "Play a song from your library, or ask Jarvis to make one."}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {player.source ? (
              <Badge variant="success">{player.source === "speakers" ? "On speakers" : "In browser"}</Badge>
            ) : null}
            <div className="flex rounded-lg border border-border bg-background/40 p-0.5" role="group" aria-label="Visual style">
              {VISUALS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setVisual(v.id)}
                  aria-pressed={visual === v.id}
                  title={v.label}
                  className={cn(
                    "flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
                    visual === v.id ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <v.icon className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline">{v.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="relative h-[22rem] px-4 md:h-[28rem]">
          <SpectrumCanvas
            frames={viz?.frames ?? null}
            bands={viz?.bands ?? 24}
            fps={viz?.fps ?? 20}
            getPosition={player.getPosition}
            active={player.playing && !!viz}
            visual={visual}
          />
        </div>
        <div className="relative space-y-3 p-4 pt-2">
          <SeekBar player={player} />
          <div className="flex justify-center">
            <TransportButtons player={player} size="lg" />
          </div>
        </div>
      </section>

      <aside className="max-h-[36rem] overflow-y-auto rounded-2xl border border-border bg-card p-5" aria-label="Lyrics">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lyrics</h3>
        {!song ? (
          <p className="text-sm text-muted-foreground">Lyrics appear here while a song plays.</p>
        ) : song.instrumental ? (
          <p className="text-sm text-muted-foreground">Instrumental, no lyrics.</p>
        ) : (
          <div className="space-y-4">
            {sections.map((section, si) => (
              <div key={si} className="space-y-1">
                {section.tag ? (
                  <p className="text-xs font-semibold uppercase tracking-wide text-primary/80">{section.tag}</p>
                ) : null}
                {section.lines.map((line, li) => {
                  const idx = lineCursor++;
                  const on = player.source !== null && idx === activeLine;
                  return (
                    <p
                      key={li}
                      className={cn(
                        "text-sm leading-relaxed transition-colors",
                        on ? "font-medium text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {line}
                    </p>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
