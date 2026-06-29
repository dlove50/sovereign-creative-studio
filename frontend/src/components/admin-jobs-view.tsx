"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertTriangle, CheckCircle2, Clock3, Loader2, RefreshCw, XCircle } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AdminJobMonitor, AdminJobMonitorItem, StaleJob } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { jobToMedia } from "@/lib/utils/mediaMapping";
import type { HandoffAction } from "@/lib/types/media";

const STATUS_OPTIONS = ["", "queued", "running", "completed", "failed"];
const FEATURE_OPTIONS = ["", "base_generation", "product_scene", "copy", "video", "transcription"];

export function AdminJobsView() {
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Job Monitor");
  const [data, setData] = useState<AdminJobMonitor | null>(null);
  const [status, setStatus] = useState("");
  const [feature, setFeature] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [staleThreshold, setStaleThreshold] = useState(60);
  const [stale, setStale] = useState<StaleJob[]>([]);
  const [staleBusy, setStaleBusy] = useState(false);
  const [staleNote, setStaleNote] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getAdminJobs({ status: status || undefined, feature: feature || undefined, limit: 100 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load jobs");
    } finally {
      setLoading(false);
    }
  }

  async function loadStale() {
    try {
      setStale(await api.getStaleJobs(staleThreshold));
    } catch {
      setStale([]);
    }
  }

  async function markStale(action: "cancelled" | "failed") {
    if (
      !window.confirm(
        `Mark ${stale.length} stale job(s) older than ${staleThreshold}m as ${action}? ` +
          "This only updates job status (no files deleted). Uncharged jobs stay uncharged.",
      )
    )
      return;
    setStaleBusy(true);
    setStaleNote(null);
    try {
      const res = await api.markStaleJobs({ action, threshold_minutes: staleThreshold });
      setStaleNote(`Marked ${res.marked} job(s) as ${res.action}. Refunds issued: ${res.refunds}.`);
      await Promise.all([load(), loadStale()]);
    } catch (err) {
      setStaleNote(err instanceof Error ? err.message : "Could not mark stale jobs");
    } finally {
      setStaleBusy(false);
    }
  }

  async function dismissJob(job: AdminJobMonitorItem) {
    if (!["base_generation", "product_scene", "video"].includes(job.feature)) return;
    if (
      !window.confirm(
        "Dismiss this job from the monitor? It is archived (hidden) — no files are deleted.",
      )
    )
      return;
    try {
      await api.dismissJob(job.feature, job.id);
      await Promise.all([load(), loadStale()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not dismiss job");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, feature]);

  useEffect(() => {
    loadStale();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staleThreshold]);

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const counts = data?.counts ?? { queued: 0, running: 0, completed: 0, failed: 0, total: 0 };

  return (
    <div className="space-y-6">
      <Link href="/admin" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Admin
      </Link>

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Local/private generation monitor</p>
          <p className="text-xs text-muted-foreground">
            Read-only job visibility across base generations, product scenes, copy, videos, and transcriptions.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
      </div>

      <section className="grid gap-4 md:grid-cols-5">
        <StatCard label="Total" value={counts.total} icon={Clock3} />
        <StatCard label="Queued" value={counts.queued} icon={Clock3} />
        <StatCard label="Running" value={counts.running} icon={Loader2} />
        <StatCard label="Completed" value={counts.completed} icon={CheckCircle2} />
        <StatCard label="Failed" value={counts.failed} icon={XCircle} danger={counts.failed > 0} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <select className="rounded-md border border-border bg-background px-3 py-2 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option || "all-status"} value={option}>{option ? formatLabel(option) : "All statuses"}</option>
            ))}
          </select>
          <select className="rounded-md border border-border bg-background px-3 py-2 text-sm" value={feature} onChange={(event) => setFeature(event.target.value)}>
            {FEATURE_OPTIONS.map((option) => (
              <option key={option || "all-features"} value={option}>{option ? formatLabel(option) : "All features"}</option>
            ))}
          </select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Stale jobs (stuck queued/running over {staleThreshold}m)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">Threshold (minutes):</span>
            <select
              className="rounded-md border border-border bg-background px-2 py-1 text-sm"
              value={staleThreshold}
              onChange={(e) => setStaleThreshold(Number(e.target.value))}
            >
              {[30, 60, 120].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <Button type="button" variant="outline" size="sm" onClick={loadStale} disabled={staleBusy}>
              <RefreshCw className="h-4 w-4" /> Rescan
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => markStale("cancelled")}
              disabled={staleBusy || stale.length === 0}
            >
              {staleBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
              Mark stale as cancelled
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => markStale("failed")}
              disabled={staleBusy || stale.length === 0}
            >
              Mark stale as failed
            </Button>
          </div>
          {staleNote ? <p className="text-xs text-muted-foreground">{staleNote}</p> : null}
          {stale.length === 0 ? (
            <p className="text-sm text-muted-foreground">No stale jobs over the threshold. </p>
          ) : (
            <div className="space-y-2">
              {stale.map((job) => (
                <div
                  key={`${job.feature}-${job.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="font-medium">{job.title || formatLabel(job.feature)}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {formatLabel(job.feature)} · {job.user_name || "Unknown"} · {job.status}
                    </span>
                  </span>
                  <Badge variant="muted">{job.elapsed_minutes}m elapsed</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Jobs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data?.jobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No jobs match the current filters.</p>
          ) : (
            data?.jobs.map((job) => (
              <JobRow key={`${job.feature}-${job.id}`} job={job} onDismiss={() => dismissJob(job)} onAction={onAction} />
            ))
          )}
        </CardContent>
      </Card>
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function StatCard({ danger = false, icon: Icon, label, value }: { danger?: boolean; icon: typeof Clock3; label: string; value: number }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <span className={`flex h-10 w-10 items-center justify-center rounded-md ${danger ? "bg-destructive/15 text-destructive" : "bg-primary/15 text-primary"}`}>
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="text-xl font-semibold">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function JobRow({
  job,
  onDismiss,
  onAction,
}: {
  job: AdminJobMonitorItem;
  onDismiss: () => void;
  onAction: (action: HandoffAction) => void;
}) {
  const url = assetUrl(job.result_url);
  const dismissable = ["base_generation", "product_scene", "video"].includes(job.feature);
  // Completed jobs with usable media get compact handoff actions; failed jobs map to null.
  const media = jobToMedia(job);
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="line-clamp-2 text-sm font-medium">{job.title || formatLabel(job.feature)}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatLabel(job.feature)} - {job.user_name || "Unknown user"}{job.project_name ? ` - ${job.project_name}` : ""} - {formatDate(job.created_at)}
          </p>
        </div>
        <Badge variant={job.status === "failed" ? "destructive" : job.status === "completed" ? "success" : "muted"}>
          {job.status}
        </Badge>
      </div>
      {job.error ? (
        <p className="mt-2 line-clamp-3 text-xs text-destructive">
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
          {job.error}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>ID: {job.id}</span>
        {job.updated_at ? <span>Updated: {formatDate(job.updated_at)}</span> : null}
        {url ? <a className="text-primary hover:underline" href={url} target="_blank" rel="noreferrer">Open result</a> : null}
        {dismissable ? (
          <button
            type="button"
            onClick={onDismiss}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
            title="Archive this job out of the monitor (no files deleted)"
          >
            <XCircle className="h-3.5 w-3.5" /> Dismiss
          </button>
        ) : null}
      </div>
      {media ? (
        <div className="mt-3 border-t border-border/60 pt-2">
          <MediaActions
            media={media}
            onAction={onAction}
            compact
            primaryAction={media.type === "image" ? "animate_image" : media.type === "video" ? "transcribe_video" : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
