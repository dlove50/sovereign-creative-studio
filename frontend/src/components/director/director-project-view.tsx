"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Check, CircleX, Download, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { assetUrl } from "@/lib/api/core";
import { directorApi, formatLength, type DirectorProject, type DirectorSeries } from "@/lib/api/director";
import { cn } from "@/lib/utils";

const POLL_MS = 3000;
const ACTIVE = ["queued", "running"];

type Step = { id: string; label: string };

function stepsFor(project: DirectorProject): Step[] {
  const steps: Step[] = [
    { id: "planning", label: "Planning the shots" },
    { id: "clips", label: "Filming" },
    { id: "assembling", label: "Joining" },
  ];
  if (project.narration) steps.push({ id: "narration", label: "Voice-over" });
  if (project.music) steps.push({ id: "scoring", label: "Soundtrack" });
  if (project.narration || project.music) steps.push({ id: "mixing", label: "Mixing" });
  steps.push({ id: "done", label: "Ready" });
  return steps;
}

function StepList({ project }: { project: DirectorProject }) {
  const steps = stepsFor(project);
  const current = Math.max(0, steps.findIndex((s) => s.id === project.stage));
  const finished = project.status === "done";
  return (
    <ol className="flex flex-wrap gap-x-6 gap-y-2">
      {steps.map((step, i) => {
        const done = finished || i < current;
        const active = !finished && i === current && ACTIVE.includes(project.status);
        const failed = i === current && (project.status === "error" || project.status === "cancelled");
        return (
          <li key={step.id} className={cn("flex items-center gap-2 text-sm", done || active ? "text-foreground" : "text-muted-foreground")}>
            <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border", done ? "border-primary bg-primary text-primary-foreground" : active ? "border-primary" : failed ? "border-destructive" : "border-border")}>
              {done ? <Check className="h-3 w-3" strokeWidth={3} /> : active ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : failed ? <CircleX className="h-3 w-3 text-destructive" /> : null}
            </span>
            {step.label}
            {step.id === "clips" && project.shots.length > 0 && (active || done) ? (
              <span className="text-xs text-muted-foreground">({project.shots.filter((s) => s.status === "done").length}/{project.shots.length})</span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function ShotCard({ shot, index, portrait }: { shot: DirectorProject["shots"][number]; index: number; portrait: boolean }) {
  const tint = shot.status === "done" ? "border-emerald-500/40" : shot.status === "running" ? "border-primary/60" : shot.status === "error" ? "border-destructive/60" : "border-border";
  return (
    <li className={cn("overflow-hidden rounded-xl border bg-card", tint)}>
      <div className={cn("relative bg-background/60", portrait ? "aspect-[9/16]" : "aspect-video")}>
        {shot.clip_url ? (
          <video src={assetUrl(shot.clip_url) ?? shot.clip_url} muted loop playsInline preload="metadata" className="h-full w-full object-cover"
            onMouseEnter={(e) => void e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} />
        ) : shot.keyframe_url ? (
          <img src={assetUrl(shot.keyframe_url) ?? shot.keyframe_url} alt="" className="h-full w-full object-cover opacity-80" />
        ) : null}
        {shot.status === "running" ? <Loader2 className="absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 animate-spin text-primary" /> : null}
        <span className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 text-[11px] font-semibold text-white">{index + 1}</span>
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/60 px-1.5 text-[11px] tabular-nums text-white">{shot.duration}s</span>
      </div>
      <p className="line-clamp-2 p-2 text-xs text-muted-foreground" title={shot.error ?? shot.description}>{shot.error ?? shot.description}</p>
    </li>
  );
}

export function DirectorProjectView() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [project, setProject] = useState<DirectorProject | null>(null);
  const [series, setSeries] = useState<DirectorSeries | null>(null);
  const [missing, setMissing] = useState(false);
  const [direction, setDirection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setProject(await directorApi.project(id));
    } catch {
      setMissing(true);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const running = project ? ACTIVE.includes(project.status) : false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, load]);

  const seriesId = project?.series_id ?? null;
  const status = project?.status;
  useEffect(() => {
    if (seriesId) directorApi.series(seriesId).then(setSeries).catch(() => setSeries(null));
  }, [seriesId, status]);

  if (!id || missing) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">That video was not found. It may have been deleted.</p>
        <Link href="/director" className="text-primary underline underline-offset-4">Back to Director</Link>
      </div>
    );
  }
  if (!project) return <div className="h-64 animate-pulse rounded-2xl bg-card/50" />;

  const portrait = project.orientation === "portrait";
  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Link href="/director" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Director
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            {project.title}
            {project.episode ? <span className="ml-3 rounded-md bg-primary/15 px-2 py-0.5 align-middle text-sm font-semibold text-primary">Episode {project.episode}</span> : null}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{project.label} · {formatLength(project.seconds)} · {portrait ? "vertical" : "widescreen"}</p>
        </div>
        <div className="flex gap-2">
          {running ? (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => { if (window.confirm("Stop making this video? Rendering will stop.")) void act(() => directorApi.cancel(project.id)); }}>Cancel</Button>
          ) : (
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => { if (window.confirm("Delete this video? This cannot be undone.")) void act(async () => { await directorApi.remove(project.id); router.push("/director"); }); }}>
              <Trash2 className="mr-1.5 h-4 w-4" aria-hidden="true" /> Delete
            </Button>
          )}
        </div>
      </div>

      <section className="space-y-3 rounded-2xl border border-border bg-card p-4" aria-live="polite">
        <StepList project={project} />
        <p className={cn("text-sm", project.status === "error" ? "text-destructive" : "text-muted-foreground")}>{project.message}</p>
        {running ? <p className="text-xs text-muted-foreground">You can leave this page. The video keeps being made and appears under Your videos.</p> : null}
        {project.notes.map((n) => <p key={n} className="text-xs text-amber-300">{n}</p>)}
        {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      </section>

      {project.status === "done" && project.result_url ? (
        <section className="space-y-3">
          <video src={assetUrl(project.result_url) ?? project.result_url} controls playsInline className={cn("mx-auto rounded-2xl border border-border bg-black", portrait ? "max-h-[36rem]" : "w-full")} />
          <div className="flex flex-wrap justify-center gap-2">
            <a href={assetUrl(project.result_url) ?? project.result_url} download={`${project.title}.mp4`} className="inline-flex h-10 items-center gap-2 rounded-lg border border-border px-4 text-sm font-medium hover:bg-raised">
              <Download className="h-4 w-4" aria-hidden="true" /> Download MP4
            </a>
          </div>
        </section>
      ) : null}

      {project.plan ? (
        <section className="grid gap-4 md:grid-cols-[1fr_16rem]">
          <div className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Story</h2>
            <p className="text-sm leading-relaxed">{project.plan.synopsis}</p>
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cast</h2>
            <ul className="space-y-1.5 text-xs">
              {project.plan.characters.map((c) => (
                <li key={c.id}><span className="font-semibold text-foreground">{c.name}</span> <span className="text-muted-foreground">{c.description}</span></li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {project.shots.length > 0 ? (
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Shots</h2>
          <ul className={cn("grid gap-3", portrait ? "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4")}>
            {project.shots.map((shot, i) => <ShotCard key={shot.id} shot={shot} index={i} portrait={portrait} />)}
          </ul>
        </section>
      ) : null}

      {project.series_id && series ? (
        <section className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Series: {series.title || project.title}</h2>
          <ul className="flex flex-wrap gap-2">
            {series.episodes.map((e) => (
              <li key={e.project_id}>
                <Link href={`/director/watch?id=${e.project_id}`} className={cn("inline-flex h-8 items-center rounded-lg border px-3 text-xs font-medium", e.project_id === project.id ? "border-primary/60 bg-primary/15 text-primary" : "border-border hover:bg-raised")}>
                  Episode {e.number}
                </Link>
              </li>
            ))}
          </ul>
          {project.status === "done" ? (
            <div className="space-y-2">
              <label htmlFor="next-direction" className="text-xs font-medium">What should happen next? <span className="font-normal text-muted-foreground">(optional)</span></label>
              <Textarea id="next-direction" rows={2} maxLength={400} value={direction} placeholder="She follows the stranger to the old pier." onChange={(e) => setDirection(e.target.value)} />
              <Button
                disabled={busy}
                onClick={() => void act(async () => {
                  const next = await directorApi.nextEpisode(project.series_id as string, { direction, music: project.music, planner: project.planner });
                  router.push(`/director/watch?id=${next.id}`);
                })}
              >
                <Plus className="mr-1.5 h-4 w-4" aria-hidden="true" /> Make episode {series.episodes.length + 1}
              </Button>
              <p className="text-xs text-muted-foreground">The same characters and places are carried forward. Faces can still vary a little between episodes.</p>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
