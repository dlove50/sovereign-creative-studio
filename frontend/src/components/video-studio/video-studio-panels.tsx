"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Clock,
  Download,
  Film,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  AppStatus,
  ProductSceneGeneration,
  Project,
  Shot,
  Storyboard,
  VideoGeneration,
  VideoMode,
  VideoModeOption,
  VideoMotionPreset,
  VideoProvider,
  VideoQualityPreset,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { ActiveConfigBadge } from "@/components/active-config-badge";
import { BriefSelect } from "@/components/brief-select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { consumeHandoff } from "@/lib/stores/useMediaHandoff";
import { videoToMedia } from "@/lib/utils/mediaMapping";
import { validateSourceUrl } from "@/lib/utils/validateSourceUrl";
import { cn } from "@/lib/utils";
import { confirmDialog } from "@/components/ui/confirm-host";

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

export function VideoModeBanner({
  status,
  refreshing,
  onRefresh,
}: {
  status: AppStatus | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const backend = status?.video_backend ?? "unknown";
  const isComfy = backend === "comfyui";
  const comfyOffline = isComfy && status?.comfyui_reachable === false;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Film className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">Video backend</span>
            <Badge variant={isComfy ? "default" : "muted"}>{backend}</Badge>
            {isComfy ? (
              <Badge variant="outline">Local video workflows</Badge>
            ) : (
              <Badge variant="outline">Mock preview mode</Badge>
            )}
          </div>
          {comfyOffline ? (
            <div className="flex gap-2 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                ComfyUI offline. Expected URL:{" "}
                <span className="font-mono">
                  {status?.comfyui_base_url || "http://127.0.0.1:8001"}
                </span>
                . Start with{" "}
                <span className="font-mono">
                  Start-Sovereign-Creative-Studio.bat
                </span>
                .
              </span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {isComfy
                ? "Real jobs use the configured ComfyUI video workflows for each wired mode."
                : "Mock mode creates a lightweight local preview and stays available as the fallback."}
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>
    </div>
  );
}

export function VideoCard({
  video,
  onTrash,
  onAction,
}: {
  video: VideoGeneration;
  onTrash: (id: string) => void;
  onAction: (action: import("@/lib/types/media").HandoffAction) => void;
}) {
  const src = assetUrl(video.result_url);
  const isHtmlPreview = src?.toLowerCase().endsWith(".html") ?? false;
  const elapsed = formatElapsed(video.created_at, video.completed_at);
  const providerLabel =
    video.provider === "seedance_api"
      ? "Seedance"
      : video.provider === "local_wan"
        ? "Wan 2.1"
        : video.provider === "local_h3"
          ? "MiniMax H3"
          : "Local LTX";
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="relative aspect-square bg-background/60">
        {video.status === "completed" && src && isHtmlPreview ? (
          <iframe
            src={src}
            title={video.prompt}
            className="h-full w-full border-0"
          />
        ) : video.status === "completed" && src ? (
          <video
            src={src}
            title={video.prompt}
            className="h-full w-full bg-black object-contain"
            controls
            playsInline
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            {video.status === "failed" ? (
              <span className="px-3 text-center text-destructive">
                {video.error ?? "Video failed"}
              </span>
            ) : (
              <>
                <Film className="h-7 w-7" />
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="capitalize">{video.status}</span>
              </>
            )}
          </div>
        )}
        <Badge
          variant={STATUS_VARIANT[video.status]}
          className="absolute right-2 top-2 capitalize"
        >
          {video.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{video.motion_preset.replace("_", " ")}</span>
          <Badge variant="muted" className="capitalize">
            {video.mode.replaceAll("_", " ")}
          </Badge>
          <Badge variant={video.provider === "seedance_api" ? "default" : "outline"}>
            {providerLabel}
          </Badge>
          {video.quality_preset ? (
            <Badge variant="outline">
              {video.quality_preset.replaceAll("_", " ")}
            </Badge>
          ) : null}
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {video.status === "queued" || video.status === "running"
              ? `${elapsed} elapsed`
              : `${video.duration_seconds}s`}
          </span>
        </div>
        <p className="line-clamp-2 text-sm text-foreground/90">{video.prompt}</p>
        <div className="flex gap-2">
          {video.status === "completed" ? (
            <a
              href={api.exportVideoUrl(video.id)}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "flex-1",
              )}
            >
              <Download className="h-4 w-4" /> Download
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => onTrash(video.id)}
            title="Move to trash (recoverable)"
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "text-destructive hover:text-destructive",
            )}
          >
            <Trash2 className="h-4 w-4" /> Trash
          </button>
        </div>
        {video.status === "completed" && video.result_url ? (
          <div className="border-t border-border/60 pt-2">
            <MediaActions media={videoToMedia(video)} onAction={onAction} compact />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function StoryboardPlanner({ projectId }: { projectId: string }) {
  const [storyboards, setStoryboards] = useState<Storyboard[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [shotDescription, setShotDescription] = useState("");
  const [shotCamera, setShotCamera] = useState("");
  const [shotPrompt, setShotPrompt] = useState("");
  const [shotDuration, setShotDuration] = useState(5);
  const [error, setError] = useState<string | null>(null);

  const selected = storyboards.find((storyboard) => storyboard.id === selectedId);

  useEffect(() => {
    if (!projectId) {
      setStoryboards([]);
      setSelectedId("");
      return;
    }
    api
      .listStoryboards(projectId)
      .then((loaded) => {
        setStoryboards(loaded);
        setSelectedId((current) =>
          loaded.some((storyboard) => storyboard.id === current)
            ? current
            : loaded[0]?.id ?? "",
        );
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load storyboards"),
      );
  }, [projectId]);

  useEffect(() => {
    if (!selectedId) {
      setShots([]);
      return;
    }
    api
      .listShots(selectedId)
      .then(setShots)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load shots"),
      );
  }, [selectedId]);

  async function createStoryboard(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId || !title.trim()) return;
    setError(null);
    try {
      const created = await api.createStoryboard(projectId, {
        title: title.trim(),
        description: description.trim() || null,
        status: "draft",
      });
      setStoryboards((current) => [created, ...current]);
      setSelectedId(created.id);
      setTitle("");
      setDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create storyboard");
    }
  }

  async function deleteStoryboard(storyboard: Storyboard) {
    if (!await confirmDialog(`Delete the storyboard "${storyboard.title}" and all of its shots? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.deleteStoryboard(projectId, storyboard.id);
      setStoryboards((current) => current.filter((item) => item.id !== storyboard.id));
      if (selectedId === storyboard.id) {
        setSelectedId(storyboards.find((item) => item.id !== storyboard.id)?.id ?? "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete storyboard");
    }
  }

  async function createShot(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId) return;
    setError(null);
    try {
      const created = await api.createShot(selectedId, {
        shot_number: shots.length + 1,
        duration_seconds: shotDuration,
        description: shotDescription.trim() || null,
        camera_notes: shotCamera.trim() || null,
        generation_prompt: shotPrompt.trim() || null,
      });
      setShots((current) => [...current, created]);
      setShotDescription("");
      setShotCamera("");
      setShotPrompt("");
      setShotDuration(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create shot");
    }
  }

  async function deleteShot(shot: Shot) {
    if (!selectedId) return;
    if (!await confirmDialog(`Delete shot ${shot.shot_number}? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.deleteShot(selectedId, shot.id);
      setShots((current) => current.filter((item) => item.id !== shot.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete shot");
    }
  }

  async function saveShotPrompt(shot: Shot, prompt: string) {
    if (!selectedId) return;
    const updated = await api.updateShot(selectedId, shot.id, {
      generation_prompt: prompt,
    });
    setShots((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-5">
      <div>
        <h3 className="text-base font-semibold">Storyboards & Shot Planner</h3>
        <p className="text-sm text-muted-foreground">
          Plan project-linked video sequences, shots, camera notes, and prompts.
        </p>
      </div>
      {error ? (
        <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <form onSubmit={createStoryboard} className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="storyboard-title">Storyboard title</Label>
              <Input
                id="storyboard-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Launch teaser sequence"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="storyboard-description">Description</Label>
              <Textarea
                id="storyboard-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What is this sequence trying to show?"
              />
            </div>
            <Button type="submit" disabled={!title.trim() || !projectId}>
              <Plus className="h-4 w-4" />
              Create storyboard
            </Button>
          </form>

          <div className="space-y-2">
            {storyboards.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                No storyboards yet.
              </p>
            ) : (
              storyboards.map((storyboard) => (
                <button
                  key={storyboard.id}
                  type="button"
                  onClick={() => setSelectedId(storyboard.id)}
                  className={cn(
                    "w-full rounded-md border px-3 py-2 text-left transition-colors",
                    selectedId === storyboard.id
                      ? "border-primary bg-primary/15"
                      : "border-border hover:bg-muted",
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">
                      {storyboard.title}
                    </span>
                    <Badge variant="outline">{storyboard.status}</Badge>
                  </span>
                  <span className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                    {storyboard.description || "No description"}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="space-y-4">
          {selected ? (
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 className="font-medium">{selected.title}</h4>
                <p className="text-sm text-muted-foreground">
                  {selected.description || "No description"}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => deleteStoryboard(selected)}
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </Button>
            </div>
          ) : null}

          {selectedId ? (
            <form
              onSubmit={createShot}
              className="grid gap-3 rounded-md border border-border bg-background/30 p-3 md:grid-cols-2"
            >
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="shot-description">Shot description</Label>
                <Textarea
                  id="shot-description"
                  value={shotDescription}
                  onChange={(event) => setShotDescription(event.target.value)}
                  placeholder="Close-up product reveal on marble"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="shot-camera">Camera notes</Label>
                <Input
                  id="shot-camera"
                  value={shotCamera}
                  onChange={(event) => setShotCamera(event.target.value)}
                  placeholder="Slow push, shallow depth"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="shot-duration">Duration seconds</Label>
                <Input
                  id="shot-duration"
                  type="number"
                  min={1}
                  max={60}
                  value={shotDuration}
                  onChange={(event) => setShotDuration(Number(event.target.value))}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="shot-prompt">Generation prompt</Label>
                <Textarea
                  id="shot-prompt"
                  value={shotPrompt}
                  onChange={(event) => setShotPrompt(event.target.value)}
                  placeholder="Prompt to reuse in Video Studio"
                />
              </div>
              <Button
                type="submit"
                disabled={!shotDescription.trim() && !shotPrompt.trim()}
              >
                <Plus className="h-4 w-4" />
                Add shot
              </Button>
            </form>
          ) : null}

          <div className="space-y-3">
            {shots.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                Select a storyboard and add shots.
              </p>
            ) : (
              shots.map((shot) => (
                <ShotCard
                  key={shot.id}
                  shot={shot}
                  onDelete={() => deleteShot(shot)}
                  onSavePrompt={(prompt) => saveShotPrompt(shot, prompt)}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function ShotCard({
  onDelete,
  onSavePrompt,
  shot,
}: {
  onDelete: () => void;
  onSavePrompt: (prompt: string) => void;
  shot: Shot;
}) {
  const [prompt, setPrompt] = useState(shot.generation_prompt ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await onSavePrompt(prompt);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Badge variant="muted">Shot {shot.shot_number}</Badge>
          <p className="mt-2 text-sm font-medium">
            {shot.description || "Untitled shot"}
          </p>
          <p className="text-xs text-muted-foreground">
            {shot.duration_seconds}s · {shot.camera_notes || "No camera notes"}
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      <div className="space-y-2">
        <Label>Video prompt</Label>
        <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
        <Button type="button" variant="outline" size="sm" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Save prompt
        </Button>
      </div>
    </div>
  );
}

function formatElapsed(createdAt: string, completedAt: string | null) {
  const start = new Date(createdAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return "0s";
  const seconds = Math.floor((end - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}
