"use client";

import { Scissors, Trash2, VolumeX } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDuration, type DubParams } from "@/lib/api/music";

import { Fader, Panel, Segmented, Toggle } from "./dub-ui";

type DropBeats = "1" | "2" | "4" | "8";
const DROP_BEATS: DropBeats[] = ["1", "2", "4", "8"];

type Props = {
  params: DubParams;
  patch: (p: Partial<DubParams>) => void;
  cursor: number;
  duration: number;
  bpm: number;
};

/** Mixer, filter, dub echo and reverb, drop-outs and the cut. These are applied when you audition or press. */
export function DubFxPanel({ params, patch, cursor, duration, bpm }: Props) {
  const [dropBeats, setDropBeats] = useState<DropBeats>("4");
  const end = params.end ?? duration;
  const db = (v: number) => `${v > 0 ? "+" : ""}${v} dB`;
  const beatSeconds = bpm > 0 ? 60 / bpm : 0.5;

  const addDrop = () =>
    patch({ drops: [...params.drops, { at: cursor, beats: Number(dropBeats) }].sort((a, b) => a.at - b.at).slice(0, 16) });

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Mixer" hint="Applied when you audition or press">
        <div className="space-y-3">
          <Fader label="Low" value={params.eq_low} min={-12} max={12} step={0.5} format={db} onChange={(v) => patch({ eq_low: v })} />
          <Fader label="Mid" value={params.eq_mid} min={-12} max={12} step={0.5} format={db} onChange={(v) => patch({ eq_mid: v })} />
          <Fader label="High" value={params.eq_high} min={-12} max={12} step={0.5} format={db} onChange={(v) => patch({ eq_high: v })} />
          <Segmented
            label="Filter"
            value={params.filter_mode}
            onChange={(v) => patch({ filter_mode: v })}
            options={[
              { id: "off", label: "Filter off" },
              { id: "lowpass", label: "Low-pass" },
              { id: "highpass", label: "High-pass" },
            ]}
          />
          {params.filter_mode !== "off" ? (
            <Fader label="Cutoff" value={params.filter_hz} min={40} max={16000} step={10} reset={1000} format={(v) => `${v} Hz`} onChange={(v) => patch({ filter_hz: v })} />
          ) : null}
          <Fader label="Pitch (key)" value={params.pitch} min={-6} max={6} step={0.5} format={(v) => `${v > 0 ? "+" : ""}${v} st`} onChange={(v) => patch({ pitch: v })} />
        </div>
      </Panel>

      <Panel title="Dub FX" hint="Echo and reverb ring out after drop-outs">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Toggle on={params.echo} onChange={(v) => patch({ echo: v })}>Echo</Toggle>
            {params.echo ? (
              <Segmented
                label="Echo length"
                value={params.echo_division}
                onChange={(v) => patch({ echo_division: v })}
                options={[
                  { id: "1/8", label: "1/8" },
                  { id: "1/4", label: "1/4" },
                  { id: "3/8", label: "3/8" },
                  { id: "1/2", label: "1/2" },
                  { id: "1", label: "1" },
                ]}
              />
            ) : null}
          </div>
          {params.echo ? (
            <>
              <Fader label="Feedback" value={params.echo_feedback} min={0} max={0.85} step={0.05} reset={0.45} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ echo_feedback: v })} />
              <Fader label="Echo level" value={params.echo_mix} min={0} max={1} step={0.05} reset={0.4} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ echo_mix: v })} />
            </>
          ) : null}
          <Fader label="Reverb" value={params.reverb} min={0} max={1} step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ reverb: v })} />

          <div className="space-y-2 border-t border-border pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={addDrop}>
                <VolumeX className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" /> Drop-out at playhead
              </Button>
              <Segmented
                label="Drop length in beats"
                value={dropBeats}
                onChange={setDropBeats}
                options={DROP_BEATS.map((b) => ({ id: b, label: `${b} beat${b === "1" ? "" : "s"}` }))}
              />
            </div>
            {params.drops.length === 0 ? (
              <p className="text-xs text-muted-foreground">Drop-outs mute the track so the echo rings alone, the classic dub moment.</p>
            ) : (
              <ul className="space-y-1">
                {params.drops.map((d, i) => (
                  <li key={`${d.at}-${i}`} className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-1.5 text-xs">
                    <span className="tabular-nums">
                      {formatDuration(d.at)} · {d.beats} beat{d.beats === 1 ? "" : "s"} ({(d.beats * beatSeconds).toFixed(1)}s)
                    </span>
                    <button type="button" onClick={() => patch({ drops: params.drops.filter((_, j) => j !== i) })} aria-label="Remove drop-out" className="text-muted-foreground hover:text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Panel>

      <Panel title="Cut" hint="Only the bright part of the waveform is pressed" className="lg:col-span-2">
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => patch({ start: Math.min(cursor, end - 2) })}>
            <Scissors className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" /> Start here
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground">
            {formatDuration(params.start)} to {formatDuration(end)} ({formatDuration(end - params.start)})
          </span>
          <Button size="sm" variant="outline" onClick={() => patch({ end: Math.max(cursor, params.start + 2) })}>
            <Scissors className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" /> End here
          </Button>
          <Button size="sm" variant="ghost" onClick={() => patch({ start: 0, end: null })}>Whole song</Button>
          <div className="ml-auto grid w-full gap-3 sm:w-auto sm:grid-cols-2">
            <Fader label="Fade in" value={params.fade_in} min={0} max={10} step={0.5} unit=" s" onChange={(v) => patch({ fade_in: v })} />
            <Fader label="Fade out" value={params.fade_out} min={0} max={15} step={0.5} unit=" s" reset={2} onChange={(v) => patch({ fade_out: v })} />
          </div>
        </div>
      </Panel>
    </div>
  );
}
