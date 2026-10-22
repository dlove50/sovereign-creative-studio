"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Brush, Camera, Download, ImagePlus, Loader2, Package, Palette, Search, Sparkles, Wand2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadError } from "@/components/ui/load-error";
import { ApiError, assetUrl } from "@/lib/api/core";
import { enhanceApi } from "@/lib/api/enhance";
import { imageTemplatesApi, type ImageTemplate, type TemplateField, type TemplateRun } from "@/lib/api/image-templates";
import { cn } from "@/lib/utils";

const glass = "rounded-2xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] backdrop-blur-xl";
const POLL_MS = 2000;

// Each card gets an original gradient + icon by its first category (no third-party artwork).
const LOOK: Record<string, { icon: typeof Sparkles; gradient: string }> = {
  Trending: { icon: Sparkles, gradient: "from-fuchsia-500/40 via-violet-500/25 to-sky-500/20" },
  Edit: { icon: Wand2, gradient: "from-sky-500/35 via-indigo-500/25 to-violet-500/20" },
  "Product/Ads": { icon: Package, gradient: "from-amber-400/35 via-rose-500/25 to-fuchsia-500/20" },
  Photography: { icon: Camera, gradient: "from-emerald-400/30 via-teal-500/25 to-sky-500/20" },
  Creative: { icon: Palette, gradient: "from-pink-500/35 via-fuchsia-500/25 to-amber-400/20" },
  Tattoo: { icon: Brush, gradient: "from-zinc-200/20 via-violet-500/25 to-black/40" },
};

function message(err: unknown) {
  return err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong.";
}

function PictureField({ field, files, onChange }: { field: TemplateField; files: File[]; onChange: (f: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const max = field.kind === "images" ? field.max_images ?? 1 : 1;
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);
  return (
    <div>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" multiple={max > 1} className="hidden"
        onChange={(e) => { const picked = [...(e.target.files ?? [])]; onChange(max > 1 ? [...files, ...picked].slice(0, max) : picked.slice(0, 1)); e.target.value = ""; }} />
      <div className="flex flex-wrap gap-2">
        {previews.map((src, i) => (
          <div key={src} className="relative h-20 w-20 overflow-hidden rounded-xl border border-white/10">
            <img src={src} alt="" className="h-full w-full object-cover" />
            <button type="button" aria-label="Remove picture" onClick={() => onChange(files.filter((_, k) => k !== i))}
              className="absolute right-1 top-1 rounded-full bg-black/70 p-0.5"><X className="h-3 w-3" /></button>
          </div>
        ))}
        {files.length < max ? (
          <button type="button" onClick={() => input.current?.click()}
            className="flex h-20 min-w-[5rem] flex-1 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-white/15 text-[11px] text-muted-foreground hover:border-fuchsia-300/50 hover:text-foreground">
            <ImagePlus className="h-5 w-5" />{max > 1 ? `Add (${files.length}/${max})` : "Add picture"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function TemplatePanel({ template, onClose }: { template: ImageTemplate; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [pictures, setPictures] = useState<Record<string, File[]>>({});
  const [run, setRun] = useState<TemplateRun | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ready = template.fields.every((f) => !f.required || (f.kind === "image" || f.kind === "images" ? (pictures[f.id]?.length ?? 0) > 0 : !!values[f.id]?.trim()));

  useEffect(() => {
    if (!run) return;
    const timer = window.setInterval(async () => {
      try {
        if (run.kind === "generation") {
          const g = await imageTemplatesApi.generation(run.generation.id);
          setStatus(g.status);
          if (g.status === "completed") { setResult(g.file_url); window.clearInterval(timer); setBusy(false); }
          if (g.status === "failed") { setError(g.error || "The image could not be made."); window.clearInterval(timer); setBusy(false); }
        } else {
          const j = await enhanceApi.job(run.job.id);
          setStatus(j.status);
          if (j.status === "done") { setResult(j.outputs[0]?.url ?? null); window.clearInterval(timer); setBusy(false); }
          if (["error", "cancelled"].includes(j.status)) { setError(j.error || "Enhancement failed."); window.clearInterval(timer); setBusy(false); }
        }
      } catch (err) { setError(message(err)); window.clearInterval(timer); setBusy(false); }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [run]);

  const generate = async () => {
    setBusy(true); setError(null); setResult(null); setStatus("queued");
    try { setRun(await imageTemplatesApi.run(template.id, values, pictures)); } catch (err) { setError(message(err)); setBusy(false); }
  };

  const look = LOOK[template.categories[0]] ?? LOOK.Trending;
  const Icon = look.icon;
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={template.name}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cn(glass, "m-3 flex w-full max-w-md flex-col overflow-y-auto rounded-3xl bg-[hsl(236_30%_7%/0.85)] p-5")}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{template.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{template.description}</p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}><X className="h-5 w-5" /></Button>
        </div>
        <div className={cn("mb-5 flex aspect-[16/9] items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br", look.gradient)}>
          {result ? <img src={assetUrl(result) ?? undefined} alt="Result" className="h-full w-full object-contain" />
            : busy ? <Loader2 className="h-8 w-8 animate-spin text-white/80" /> : <Icon className="h-10 w-10 text-white/70" />}
        </div>
        <div className="space-y-4">
          {template.fields.map((f) => (
            <label key={f.id} className="block text-sm">
              <span className="font-medium">{f.label}{f.required ? <span className="text-fuchsia-300"> *</span> : null}</span>
              {f.hint ? <span className="mb-1.5 block text-xs text-muted-foreground">{f.hint}</span> : <span className="mb-1.5 block" />}
              {f.kind === "image" || f.kind === "images" ? (
                <PictureField field={f} files={pictures[f.id] ?? []} onChange={(files) => setPictures((p) => ({ ...p, [f.id]: files }))} />
              ) : f.kind === "select" ? (
                <select className="h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3" value={values[f.id] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.id]: e.target.value }))}>
                  <option value="" className="bg-neutral-900">Select an option</option>
                  {f.options?.map((o) => <option key={o} value={o} className="bg-neutral-900">{o}</option>)}
                </select>
              ) : (
                <Input value={values[f.id] ?? ""} placeholder={f.placeholder} maxLength={400}
                  onChange={(e) => setValues((v) => ({ ...v, [f.id]: e.target.value }))} />
              )}
            </label>
          ))}
        </div>
        {error ? <p role="alert" className="mt-4 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">{error}</p> : null}
        <div className="mt-5 flex gap-2">
          <Button className="flex-1 gap-2" disabled={!ready || busy} onClick={() => void generate()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {busy ? (status === "running" ? "Creating…" : "Waiting for the GPU…") : result ? "Generate again" : "Generate"}
          </Button>
          {result ? (
            <a href={assetUrl(result) ?? undefined} download className="inline-flex h-11 items-center gap-2 rounded-xl border border-border px-3.5 text-sm hover:bg-muted">
              <Download className="h-4 w-4" /> Save
            </a>
          ) : null}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          Runs locally on your GPU ({template.engine === "generate" ? "text-to-image" : template.engine === "enhance" ? "AI Enhance" : "Qwen Image Edit"}). Results are saved to your library.
        </p>
      </div>
    </div>
  );
}

export function ImageTemplatesView() {
  const [data, setData] = useState<{ categories: string[]; templates: ImageTemplate[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("All");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<ImageTemplate | null>(null);

  const load = useCallback(async () => {
    try { setData(await imageTemplatesApi.catalog()); setError(null); } catch (err) { setError(message(err)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.templates ?? []).filter((t) => (tab === "All" || t.categories.includes(tab)) &&
      (!q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)));
  }, [data, tab, query]);

  if (error) return <LoadError what="the templates" message={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-[-0.025em] md:text-3xl">Image Templates</h1>
        <p className="mt-2 text-sm text-muted-foreground">Pick a template, add your pictures, and generate. Everything runs locally on your GPU and lands in your library.</p>
      </header>
      <div className="flex flex-wrap items-center gap-3">
        <div className={cn(glass, "flex flex-wrap gap-1 p-1")} role="tablist">
          {["All", ...(data?.categories ?? [])].map((c) => (
            <button key={c} type="button" role="tab" aria-selected={tab === c} onClick={() => setTab(c)}
              className={cn("rounded-xl px-3.5 py-2 text-sm transition", tab === c ? "bg-white/15 text-white" : "text-muted-foreground hover:text-foreground")}>
              {c}
            </button>
          ))}
        </div>
        <label className="relative ml-auto w-full max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search templates" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>
      {!data ? <div className="flex h-40 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div> : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
          {shown.map((t) => {
            const look = LOOK[t.categories[0]] ?? LOOK.Trending;
            const Icon = look.icon;
            return (
              <button key={t.id} type="button" onClick={() => setOpen(t)}
                className={cn(glass, "group flex flex-col overflow-hidden text-left transition hover:-translate-y-0.5 hover:border-fuchsia-300/30")}>
                <span className={cn("flex aspect-[4/3] items-center justify-center bg-gradient-to-br", look.gradient)}>
                  <Icon className="h-9 w-9 text-white/75 transition group-hover:scale-110" />
                </span>
                <span className="flex flex-1 flex-col gap-1 p-3">
                  <span className="text-sm font-semibold">{t.name}</span>
                  <span className="line-clamp-2 text-xs text-muted-foreground">{t.description}</span>
                  <span className="mt-auto pt-2 text-xs font-medium text-fuchsia-200">Try now →</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
      {open ? <TemplatePanel template={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
