"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Pencil, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDuration, musicApi, type LyricLine, type Song } from "@/lib/api/music";
import { cn } from "@/lib/utils";

/** Index of the line being sung at `position` (the last one that has started), or -1 before the first. */
export function activeLineAt(lines: LyricLine[], position: number): number {
  let active = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].start <= position) active = i;
    else break;
  }
  return active;
}

/** Lyrics written down from the vocal, lit line by line as the song plays; click a line to jump to it. */
export function TimedLyrics({ song, position, playing, onSeek, onSaved }: {
  song: Song;
  position: number;
  playing: boolean;
  onSeek: (seconds: number) => void;
  onSaved: (song: Song) => void;
}) {
  const lines = song.lyric_lines ?? [];
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LyricLine[]>(lines);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const list = useRef<HTMLOListElement | null>(null);
  const active = playing ? activeLineAt(lines, position) : -1;

  useEffect(() => {
    if (!editing) setDraft(song.lyric_lines ?? []);
  }, [song.lyric_lines, editing]);

  // Keep the sung line in view inside the lyrics box (never scroll the whole page).
  useEffect(() => {
    const box = list.current?.closest("aside");
    const row = active >= 0 ? list.current?.children[active] as HTMLElement | undefined : undefined;
    if (!box || !row) return;
    const top = row.offsetTop - box.clientHeight / 3;
    box.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, [active]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      onSaved(await musicApi.saveLyricLines(song.id, draft));
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the lyrics.");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="space-y-3">
        <ol className="space-y-2">
          {draft.map((line, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{formatDuration(line.start)}</span>
              <Input
                value={line.text}
                maxLength={300}
                aria-label={`Line ${i + 1}`}
                onChange={(e) => setDraft(draft.map((l, j) => (j === i ? { ...l, text: e.target.value } : l)))}
                className="h-8 text-sm"
              />
            </li>
          ))}
        </ol>
        {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
        <div className="flex gap-2">
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
            Save
          </Button>
          <Button size="sm" variant="outline" onClick={() => { setDraft(lines); setEditing(false); }} disabled={saving}>
            <X className="h-4 w-4" aria-hidden="true" /> Cancel
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Clear a line to remove it. Each line keeps its timing.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <ol ref={list} className="space-y-1">
        {lines.map((line, i) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => onSeek(line.start)}
              title={`Jump to ${formatDuration(line.start)}`}
              className={cn(
                "w-full rounded-md px-2 py-1 text-left text-sm leading-relaxed transition-colors hover:bg-muted/60",
                i === active ? "bg-primary/10 font-medium text-foreground" : "text-muted-foreground",
              )}
            >
              {line.text}
            </button>
          </li>
        ))}
      </ol>
      <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
        <Pencil className="h-4 w-4" aria-hidden="true" /> Correct the lyrics
      </Button>
    </div>
  );
}
