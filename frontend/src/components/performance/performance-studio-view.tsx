"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioLines, Clapperboard, Film, ImagePlus, Loader2, Music2, Pause, Play, Plus, Trash2, Users, Wand2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { confirmDialog } from "@/components/ui/confirm-host";
import { LoadError } from "@/components/ui/load-error";
import { ApiError, assetUrl } from "@/lib/api/core";
import {
  clock,
  performancesApi,
  STATE_STYLE,
  VOICED,
  type CameraShot,
  type Performance,
  type PerformanceMode,
  type Performer,
  type PerformerState,
  type Region,
  type ShotKind,
} from "@/lib/api/performances";
import { cn } from "@/lib/utils";

const MODES: { id: PerformanceMode; label: string; hint: string }[] = [
  { id: "alternating", label: "A · Alternating verses", hint: "One sings, the other listens and reacts" },
  { id: "call_response", label: "B · Call & response", hint: "Phrases answer each other" },
  { id: "harmony", label: "C · Duet harmony", hint: "Both sing, each from their own stem" },
  { id: "lead_background", label: "D · Lead & backing", hint: "Second singer only on backing parts" },
  { id: "shared_stage", label: "E · Shared stage", hint: "Free, independent stage performance" },
];
const STATES = Object.keys(STATE_STYLE) as PerformerState[];
const SHOTS: ShotKind[] = ["wide", "two_shot", "close_up"];
const glass = "rounded-2xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl";
const POLL_MS = 3000;

function stateAt(p: Performer, all: Performer[], t: number): PerformerState {
  const own = p.regions.find((r) => r.start <= t && t < r.end);
  if (own) return own.state;
  return all.some((o) => o.id !== p.id && o.regions.some((r) => r.start <= t && t < r.end && VOICED.includes(r.state)))
    ? "LISTENING"
    : "IDLE";
}

function message(err: unknown) {
  return err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong.";
}

function FilePick({ label, accept, onFile, icon: Icon, done }: { label: string; accept: string; onFile: (f: File) => void; icon: typeof Music2; done?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      <Button variant="outline" size="sm" onClick={() => ref.current?.click()} className={cn("gap-2", done && "border-emerald-400/40 text-emerald-200")}>
        <Icon className="h-4 w-4" /> {label}
      </Button>
    </>
  );
}

type Drag = { pid: string; rid: string; mode: "move" | "start" | "end"; x0: number; orig: Region };

function Timeline({ project, time, onSeek, onRegions, selected, onSelect, onCamera }: {
  project: Performance;
  time: number;
  onSeek: (t: number) => void;
  onRegions: (pid: string, regions: Region[], commit: boolean) => void;
  selected: { pid: string; rid: string } | null;
  onSelect: (s: { pid: string; rid: string } | null) => void;
  onCamera: (index: number) => void;
}) {
  const lanes = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const dur = Math.max(project.duration, 1);
  const pct = (t: number) => `${(t / dur) * 100}%`;
  const secPerPx = () => dur / (lanes.current?.clientWidth || 1);
  const names = Object.fromEntries(project.performers.map((p) => [p.id, p.name]));

  const onMove = useCallback((e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = project.performers.find((x) => x.id === d.pid);
    if (!p) return;
    const dt = (e.clientX - d.x0) * secPerPx();
    const others = p.regions.filter((r) => r.id !== d.rid);
    const lo = Math.max(0, ...others.filter((r) => r.end <= d.orig.start + 1e-6).map((r) => r.end));
    const hi = Math.min(dur, ...others.filter((r) => r.start >= d.orig.end - 1e-6).map((r) => r.start));
    let { start, end } = d.orig;
    if (d.mode === "move") {
      const len = end - start;
      start = Math.min(Math.max(lo, start + dt), hi - len);
      end = start + len;
    } else if (d.mode === "start") start = Math.min(Math.max(lo, start + dt), end - 0.1);
    else end = Math.max(Math.min(hi, end + dt), start + 0.1);
    const regions = p.regions.map((r) => (r.id === d.rid ? { ...r, start: +start.toFixed(3), end: +end.toFixed(3), manual: true } : r));
    onRegions(d.pid, regions, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, dur, onRegions]);

  useEffect(() => {
    const up = () => {
      const d = drag.current;
      if (!d) return;
      drag.current = null;
      const p = project.performers.find((x) => x.id === d.pid);
      if (p) onRegions(d.pid, p.regions, true);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", onMove); window.removeEventListener("pointerup", up); };
  }, [onMove, onRegions, project]);

  const start = (e: React.PointerEvent, pid: string, r: Region, mode: Drag["mode"]) => {
    e.stopPropagation();
    onSelect({ pid, rid: r.id });
    drag.current = { pid, rid: r.id, mode, x0: e.clientX, orig: r };
  };

  const addAt = (e: React.MouseEvent, p: Performer) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = ((e.clientX - box.left) / box.width) * dur;
    if (p.regions.some((r) => r.start <= t && t < r.end)) return;
    const next = Math.min(dur, ...p.regions.filter((r) => r.start > t).map((r) => r.start));
    const region: Region = { id: Math.random().toString(36).slice(2, 12), start: +t.toFixed(3), end: +Math.min(t + 2, next).toFixed(3),
      state: p.stem_url ? "SINGING" : "MOVING", intensity: 0.6, lyric: "", source: "own", manual: true };
    onRegions(p.id, [...p.regions, region].sort((a, b) => a.start - b.start), true);
    onSelect({ pid: p.id, rid: region.id });
  };

  return (
    <div className={cn(glass, "p-4")}>
      <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
        <span>Drag to move · drag edges to trim · double-click a lane to add · click the ruler to seek</span>
        <span className="tabular-nums">{clock(time)} / {clock(project.duration)}</span>
      </div>
      <div className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2">
        <div />
        <div className="relative h-6 cursor-pointer rounded-md bg-white/[0.03]" onClick={(e) => { const b = e.currentTarget.getBoundingClientRect(); onSeek(((e.clientX - b.left) / b.width) * dur); }}>
          {Array.from({ length: Math.floor(dur / 10) + 1 }, (_, i) => (
            <span key={i} className="absolute top-0 h-full border-l border-white/10 pl-1 text-[10px] text-muted-foreground" style={{ left: pct(i * 10) }}>{clock(i * 10).replace(/\.\d$/, "")}</span>
          ))}
        </div>
        {project.performers.map((p) => {
          const live = stateAt(p, project.performers, time);
          return (
            <div key={p.id} className="contents">
              <div className="flex flex-col justify-center">
                <span className="truncate text-sm font-medium">{p.name}</span>
                <span className={cn("mt-0.5 w-fit rounded-full border px-2 text-[10px] uppercase tracking-wide", STATE_STYLE[live].className)}>{STATE_STYLE[live].label}</span>
              </div>
              <div ref={lanes} className="relative h-12 rounded-lg bg-white/[0.03] ring-1 ring-white/5" onDoubleClick={(e) => addAt(e, p)}>
                {p.regions.map((r) => (
                  <div key={r.id} title={`${STATE_STYLE[r.state].label} ${clock(r.start)}–${clock(r.end)}${r.lyric ? ` · ${r.lyric}` : ""}`}
                    onPointerDown={(e) => start(e, p.id, r, "move")}
                    className={cn("absolute inset-y-1 cursor-grab touch-none select-none overflow-hidden rounded-md border text-[10px] leading-[2.5rem] text-white/90 active:cursor-grabbing",
                      STATE_STYLE[r.state].className, selected?.rid === r.id && "ring-2 ring-white/80")}
                    style={{ left: pct(r.start), width: pct(r.end - r.start) }}>
                    <span className="absolute inset-y-0 left-0 w-1.5 cursor-ew-resize" onPointerDown={(e) => start(e, p.id, r, "start")} />
                    <span className="px-2">{r.lyric || STATE_STYLE[r.state].label}</span>
                    <span className="absolute inset-y-0 right-0 w-1.5 cursor-ew-resize" onPointerDown={(e) => start(e, p.id, r, "end")} />
                  </div>
                ))}
                <div className="pointer-events-none absolute inset-y-0 w-px bg-white" style={{ left: pct(time) }} />
              </div>
            </div>
          );
        })}
        <div className="flex items-center gap-1.5 text-sm font-medium"><Clapperboard className="h-4 w-4" /> Camera</div>
        <div className="relative h-9 rounded-lg bg-white/[0.03] ring-1 ring-white/5">
          {project.camera.map((s, i) => (
            <button key={i} type="button" onClick={() => onCamera(i)} title="Click to change the shot"
              className="absolute inset-y-1 overflow-hidden rounded-md border border-white/15 bg-white/[0.08] px-2 text-left text-[10px] text-white/80 hover:bg-white/15"
              style={{ left: pct(s.start), width: pct(s.end - s.start) }}>
              {s.shot.replace("_", " ")}{s.focus ? ` · ${names[s.focus]}` : ""}
            </button>
          ))}
          <div className="pointer-events-none absolute inset-y-0 w-px bg-white" style={{ left: pct(time) }} />
        </div>
      </div>
    </div>
  );
}

function Editor({ id, onClose }: { id: string; onClose: () => void }) {
  const [project, setProject] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<{ pid: string; rid: string } | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const audio = useRef<HTMLAudioElement>(null);

  const load = useCallback(async () => {
    try { setProject(await performancesApi.get(id)); setError(null); } catch (err) { setError(message(err)); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { performancesApi.readiness().then((r) => setMissing(r.missing)).catch(() => setMissing([])); }, []);

  const rendering = project?.render && ["queued", "running"].includes(project.render.status);
  useEffect(() => {
    if (!rendering) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [rendering, load]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => { if (audio.current) setTime(audio.current.currentTime); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const run = async (label: string, fn: () => Promise<Performance | void>) => {
    setBusy(label);
    setError(null);
    try { const next = await fn(); if (next) setProject(next); } catch (err) { setError(message(err)); await load(); } finally { setBusy(null); }
  };

  const onRegions = useCallback((pid: string, regions: Region[], commit: boolean) => {
    setProject((prev) => prev && { ...prev, performers: prev.performers.map((p) => (p.id === pid ? { ...p, regions } : p)) });
    if (commit) void run("Saving", () => performancesApi.putRegions(id, pid, regions.map(({ manual: _m, ...r }) => r)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const seek = (t: number) => { if (audio.current) audio.current.currentTime = t; setTime(t); };

  const cycleShot = (i: number) => {
    if (!project) return;
    const performers = project.performers;
    const current = project.camera[i];
    const options: CameraShot[] = [
      ...SHOTS.filter((s) => s !== "close_up").map((shot) => ({ ...current, shot, focus: null })),
      ...performers.map((p) => ({ ...current, shot: "close_up" as ShotKind, focus: p.id })),
    ];
    const at = options.findIndex((o) => o.shot === current.shot && o.focus === current.focus);
    const camera = project.camera.map((s, k) => (k === i ? options[(at + 1) % options.length] : s));
    void run("Saving", () => performancesApi.patch(id, { camera }));
  };

  const sel = useMemo(() => {
    if (!project || !selected) return null;
    const p = project.performers.find((x) => x.id === selected.pid);
    const r = p?.regions.find((x) => x.id === selected.rid);
    return p && r ? { p, r } : null;
  }, [project, selected]);

  if (error && !project) return <LoadError what="this performance" message={error} onRetry={load} />;
  if (!project) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const render = project.render;
  const hasStems = project.performers.some((p) => p.stem_url);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Back to performances"><X className="h-5 w-5" /></Button>
        <Input className="h-11 max-w-sm text-lg font-semibold" defaultValue={project.title}
          onBlur={(e) => e.target.value.trim() && e.target.value !== project.title && void run("Saving", () => performancesApi.patch(id, { title: e.target.value }))} />
        <select className="h-11 rounded-xl border border-white/10 bg-white/[0.04] px-3 text-sm" value={project.mode}
          onChange={(e) => void run("Switching mode", () => performancesApi.patch(id, { mode: e.target.value as PerformanceMode }))}>
          {MODES.map((m) => <option key={m.id} value={m.id} className="bg-neutral-900">{m.label}</option>)}
        </select>
        <span className="text-xs text-muted-foreground">{MODES.find((m) => m.id === project.mode)?.hint}</span>
        {busy ? <span className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{busy}…</span> : null}
      </div>
      {error ? <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive-foreground">{error}</p> : null}

      <div className={cn(glass, "flex flex-wrap items-center gap-3 p-4")}>
        <Music2 className="h-5 w-5 text-fuchsia-300" />
        <span className="text-sm font-medium">Master song</span>
        <FilePick label={project.master_audio_url ? "Replace song" : "Upload song"} accept="audio/*" icon={Music2} done={!!project.master_audio_url}
          onFile={(f) => void run("Uploading the song", () => performancesApi.uploadMaster(id, f))} />
        {project.master_audio_url ? (
          <>
            <audio ref={audio} src={assetUrl(project.master_audio_url) ?? undefined} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)} onTimeUpdate={(e) => !playing && setTime(e.currentTarget.currentTime)} preload="auto" />
            <Button variant="outline" size="sm" className="gap-2" onClick={() => (playing ? audio.current?.pause() : void audio.current?.play())}>
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}{playing ? "Pause" : "Play"}
            </Button>
          </>
        ) : null}
        <FilePick label="Stage picture (optional)" accept="image/*" icon={ImagePlus} done={!!project.stage.image_url}
          onFile={(f) => void run("Uploading the stage", () => performancesApi.uploadStage(id, f))} />
        <Button size="sm" className="ml-auto gap-2" disabled={!hasStems || !!busy}
          onClick={() => void run("Finding each voice", () => performancesApi.analyze(id))}>
          <Wand2 className="h-4 w-4" /> Detect each singer&apos;s parts
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {project.performers.map((p) => (
          <div key={p.id} className={cn(glass, "flex gap-4 p-4")}>
            <div className="h-28 w-20 shrink-0 overflow-hidden rounded-xl bg-white/5">
              {p.identity_url ? <img src={assetUrl(p.identity_url) ?? undefined} alt={p.name} className="h-full w-full object-cover" />
                : <Users className="m-auto mt-10 h-6 w-6 text-muted-foreground" />}
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <Input className="h-9" defaultValue={p.name}
                onBlur={(e) => e.target.value.trim() && e.target.value !== p.name && void run("Saving", () => performancesApi.patchPerformer(id, p.id, { name: e.target.value.trim() }))} />
              <div className="flex flex-wrap gap-2">
                <FilePick label="Identity" accept="image/*" icon={ImagePlus} done={!!p.identity_url}
                  onFile={(f) => void run("Uploading the picture", () => performancesApi.uploadIdentity(id, p.id, f))} />
                <FilePick label="Vocal stem" accept="audio/*" icon={AudioLines} done={!!p.stem_url}
                  onFile={(f) => void run("Uploading the stem", () => performancesApi.uploadStem(id, p.id, f))} />
              </div>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Stage
                <input type="range" min={0.05} max={0.95} step={0.01} defaultValue={p.stage.x} className="flex-1 accent-fuchsia-400"
                  onPointerUp={(e) => void run("Saving", () => performancesApi.patchPerformer(id, p.id, { stage: { ...p.stage, x: +e.currentTarget.value } }))} />
                {p.stage.x < 0.4 ? "left" : p.stage.x > 0.6 ? "right" : "centre"}
              </label>
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer py-1">Performance direction</summary>
                <div className="space-y-2 pt-2">
                  {(["head", "shoulders", "hands", "sway", "energy"] as const).map((control) => (
                    <label key={control} className="flex items-center gap-2 capitalize">
                      <span className="w-20">{control}</span>
                      <input aria-label={`${p.name} ${control}`} type="range" min={0} max={1} step={0.05}
                        defaultValue={p.motion[control] ?? 0.5} className="min-w-0 flex-1 accent-fuchsia-400"
                        onBlur={(e) => void run("Saving direction", () => performancesApi.patchPerformer(id, p.id, { motion: { [control]: +e.target.value } }))} />
                    </label>
                  ))}
                  <label className="flex items-center justify-between gap-2">Expression
                    <select className="rounded border bg-background p-1" value={p.motion.expression ?? "natural"}
                      onChange={(e) => void run("Saving expression", () => performancesApi.patchPerformer(id, p.id, { motion: { expression: e.target.value as NonNullable<typeof p.motion.expression> } }))}>
                      {["natural", "joyful", "intense", "tender", "restrained"].map((v) => <option key={v}>{v}</option>)}
                    </select>
                  </label>
                  <label className="flex items-center justify-between gap-2">Gaze
                    <select className="rounded border bg-background p-1" value={p.motion.gaze ?? "automatic"}
                      onChange={(e) => void run("Saving gaze", () => performancesApi.patchPerformer(id, p.id, { motion: { gaze: e.target.value as NonNullable<typeof p.motion.gaze> } }))}>
                      {["automatic", "audience", "partner", "left", "right"].map((v) => <option key={v}>{v}</option>)}
                    </select>
                  </label>
                  <p>Directions guide the model. Check the rendered movement and lip timing.</p>
                  {project.render_strategy === "independent_layers" ? (
                    <Button variant="outline" size="sm" disabled={!!rendering || !!busy}
                      onClick={() => void run(`Rendering a new take for ${p.name}`, async () => {
                        await performancesApi.patchPerformer(id, p.id, { motion: { seed: Math.floor(Math.random() * 2 ** 31) } });
                        return performancesApi.render(id);
                      })}>New take for {p.name}</Button>
                  ) : null}
                </div>
              </details>
            </div>
          </div>
        ))}
      </div>

      {project.duration > 0 ? (
        <Timeline project={project} time={time} onSeek={seek} onRegions={onRegions} selected={selected} onSelect={setSelected} onCamera={cycleShot} />
      ) : (
        <p className={cn(glass, "p-6 text-sm text-muted-foreground")}>Upload the master song to open the timeline.</p>
      )}

      {sel ? (
        <div className={cn(glass, "flex flex-wrap items-center gap-3 p-4 text-sm")}>
          <span className="font-medium">{sel.p.name}</span>
          <span className="tabular-nums text-muted-foreground">{clock(sel.r.start)}–{clock(sel.r.end)}</span>
          <select className="h-9 rounded-lg border border-white/10 bg-white/[0.04] px-2" value={sel.r.state}
            onChange={(e) => onRegions(sel.p.id, sel.p.regions.map((r) => (r.id === sel.r.id ? { ...r, state: e.target.value as PerformerState, manual: true } : r)), true)}>
            {STATES.map((s) => <option key={s} value={s} className="bg-neutral-900">{STATE_STYLE[s].label}</option>)}
          </select>
          <Input className="h-9 max-w-xs" placeholder="Lyric (optional)" defaultValue={sel.r.lyric} key={sel.r.id}
            onBlur={(e) => e.target.value !== sel.r.lyric && onRegions(sel.p.id, sel.p.regions.map((r) => (r.id === sel.r.id ? { ...r, lyric: e.target.value } : r)), true)} />
          <Button variant="ghost" size="sm" className="gap-2 text-destructive" onClick={() => { onRegions(sel.p.id, sel.p.regions.filter((r) => r.id !== sel.r.id), true); setSelected(null); }}>
            <Trash2 className="h-4 w-4" /> Remove
          </Button>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_minmax(0,28rem)]">
        <div className={cn(glass, "overflow-x-auto p-4")}>
          <h2 className="mb-3 text-sm font-semibold">Director sheet</h2>
          {project.sheet.length ? (
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr><th className="py-1 pr-3">Time</th>{project.performers.map((p) => <th key={p.id} className="py-1 pr-3">{p.name}</th>)}<th className="py-1">Camera</th></tr>
              </thead>
              <tbody>
                {project.sheet.map((row) => (
                  <tr key={row.start} className="cursor-pointer border-t border-white/5 hover:bg-white/[0.03]" onClick={() => seek(row.start)}>
                    <td className="py-1.5 pr-3 tabular-nums">{clock(row.start)}–{clock(row.end)}</td>
                    {project.performers.map((p) => {
                      const s = row.performers[p.name];
                      return <td key={p.id} className="py-1.5 pr-3"><span className={cn("rounded-full border px-2 py-0.5", STATE_STYLE[s].className)}>{STATE_STYLE[s].label}</span></td>;
                    })}
                    <td className="py-1.5 capitalize">{row.camera}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-sm text-muted-foreground">The sheet appears once the song is in.</p>}
        </div>

        <div className={cn(glass, "space-y-3 p-4")}>
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Film className="h-4 w-4" /> Render</h2>
          {missing.length ? <p className="text-xs text-amber-200">Model files still missing: {missing.join(", ")}</p> : null}
          {render?.video_url && render.status === "done" ? (
            <video src={assetUrl(render.video_url) ?? undefined} controls className="w-full rounded-xl" />
          ) : null}
          {render ? (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs"><span>{render.stage}</span><span className="tabular-nums">{Math.round(render.progress * 100)}%</span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-gradient-to-r from-fuchsia-400 to-violet-400 transition-[width]" style={{ width: `${render.progress * 100}%` }} /></div>
              {render.error ? <p className="text-xs text-destructive">{render.error}</p> : null}
            </div>
          ) : <p className="text-xs text-muted-foreground">Render locally with Wan 2.1 + InfiniteTalk, using each performer&apos;s assigned vocal audio. Review the result for lip timing and identity consistency.</p>}
          <label className="block text-xs text-muted-foreground">Rendering approach
            <select className="mt-1 w-full rounded-lg border bg-background p-2" value={project.render_strategy ?? "shared_pass"}
              disabled={!!rendering || !!busy}
              onChange={(e) => void run("Saving render approach", () => performancesApi.patch(id, { render_strategy: e.target.value as Performance["render_strategy"] }))}>
              <option value="shared_pass">Shared scene — one or two performers</option>
              <option value="independent_layers">Independent layers — reuse unchanged performers</option>
            </select>
          </label>
          {project.render_strategy === "independent_layers" ? <p className="text-xs text-muted-foreground">Each performer renders separately into a stage zone. Unchanged passes are reused. Zone boundaries and lighting need visual review.</p> : null}
          <div className="flex gap-2">
            <Button className="flex-1 gap-2" disabled={!!rendering || !!busy} onClick={() => void run("Starting the render", () => performancesApi.render(id))}>
              <Film className="h-4 w-4" /> {render?.status === "done" ? "Render again" : "Render video"}
            </Button>
            {rendering ? <Button variant="outline" onClick={() => void performancesApi.cancelRender(id).then(load)}>Cancel</Button> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export function PerformanceStudioView() {
  const [items, setItems] = useState<Performance[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [names, setNames] = useState("Singer A, Singer B");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await performancesApi.list()); setError(null); } catch (err) { setError(message(err)); }
  }, []);
  useEffect(() => {
    void load();
    const fromUrl = new URLSearchParams(window.location.search).get("id");
    if (fromUrl) setOpen(fromUrl);
  }, [load]);

  const show = (id: string | null) => {
    setOpen(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("id", id); else url.searchParams.delete("id");
    window.history.replaceState(null, "", url);
    if (!id) void load();
  };

  const create = async () => {
    const performers = names.split(",").map((n) => n.trim()).filter(Boolean);
    setCreating(true);
    try { const p = await performancesApi.create("", performers, "alternating"); show(p.id); } catch (err) { setError(message(err)); } finally { setCreating(false); }
  };

  if (open) return <Editor id={open} onClose={() => show(null)} />;

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-[-0.025em] md:text-3xl">Dual Performance Studio</h1>
        <p className="mt-2 text-sm text-muted-foreground">Direct a duet on one stage with separate vocal assignments and performer states. The timeline supports larger casts; video rendering currently supports two performers. Review silent reactions and lip timing in the rendered preview.</p>
      </header>
      <div className={cn(glass, "flex flex-wrap items-end gap-3 p-4")}>
        <label className="min-w-[16rem] flex-1 text-xs text-muted-foreground">
          Performers (comma separated)
          <Input className="mt-1" value={names} onChange={(e) => setNames(e.target.value)} />
        </label>
        <Button className="gap-2" disabled={creating} onClick={() => void create()}>
          {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} New performance
        </Button>
      </div>
      {error ? <LoadError what="your performances" message={error} onRetry={load} /> : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items?.map((p) => (
          <div key={p.id} className={cn(glass, "group flex flex-col gap-3 p-4 transition hover:bg-white/[0.07]")}>
            <button type="button" className="text-left" onClick={() => show(p.id)}>
              <span className="block truncate font-medium">{p.title}</span>
              <span className="text-xs text-muted-foreground">
                {p.performers.map((x) => x.name).join(" · ")} · {MODES.find((m) => m.id === p.mode)?.label.split(" · ")[1]} · {clock(p.duration)}
              </span>
              {p.render?.status ? <span className="mt-1 block text-xs capitalize text-fuchsia-200">{p.render.status}</span> : null}
            </button>
            <Button variant="ghost" size="sm" className="w-fit gap-2 text-muted-foreground opacity-0 group-hover:opacity-100"
              onClick={async () => { if (await confirmDialog(`Delete "${p.title}" and its files?`)) { await performancesApi.remove(p.id); void load(); } }}>
              <Trash2 className="h-4 w-4" /> Delete
            </Button>
          </div>
        ))}
        {items && !items.length ? <p className="text-sm text-muted-foreground">No performances yet.</p> : null}
      </div>
    </div>
  );
}
