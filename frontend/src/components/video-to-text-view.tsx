"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Copy,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Upload,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  AppStatus,
  Project,
  TranscriptionJob,
  TranscriptionSummaryType,
  VideoGeneration,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MediaActions } from "@/components/media/MediaActions";
import { NextStepCard } from "@/components/media/NextStepCard";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { consumeHandoff } from "@/lib/stores/useMediaHandoff";
import { transcriptToMedia } from "@/lib/utils/mediaMapping";
import { validateSourceUrl } from "@/lib/utils/validateSourceUrl";
import { cn } from "@/lib/utils";
import { safeInterval } from "@/lib/safe-interval";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const SUMMARY_TYPES: { value: TranscriptionSummaryType; label: string }[] = [
  { value: "short_summary", label: "Short summary" },
  { value: "bullet_summary", label: "Bullet summary" },
  { value: "key_points", label: "Key points" },
  { value: "social_caption_ideas", label: "Social caption ideas" },
  { value: "scene_breakdown", label: "Scene breakdown" },
];

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

export function VideoToTextView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [appStatus, setAppStatus] = useState<AppStatus | null>(null);
  const [videos, setVideos] = useState<VideoGeneration[]>([]);
  const [jobs, setJobs] = useState<TranscriptionJob[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [summaryType, setSummaryType] =
    useState<TranscriptionSummaryType>("short_summary");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const completedVideos = useMemo(
    () => videos.filter((video) => video.status === "completed" && video.result_url),
    [videos],
  );
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;

  const [autoAttachedFrom, setAutoAttachedFrom] = useState<string | null>(null);
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Video Studio");

  useEffect(() => {
    load();
    // Consume a "Transcribe This Video" handoff (or ?source=/storage/...video).
    if (typeof window === "undefined") return;
    const pending = consumeHandoff();
    const sp = new URLSearchParams(window.location.search);
    const src = pending?.sourceUrl ?? sp.get("source");
    if (src && validateSourceUrl(src, ["video"]).ok) {
      setSourceUrl(src);
      setAutoAttachedFrom(pending?.originLabel ?? "from a previous step");
    }
  }, []);

  useEffect(() => {
    const active = jobs.filter(
      (job) => job.status === "queued" || job.status === "running",
    );
    if (active.length === 0) return;
    const poll = safeInterval(async () => {
      const updates = await Promise.all(active.map((job) => api.getTranscription(job.id)));
      setJobs((current) =>
        current.map((job) => updates.find((update) => update.id === job.id) ?? job),
      );
    }, 2500);
    return poll;
  }, [jobs]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [projectList, videoList, jobList, status] = await Promise.all([
        api.listProjects(),
        api.listVideos(),
        api.listTranscriptions(),
        api.getStatus(),
      ]);
      setProjects(projectList);
      setVideos(videoList);
      setJobs(jobList);
      setAppStatus(status);
      setProjectId(projectList[0]?.id ?? "");
      setSelectedJobId(jobList[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load transcriptions");
    } finally {
      setLoading(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting || (!file && !sourceUrl.trim())) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createTranscription({
        project_id: projectId || null,
        source_video_url: file ? null : sourceUrl.trim(),
        file,
      });
      setJobs((current) => [created, ...current]);
      setSelectedJobId(created.id);
      setFile(null);
      setSourceUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create transcription");
    } finally {
      setSubmitting(false);
    }
  }

  async function summarize() {
    if (!selectedJob || selectedJob.status !== "completed") return;
    setSummarizing(true);
    setError(null);
    try {
      const updated = await api.summarizeTranscription(selectedJob.id, summaryType);
      setJobs((current) =>
        current.map((job) => (job.id === updated.id ? updated : job)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not summarize transcript");
    } finally {
      setSummarizing(false);
    }
  }

  async function copyText(text: string) {
    await navigator.clipboard.writeText(text);
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading transcription workspace...
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
      <section className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5" />
              New transcript
            </CardTitle>
            <CardDescription>
              Local/private video transcription. Standard transcript cost: 5 credits.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {appStatus ? (
                <div
                  className={cn(
                    "rounded-md border p-3 text-sm",
                    appStatus.transcription_available
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                      : "border-destructive/30 bg-destructive/10 text-destructive",
                  )}
                >
                  <div className="font-medium">
                    {appStatus.transcription_backend === "mock"
                      ? "Mock transcription fallback"
                      : appStatus.transcription_available
                        ? "Real local transcription ready"
                        : "Real local transcription not ready"}
                  </div>
                  <div className="mt-1 text-xs">
                    Backend: {appStatus.transcription_backend} - Model:{" "}
                    {appStatus.transcription_model_name} / {appStatus.transcription_device} /{" "}
                    {appStatus.transcription_compute_type} - ffmpeg:{" "}
                    {appStatus.transcription_ffmpeg_available ? "available" : "missing"} - faster-whisper:{" "}
                    {appStatus.transcription_faster_whisper_available ? "available" : "missing"}
                  </div>
                  {!appStatus.transcription_available ? (
                    <div className="mt-1 text-xs">
                      {appStatus.transcription_message}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {error ? (
                <div className="flex gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="project">Project</Label>
                <select
                  id="project"
                  className={selectClass}
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                >
                  <option value="">No project</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="existing-video">Existing completed video</Label>
                <select
                  id="existing-video"
                  className={selectClass}
                  value={sourceUrl}
                  onChange={(e) => {
                    setSourceUrl(e.target.value);
                    if (e.target.value) setFile(null);
                  }}
                >
                  <option value="">Choose a completed video...</option>
                  {completedVideos.map((video) => (
                    <option key={video.id} value={video.result_url ?? ""}>
                      {video.prompt.slice(0, 80)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="source-url">Source URL override</Label>
                {autoAttachedFrom && sourceUrl ? (
                  <p className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
                    Auto-attached {autoAttachedFrom}
                  </p>
                ) : null}
                <Input
                  id="source-url"
                  placeholder="/storage/videos/example.mp4"
                  value={sourceUrl}
                  onChange={(e) => {
                    setSourceUrl(e.target.value);
                    setAutoAttachedFrom(null);
                    if (e.target.value) setFile(null);
                  }}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="video-file">Upload video file</Label>
                <Input
                  id="video-file"
                  type="file"
                  accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
                  onChange={(e) => {
                    const next = e.target.files?.[0] ?? null;
                    setFile(next);
                    if (next) setSourceUrl("");
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  Supported: MP4, MOV, WEBM, MKV. Real local mode uses faster-whisper
                  and ffmpeg; mock remains available as a fallback.
                </p>
              </div>

              <Button type="submit" disabled={submitting || (!file && !sourceUrl.trim())}>
                {submitting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="mr-2 h-4 w-4" />
                )}
                Transcribe video
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-lg">History</CardTitle>
              <CardDescription>Queued, completed, and failed transcript jobs.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No transcripts yet.</p>
            ) : (
              jobs.map((job) => (
                <button
                  key={job.id}
                  type="button"
                  onClick={() => setSelectedJobId(job.id)}
                  className={cn(
                    "w-full rounded-md border p-3 text-left text-sm transition-colors hover:border-primary/50",
                    selectedJob?.id === job.id
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background/30",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">
                      {job.source_filename ?? job.source_video_url}
                    </span>
                    <Badge variant={STATUS_VARIANT[job.status]}>{job.status}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {new Date(job.created_at).toLocaleString()} - {job.provider}/{job.model_name}
                  </div>
                </button>
              ))
            )}
          </CardContent>
        </Card>
      </section>

      <section className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Transcript</CardTitle>
            <CardDescription>
              {selectedJob
                ? selectedJob.source_video_url
                : "Select or create a transcript job."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedJob ? (
              <p className="text-sm text-muted-foreground">No transcript selected.</p>
            ) : (
              <>
                {assetUrl(selectedJob.source_video_url) ? (
                  <video
                    src={assetUrl(selectedJob.source_video_url) ?? undefined}
                    controls
                    className="max-h-80 w-full rounded-md border border-border bg-black"
                  />
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={STATUS_VARIANT[selectedJob.status]}>
                    {selectedJob.status}
                  </Badge>
                  <Badge variant="muted">{selectedJob.credits_cost} credits</Badge>
                  {selectedJob.detected_language ? (
                    <Badge variant="outline">{selectedJob.detected_language}</Badge>
                  ) : null}
                  {selectedJob.duration_seconds ? (
                    <Badge variant="outline">
                      {Math.round(selectedJob.duration_seconds)}s
                    </Badge>
                  ) : null}
                </div>
                {selectedJob.error_message ? (
                  <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                    {selectedJob.error_message}
                  </div>
                ) : null}
                <Textarea
                  readOnly
                  value={selectedJob.transcript_text ?? ""}
                  placeholder="Transcript will appear here when the job completes."
                  className="min-h-[260px]"
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!selectedJob.transcript_text}
                    onClick={() => copyText(selectedJob.transcript_text ?? "")}
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    Copy transcript
                  </Button>
                  {selectedJob.status === "completed" && selectedJob.transcript_text ? (
                    <a
                      href={api.transcriptionDownloadUrl(selectedJob.id)}
                      className={cn(buttonVariants({ variant: "outline" }), "gap-2")}
                    >
                      <Download className="h-4 w-4" />
                      Download TXT
                    </a>
                  ) : null}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {selectedJob ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Summary</CardTitle>
              <CardDescription>
                Optional local copy-provider summary. Summary cost: 2 credits.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row">
                <select
                  className={selectClass}
                  value={summaryType}
                  onChange={(e) =>
                    setSummaryType(e.target.value as TranscriptionSummaryType)
                  }
                >
                  {SUMMARY_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  disabled={
                    summarizing ||
                    selectedJob.status !== "completed" ||
                    !selectedJob.transcript_text
                  }
                  onClick={summarize}
                >
                  {summarizing ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Summarize
                </Button>
              </div>
              <Textarea
                readOnly
                value={selectedJob.summary_text ?? ""}
                placeholder="Summary will appear here."
                className="min-h-[180px]"
              />
              <Button
                type="button"
                variant="outline"
                disabled={!selectedJob.summary_text}
                onClick={() => copyText(selectedJob.summary_text ?? "")}
              >
                <Copy className="mr-2 h-4 w-4" />
                Copy summary
              </Button>
            </CardContent>
          </Card>
        ) : null}

        {selectedJob && selectedJob.status === "completed" && selectedJob.transcript_text ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">What do you want to do with this?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <MediaActions media={transcriptToMedia(selectedJob)} onAction={onAction} />
              <NextStepCard media={transcriptToMedia(selectedJob)} onAction={onAction} />
            </CardContent>
          </Card>
        ) : null}
      </section>
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
