"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Download, Image as ImageIcon, Loader2, Music2, RotateCcw, Save, Sparkles, Trash2, Upload, Video } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, assetUrl } from "@/lib/api/core";
import {
  enhanceApi,
  kindOfName,
  type EnhanceJob,
  type EnhanceOperation,
  type EnhanceOpInput,
  type EnhancePreset,
  type MediaKind,
} from "@/lib/api/enhance";
import { cn } from "@/lib/utils";

const glass = "rounded-2xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl";
const KIND_ICON = { image: ImageIcon, audio: Music2, video: Video } as const;
const POLL_MS = 1200;

function message(err: unknown) {
  return err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong.";
}

/** Drag the divider to compare the original (left) with the enhanced version (right). */
function ImageCompare({ before, after }: { before: string; after: string }) {
  const [split, setSplit] = useState(50);
  const box = useRef<HTMLDivElement>(null);
  const move = (clientX: number) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setSplit(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)));
  };
  return (
    <div ref={box} className="relative select-none overflow-hidden rounded-xl bg-black/40"
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); move(e.clientX); }}
      onPointerMove={(e) => e.buttons && move(e.clientX)}>
      <img src={after} alt="Enhanced" className="block w-full" draggable={false} />
      <img src={before} alt="Original" className="absolute inset-0 h-full w-full object-contain" draggable={false}
        style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }} />
      <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/90 shadow-[0_0_12px_rgba(255,255,255,0.6)]" style={{ left: `${split}%` }} />
      <span className="absolute left-3 top-3 rounded-full bg-black/60 px-2 py-0.5 text-[11px]">Original</span>
      <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2 py-0.5 text-[11px]">Enhanced</span>
    </div>
  );
}

/** A/B a time-based medium: one transport, switch which version you hear/see without losing your place. */
function MediaCompare({ kind, before, after }: { kind: "audio" | "video"; before: string; after: string }) {
  const [side, setSide] = useState<"before" | "after">("after");
  const a = useRef<HTMLMediaElement | null>(null);
  const b = useRef<HTMLMediaElement | null>(null);
  const flip = (next: "before" | "after") => {
    const from = side === "before" ? a.current : b.current;
    const to = next === "before" ? a.current : b.current;
    if (from && to && from !== to) {
      to.currentTime = from.currentTime;
      if (!from.paused) { void to.play(); from.pause(); }
    }
    setSide(next);
  };
  const Tag = kind === "video" ? "video" : "audio";
  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-full border border-white/10 bg-white/5 p-1 text-xs">
        {(["before", "after"] as const).map((s) => (
          <button key={s} type="button" onClick={() => flip(s)}
            className={cn("rounded-full px-3 py-1.5 transition", side === s ? "bg-white/15 text-white" : "text-muted-foreground")}>
            {s === "before" ? "Original" : "Enhanced"}
          </button>
        ))}
      </div>
      <Tag ref={(el: HTMLMediaElement | null) => { a.current = el; }} src={before} controls className={cn("w-full rounded-xl", side !== "before" && "hidden")} />
      <Tag ref={(el: HTMLMediaElement | null) => { b.current = el; }} src={after} controls className={cn("w-full rounded-xl", side !== "after" && "hidden")} />
    </div>
  );
}

export function EnhanceView() {
  const [ops, setOps] = useState<EnhanceOperation[]>([]);
  const [presets, setPresets] = useState<EnhancePreset[]>([]);
  const [history, setHistory] = useState<EnhanceJob[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [libraryUrl, setLibraryUrl] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, Record<string, number>>>({});
  const [job, setJob] = useState<EnhanceJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [presetName, setPresetName] = useState("");
  const picker = useRef<HTMLInputElement>(null);

  const kind: MediaKind | null = file ? kindOfName(file.name) : libraryUrl ? kindOfName(libraryUrl) : job?.kind ?? null;
  const forKind = useMemo(() => ops.filter((o) => kind && o.kinds.includes(kind)), [ops, kind]);

  const refresh = useCallback(async () => {
    try {
      const [o, p, h] = await Promise.all([enhanceApi.operations(), enhanceApi.presets(), enhanceApi.jobs()]);
      setOps(o.operations); setPresets(p); setHistory(h);
    } catch (err) { setError(message(err)); }
  }, []);
  useEffect(() => {
    void refresh();
    const url = new URLSearchParams(window.location.search).get("url");
    if (url?.startsWith("/storage/")) setLibraryUrl(url); // contextual "Enhance" links from other studios
  }, [refresh]);

  const busy = job && ["queued", "running"].includes(job.status);
  useEffect(() => {
    if (!busy || !job) return;
    const t = window.setInterval(async () => {
      try {
        const next = await enhanceApi.job(job.id);
        setJob(next);
        if (!["queued", "running"].includes(next.status)) void refresh();
      } catch (err) { setError(message(err)); }
    }, POLL_MS);
    return () => window.clearInterval(t);
  }, [busy, job, refresh]);

  const pick = (f: File) => {
    if (!kindOfName(f.name)) { setError("That file type is not supported. Use an image, audio or video file."); return; }
    setFile(f); setLibraryUrl(null); setJob(null); setChosen({}); setError(null);
  };

  const toggle = (op: EnhanceOperation) => {
    if (!op.available) return;
    setChosen((prev) => {
      const next = { ...prev };
      if (next[op.id]) delete next[op.id];
      else next[op.id] = Object.fromEntries(op.params.map((p) => [p.id, p.default]));
      return next;
    });
  };

  const selection: EnhanceOpInput[] = forKind.filter((o) => chosen[o.id]).map((o) => ({ op: o.id, params: chosen[o.id] }));

  const run = async () => {
    setError(null);
    try {
      setJob(file ? await enhanceApi.upload(file, selection) : libraryUrl ? await enhanceApi.fromLibrary(libraryUrl, selection) : null);
    } catch (err) { setError(message(err)); }
  };

  const loadPreset = (p: EnhancePreset) => {
    setChosen(Object.fromEntries(p.ops.map((o) => [o.op, o.params])));
  };

  const savePreset = async () => {
    if (!kind || !presetName.trim() || !selection.length) return;
    try { setPresets(await enhanceApi.savePreset(presetName.trim(), kind, selection)); setPresetName(""); } catch (err) { setError(message(err)); }
  };

  const output = job?.status === "done" ? job.outputs[0] : null;
  const KindIcon = kind ? KIND_ICON[kind] : Sparkles;

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-[-0.025em] md:text-3xl">AI Enhance</h1>
        <p className="mt-2 text-sm text-muted-foreground">One place to enhance any image, audio track or video: select, enhance, compare, adjust, apply. Originals are never changed; every result is a new version.</p>
      </header>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <section className="min-w-0 space-y-4">
          <div className={cn(glass, "flex min-h-[9rem] flex-col items-center justify-center gap-3 border-dashed p-6 text-center")}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) pick(f); }}>
            <input ref={picker} type="file" className="hidden" accept="image/*,audio/*,video/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); e.target.value = ""; }} />
            <KindIcon className="h-7 w-7 text-fuchsia-300" />
            <p className="max-w-full break-all text-sm">{file?.name ?? libraryUrl?.split("/").pop() ?? "Drop an image, audio track or video here"}</p>
            <Button variant="outline" size="sm" className="gap-2" onClick={() => picker.current?.click()}><Upload className="h-4 w-4" /> Choose media</Button>
          </div>

          {error ? <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm">{error}</p> : null}

          {job ? (
            <div className={cn(glass, "space-y-4 p-4")}>
              <div className="flex items-start justify-between gap-3 text-sm">
                <span className="min-w-0 break-words font-medium">{job.name}</span>
                <span className="shrink-0 capitalize text-muted-foreground">{job.status}{busy ? ` · ${Math.round(job.progress * 100)}%` : ""}</span>
              </div>
              {busy ? (
                <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full bg-gradient-to-r from-fuchsia-400 to-violet-400 transition-[width]" style={{ width: `${Math.max(4, job.progress * 100)}%` }} />
                </div>
              ) : null}
              {job.error ? <p className="text-sm text-destructive">{job.error}</p> : null}
              {output && job.kind === "image" ? <ImageCompare before={assetUrl(job.source_url)!} after={assetUrl(output.url)!} /> : null}
              {output && job.kind !== "image" && job.outputs.length === 1 ? (
                <MediaCompare kind={job.kind as "audio" | "video"} before={assetUrl(job.source_url)!} after={assetUrl(output.url)!} />
              ) : null}
              {job.status === "done" && job.outputs.length > 1 ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {job.outputs.map((o) => (
                    <div key={o.url} className="space-y-1.5"><p className="text-xs font-medium">{o.label}</p><audio src={assetUrl(o.url)!} controls className="w-full" /></div>
                  ))}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {busy ? <Button variant="outline" onClick={() => void enhanceApi.cancel(job.id)}>Cancel</Button> : null}
                {job.status === "done" ? (
                  <>
                    <Button className="gap-2" disabled={!!job.applied} onClick={async () => setJob(await enhanceApi.apply(job.id, 0))}>
                      <Check className="h-4 w-4" /> {job.applied ? "Applied" : "Apply this version"}
                    </Button>
                    {job.outputs.map((o) => (
                      <a key={o.url} href={assetUrl(o.url)!} download className="inline-flex h-11 items-center gap-2 rounded-xl border border-border px-3.5 text-xs hover:bg-muted">
                        <Download className="h-4 w-4" /> {o.label}
                      </a>
                    ))}
                    <Button variant="ghost" className="gap-2" onClick={() => setJob(null)}><RotateCcw className="h-4 w-4" /> Adjust & run again</Button>
                  </>
                ) : null}
              </div>
            </div>
          ) : null}

          {history.length ? (
            <div className={cn(glass, "p-4")}>
              <h2 className="mb-2 text-sm font-semibold">Recent</h2>
              <ul className="divide-y divide-white/5 text-sm">
                {history.slice(0, 12).map((h) => (
                  <li key={h.id} className="flex items-center gap-3 py-2">
                    <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => { setFile(null); setLibraryUrl(null); setJob(h); }}>{h.name}</button>
                    <span className="text-xs capitalize text-muted-foreground">{h.kind} · {h.status}{h.applied ? " · applied" : ""}</span>
                    <Button variant="ghost" size="icon" aria-label="Delete" onClick={async () => { await enhanceApi.remove(h.id); if (job?.id === h.id) setJob(null); void refresh(); }}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>

        <aside className={cn(glass, "min-w-0 h-fit space-y-4 p-4 xl:sticky xl:top-4")}>
          <h2 className="text-sm font-semibold">{kind ? `Enhance ${kind}` : "Choose media to see enhancements"}</h2>
          {kind && presets.some((p) => p.kind === kind) ? (
            <div className="flex flex-wrap gap-2">
              {presets.filter((p) => p.kind === kind).map((p) => (
                <span key={p.id} className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 pl-3 text-xs">
                  <button type="button" onClick={() => loadPreset(p)}>{p.name}</button>
                  <button type="button" aria-label={`Delete preset ${p.name}`} className="px-2 py-1 text-muted-foreground" onClick={async () => setPresets(await enhanceApi.deletePreset(p.id))}>×</button>
                </span>
              ))}
            </div>
          ) : null}
          <ul className="space-y-2">
            {forKind.map((op) => {
              const on = !!chosen[op.id];
              return (
                <li key={op.id} className={cn("rounded-xl border p-3 transition", on ? "border-fuchsia-300/40 bg-fuchsia-400/10" : "border-white/10", !op.available && "opacity-50")}>
                  <label className={cn("flex items-start gap-3 text-sm", op.available ? "cursor-pointer" : "cursor-not-allowed")}>
                    <input type="checkbox" className="mt-0.5 accent-fuchsia-400" checked={on} disabled={!op.available} onChange={() => toggle(op)} />
                    <span className="flex-1">
                      {op.label}
                      {!op.available ? <span className="block text-[11px] text-amber-200/80">{op.unavailable_reason}</span> : null}
                    </span>
                  </label>
                  {on ? op.params.map((p) => (
                    <label key={p.id} className="mt-2 flex items-center gap-2 pl-7 text-[11px] text-muted-foreground">
                      <span className="w-24 shrink-0">{p.label}</span>
                      <input type="range" min={p.min} max={p.max} step={p.step} value={chosen[op.id][p.id]} className="flex-1 accent-fuchsia-400"
                        onChange={(e) => setChosen((prev) => ({ ...prev, [op.id]: { ...prev[op.id], [p.id]: +e.target.value } }))} />
                      <span className="w-10 text-right tabular-nums">{chosen[op.id][p.id]}</span>
                    </label>
                  )) : null}
                </li>
              );
            })}
          </ul>
          {kind ? (
            <>
              <Button className="w-full gap-2" disabled={!selection.length || !!busy || (!file && !libraryUrl)} onClick={() => void run()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Enhance
              </Button>
              <div className="flex gap-2">
                <Input className="h-11" placeholder="Save as preset…" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
                <Button variant="outline" size="icon" aria-label="Save preset" disabled={!presetName.trim() || !selection.length} onClick={() => void savePreset()}>
                  <Save className="h-4 w-4" />
                </Button>
              </div>
            </>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
