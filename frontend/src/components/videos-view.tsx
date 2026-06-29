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

const MOTION_PRESETS: { value: VideoMotionPreset; label: string }[] = [
    { value: "slow_zoom", label: "Slow zoom" },
    { value: "cinematic_push", label: "Cinematic push" },
    { value: "dolly_in", label: "Dolly in" },
    { value: "runway_walk", label: "Runway walk" },
    { value: "parallax", label: "Parallax" },
    { value: "orbit", label: "Orbit" },
    { value: "handheld", label: "Handheld" },
    { value: "product_reveal", label: "Product reveal" },
    { value: "product_motion", label: "Product motion" },
    { value: "subtle_breathing", label: "Subtle breathing" },
];

const DURATIONS = [3, 5, 8, 10];

const VIDEO_PRESETS: {
  label: string;
  motion: VideoMotionPreset;
  duration: number;
  description: string;
}[] = [
  {
    label: "Quick",
    motion: "slow_zoom",
    duration: 3,
    description: "Fast short LTX clip (low cost)",
  },
  {
    label: "Short Social",
    motion: "cinematic_push",
    duration: 5,
    description: "Short motion pass",
  },
  {
    label: "Product Motion",
    motion: "product_motion",
    duration: 5,
    description: "Visible pan, zoom, and product energy",
  },
  {
    label: "Runway Motion",
    motion: "runway_walk",
    duration: 5,
    description: "Fashion movement with stronger directional motion",
  },
];

const QUALITY_PRESETS: {
  value: VideoQualityPreset;
  label: string;
  description: string;
  bestFor: string;
}[] = [
  {
    value: "safe_preview",
    label: "Safe Preview",
    description: "256x256 quick compatibility test.",
    bestFor: "Only use for smoke tests.",
  },
  {
    value: "standard_local",
    label: "Standard Local",
    description: "512x320 short local LTX clip.",
    bestFor: "Recommended default for text-to-video.",
  },
  {
    value: "best_local",
    label: "Best Local Quality",
    description: "640x384, more steps, slower.",
    bestFor: "Short prompts where detail matters.",
  },
  {
    value: "image_to_video_best",
    label: "Image-to-Video Best",
    description: "640x384 with stronger source-image preservation.",
    bestFor: "Best for dogs, people, products, and characters.",
  },
];

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const PROVIDERS: { id: VideoProvider; label: string; badge: string }[] = [
  { id: "local_ltx", label: "Local LTX", badge: "Default local" },
  { id: "seedance_api", label: "Seedance / C-Dance 2.0", badge: "Premium" },
];

export function VideosView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [videos, setVideos] = useState<VideoGeneration[]>([]);
  const [appStatus, setAppStatus] = useState<AppStatus | null>(null);

  const [projectId, setProjectId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [autoAttachedFrom, setAutoAttachedFrom] = useState<string | null>(null);
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Video Studio");
  const [prompt, setPrompt] = useState("");
  const [motionPreset, setMotionPreset] = useState<VideoMotionPreset>("slow_zoom");
  const [duration, setDuration] = useState(3);
  const [qualityPreset, setQualityPreset] =
    useState<VideoQualityPreset>("standard_local");
  const [briefId, setBriefId] = useState("");
  const [videoModes, setVideoModes] = useState<VideoModeOption[]>([]);
  const [videoMode, setVideoMode] = useState<VideoMode>("image_to_video");
  const [provider, setProvider] = useState<VideoProvider>("local_ltx");

  const [loading, setLoading] = useState(true);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preselect a mode from a handoff (Animate/Upscale This …) or a ?mode= query,
  // and auto-attach the source media. Query-param source is re-validated here.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const valid: VideoMode[] = [
      "image_to_video",
      "text_to_video",
      "video_to_video",
      "video_upscale",
      "video_extension",
    ];
    const pending = consumeHandoff();
    const sp = new URLSearchParams(window.location.search);
    const requested = (pending?.targetMode ?? sp.get("mode")) as string | null;
    const src = pending?.sourceUrl ?? sp.get("source");
    if (requested && (valid as string[]).includes(requested)) {
      setVideoMode(requested as VideoMode);
    }
    if (src) {
      const accept = requested === "image_to_video" ? (["image"] as const) : (["video"] as const);
      if (validateSourceUrl(src, [...accept]).ok) {
        setSourceUrl(src);
        setAutoAttachedFrom(pending?.originLabel ?? "from a previous step");
      }
    }
  }, []);

  const projectScenes = useMemo(
    () =>
      scenes.filter((s) => s.project_id === projectId && s.status === "completed"),
    [scenes, projectId],
  );
  const selectedMode = videoModes.find((mode) => mode.id === videoMode);
  const sourceRequired = selectedMode?.source_required ?? videoMode !== "text_to_video";
  const selectedProviderReadiness = selectedMode?.providers?.[provider];
  const selectedProviderReady =
    provider === "local_ltx"
      ? selectedMode?.available ?? true
      : selectedProviderReadiness?.available ?? false;
  const selectedCost = selectedProviderReadiness?.cost ?? (provider === "seedance_api" ? 30 : 10);
  const providerBlockReason =
    provider === "seedance_api" && !selectedProviderReady
      ? selectedProviderReadiness?.note ?? "Seedance provider is not configured. Admin setup required."
      : null;
  const selectedQuality =
    QUALITY_PRESETS.find((item) => item.value === qualityPreset) ?? QUALITY_PRESETS[1];

  useEffect(() => {
    async function load() {
      try {
        const [projectList, sceneList, videoList] = await Promise.all([
          api.listProjects(),
          api.listProductScenes(),
          api.listVideos(),
        ]);
        api.getStatus().then(setAppStatus).catch(() => setAppStatus(null));
        api.listVideoModes().then(setVideoModes).catch(() => setVideoModes([]));
        setProjects(projectList);
        setScenes(sceneList);
        setVideos(videoList);
        setProjectId(projectList[0]?.id ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load videos");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function refreshStatus() {
    setRefreshingStatus(true);
    try {
      setAppStatus(await api.getStatus());
    } catch {
      setAppStatus(null);
    } finally {
      setRefreshingStatus(false);
    }
  }

  useEffect(() => {
    setSceneId((current) =>
      projectScenes.some((s) => s.id === current)
        ? current
        : projectScenes[0]?.id ?? "",
    );
  }, [projectScenes]);

  useEffect(() => {
    const active = videos.filter(
      (v) => v.status === "queued" || v.status === "running",
    );
    if (active.length === 0) return;
    const poll = window.setInterval(async () => {
      const updates = await Promise.all(active.map((v) => api.getVideo(v.id)));
      setVideos((current) =>
        current.map((v) => updates.find((u) => u.id === v.id) ?? v),
      );
    }, 2500);
    return () => window.clearInterval(poll);
  }, [videos]);

  async function trashVideo(id: string) {
    if (
      !window.confirm(
        "Move this video to trash? This will remove it from the gallery but keep a recoverable copy.",
      )
    )
      return;
    try {
      await api.trashAsset({ entity_type: "video", entity_id: id });
      setVideos((cur) => cur.filter((v) => v.id !== id));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not move video to trash";
      if (
        msg.toLowerCase().includes("referenced") &&
        window.confirm(`${msg}\n\nMove to trash anyway?`)
      ) {
        await api.trashAsset({ entity_type: "video", entity_id: id, force_referenced: true });
        setVideos((cur) => cur.filter((v) => v.id !== id));
      } else {
        setError(msg);
      }
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const source = sourceUrl.trim();
    const sceneSource = videoMode === "image_to_video" ? sceneId : "";
    if (
      !projectId ||
      !prompt.trim() ||
      submitting ||
      !selectedProviderReady ||
      (sourceRequired && !sceneSource && !source)
    ) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const video = await api.createVideo({
        project_id: projectId,
        product_scene_id: sceneSource || null,
        source_image_url: source || null,
        prompt: prompt.trim(),
        motion_preset: motionPreset,
        duration_seconds: duration,
        mode: videoMode,
        provider,
        quality_preset: qualityPreset,
        brief_id: briefId || null,
      });
      setVideos((current) => [video, ...current]);
      setPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Video generation failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <VideoModeBanner
        status={appStatus}
        refreshing={refreshingStatus}
        onRefresh={refreshStatus}
      />
      <ActiveConfigBadge fields={["video_backend"]} />
      <div className="grid gap-8 lg:grid-cols-[400px_1fr]">
      <form
        onSubmit={handleSubmit}
        className="h-fit space-y-5 rounded-lg border border-border bg-card p-6"
      >
        <div className="space-y-2">
          <Label>Creative preset</Label>
          <div className="grid gap-2">
            {VIDEO_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setMotionPreset(preset.motion);
                  setDuration(preset.duration);
                }}
                className={cn(
                  "rounded-md border px-3 py-2 text-left transition-colors",
                  motionPreset === preset.motion && duration === preset.duration
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                <span className="block text-sm font-medium">{preset.label}</span>
                <span className="block text-xs">{preset.description}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Video quality mode</Label>
          <div className="grid gap-2">
            {QUALITY_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={() => setQualityPreset(preset.value)}
                className={cn(
                  "rounded-md border px-3 py-2 text-left transition-colors",
                  qualityPreset === preset.value
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                <span className="flex items-center justify-between gap-2 text-sm font-medium">
                  {preset.label}
                  {preset.value === "safe_preview" ? (
                    <Badge variant="muted">Preview</Badge>
                  ) : preset.value === "image_to_video_best" ? (
                    <Badge variant="outline">Recommended for subjects</Badge>
                  ) : null}
                </span>
                <span className="mt-1 block text-xs">{preset.description}</span>
                <span className="mt-1 block text-xs">{preset.bestFor}</span>
              </button>
            ))}
          </div>
          {videoMode === "text_to_video" ? (
            <p className="text-xs text-muted-foreground">
              For clear dogs, people, products, or character continuity, generate a strong
              still first and use Image -&gt; Video.
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label>Video provider</Label>
          <div className="grid gap-2">
            {PROVIDERS.map((item) => {
              const readiness = selectedMode?.providers?.[item.id];
              const available =
                item.id === "local_ltx"
                  ? selectedMode?.available ?? true
                  : readiness?.available ?? false;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => available && setProvider(item.id)}
                  disabled={!available}
                  className={cn(
                    "rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                    provider === item.id
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  <span className="flex items-center justify-between gap-2 text-sm font-medium">
                    {item.label}
                    <Badge variant={item.id === "seedance_api" ? "default" : "outline"}>
                      {item.badge}
                    </Badge>
                  </span>
                  <span className="mt-1 block text-xs">
                    Cost: {readiness?.cost ?? (item.id === "seedance_api" ? 30 : 10)} credits
                  </span>
                  {!available && readiness?.note ? (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {readiness.note}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Video mode</Label>
          <div className="grid gap-2">
            {(videoModes.length
              ? videoModes
              : [
                  {
                    id: "image_to_video" as VideoMode,
                    name: "Image -> Video",
                    description: "Animate a completed scene.",
                    source_required: true,
                    available: true,
                    backend: "Mock",
                    note: null,
                  },
                  {
                    id: "text_to_video" as VideoMode,
                    name: "Text -> Video",
                    description: "Generate from prompt only.",
                    source_required: false,
                    available: true,
                    backend: "Mock",
                    note: null,
                  },
                ]).map((mode) => (
              <button
                key={mode.id}
                type="button"
                onClick={() => setVideoMode(mode.id)}
                disabled={!mode.available}
                className={cn(
                  "rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                  videoMode === mode.id
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                <span className="flex items-center justify-between gap-2 text-sm font-medium">
                  {mode.name}
                  <Badge variant={mode.available ? "outline" : "muted"}>
                    {mode.available ? mode.backend : "Not wired yet"}
                  </Badge>
                </span>
                <span className="mt-1 block text-xs">{mode.description}</span>
                {mode.note ? (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {mode.note}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>

        {videoMode === "image_to_video" ? (
          <div className="space-y-2">
          <Label htmlFor="video-project">Project</Label>
          <select
            id="video-project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className={selectClass}
          >
            {projects.length === 0 ? <option value="">No projects</option> : null}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        ) : null}

        {videoMode !== "image_to_video" ? (
          <div className="space-y-2">
            <Label htmlFor="video-project">Project</Label>
            <select
              id="video-project"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className={selectClass}
            >
              {projects.length === 0 ? <option value="">No projects</option> : null}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {videoMode === "image_to_video" ? (
        <div className="space-y-2">
          <Label htmlFor="video-scene">Completed product scene</Label>
          <select
            id="video-scene"
            value={sceneId}
            onChange={(e) => setSceneId(e.target.value)}
            className={selectClass}
          >
            {projectScenes.length === 0 ? (
              <option value="">No completed scenes</option>
            ) : null}
            {projectScenes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.prompt.slice(0, 44)}
              </option>
            ))}
          </select>
        </div>
        ) : null}

        {sourceRequired ? (
          <div className="space-y-2">
            <Label htmlFor="video-source">
              {videoMode === "image_to_video"
                ? "Source URL override"
                : "Source video/image URL"}
            </Label>
            {autoAttachedFrom && sourceUrl ? (
              <p className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                Auto-attached {autoAttachedFrom}
              </p>
            ) : null}
            <Input
              id="video-source"
              value={sourceUrl}
              onChange={(event) => {
                setSourceUrl(event.target.value);
                setAutoAttachedFrom(null);
              }}
              placeholder="/storage/videos/example.mp4 or /storage/product-scenes/example.png"
            />
            <p className="text-xs text-muted-foreground">
              {videoMode === "image_to_video"
                ? "Optional when a completed scene is selected."
                : "Required for this video mode. Use a local /storage/videos/... MP4 for video workflows."}
            </p>
          </div>
        ) : null}

        <div className="space-y-2">
          <Label>Motion preset</Label>
          <div className="grid grid-cols-2 gap-2">
            {MOTION_PRESETS.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => setMotionPreset(m.value)}
                className={cn(
                  "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                  motionPreset === m.value
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Duration</Label>
          <div className="grid grid-cols-4 gap-2">
            {DURATIONS.map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDuration(d)}
                className={cn(
                  "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                  duration === d
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {d}s
              </button>
            ))}
          </div>
        </div>

        <BriefSelect
          projectId={projectId}
          value={briefId}
          onChange={setBriefId}
          id="video-brief"
        />

        <div className="space-y-2">
          <Label htmlFor="video-prompt">
            {videoMode === "text_to_video"
              ? "Describe the video you want to create"
              : "Motion prompt"}
          </Label>
          <Textarea
            id="video-prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={
              videoMode === "text_to_video"
                ? "Large golden retriever walking toward the camera in a sunny park, dog fills much of the frame, clear visible dog, smooth natural walking motion, realistic daylight, simple background."
                : "Describe the motion, e.g. slow push toward the product with subtle parallax"
            }
            className="min-h-[100px]"
          />
          <p className="text-xs text-muted-foreground">
            {selectedQuality.label}: {selectedQuality.description}
          </p>
        </div>

        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        {providerBlockReason ? (
          <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
            {providerBlockReason}
          </p>
        ) : null}

        <div className="flex items-center gap-3">
          <Button
            type="submit"
            size="lg"
            disabled={
              !projectId ||
              !prompt.trim() ||
              submitting ||
              !selectedProviderReady ||
              (sourceRequired &&
                !(videoMode === "image_to_video" && sceneId) &&
                !sourceUrl.trim())
            }
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Generating…
              </>
            ) : (
              <>
                <Film className="h-4 w-4" />{" "}
                {videoMode === "text_to_video" ? "Generate Video" : "Generate video"}
              </>
            )}
          </Button>
          <span className="text-sm text-muted-foreground">Cost: {selectedCost} credits</span>
        </div>
      </form>

      <div>
        <h3 className="mb-4 text-sm font-semibold">Video history</h3>
        {videos.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <Film className="h-7 w-7" />
            No videos yet.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {videos.map((video) => (
              <VideoCard key={video.id} video={video} onTrash={trashVideo} onAction={onAction} />
            ))}
          </div>
        )}
      </div>
      </div>
      <StoryboardPlanner projectId={projectId} />
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function VideoModeBanner({
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
              <Badge variant="outline">Real LTX video mode</Badge>
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

function VideoCard({
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
            {video.provider === "seedance_api" ? "Seedance" : "Local LTX"}
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

function StoryboardPlanner({ projectId }: { projectId: string }) {
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
