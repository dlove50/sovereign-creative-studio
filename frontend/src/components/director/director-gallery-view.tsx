"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CircleCheck, Loader2, TriangleAlert } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { LoadError } from "@/components/ui/load-error";
import { directorApi, formatLength, type DirectorProject } from "@/lib/api/director";

import { TemplateCarousel } from "./template-carousel";

const STATUS_LABEL: Record<DirectorProject["status"], string> = {
  queued: "Waiting",
  running: "Making",
  done: "Ready",
  error: "Problem",
  cancelled: "Cancelled",
};

function StatusIcon({ status }: { status: DirectorProject["status"] }) {
  if (status === "done") return <CircleCheck className="h-4 w-4 text-emerald-400" aria-hidden="true" />;
  if (status === "error" || status === "cancelled") return <TriangleAlert className="h-4 w-4 text-amber-400" aria-hidden="true" />;
  return <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />;
}

export function DirectorGalleryView() {
  const [projects, setProjects] = useState<DirectorProject[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    // A failed refresh keeps the last list on screen; only a failed FIRST load shows the error state.
    const load = () => directorApi.projects()
      .then((p) => { if (alive) { setProjects(p); setFailed(false); } })
      .catch(() => { if (alive) { setFailed(true); setProjects((current) => current ?? []); } });
    load();
    const id = window.setInterval(load, 8000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Direct your video"
        description="Pick a format, answer a few questions, and Sovereign plans the shots, films them with your local video model, adds a voice-over and a soundtrack, and gives you one finished video."
      />
      <TemplateCarousel layout="grid" />

      <section aria-labelledby="director-recent">
        <h2 id="director-recent" className="mb-3 text-sm font-medium text-foreground/90">Your videos</h2>
        {projects === null ? (
          <div className="h-20 animate-pulse rounded-2xl bg-card/50" />
        ) : failed && projects.length === 0 ? (
          <LoadError what="your videos" message="Trying again every few seconds." />
        ) : projects.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-border p-6 text-sm text-muted-foreground">
            Nothing here yet. Choose a format above to make your first video.
          </p>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card">
            {projects.map((p) => (
              <li key={p.id}>
                <Link href={`/director/watch?id=${p.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-raised/60">
                  <StatusIcon status={p.status} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {p.title || p.label}
                      {p.episode ? <span className="ml-2 text-xs text-muted-foreground">Episode {p.episode}</span> : null}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {p.label} · {formatLength(p.seconds)} · {STATUS_LABEL[p.status]}
                      {p.status === "running" ? `: ${p.message}` : ""}
                    </span>
                  </span>
                  <span className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleDateString()}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
