"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
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
import { BriefSelect } from "@/components/brief-select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { consumeHandoff, peekHandoff } from "@/lib/stores/useMediaHandoff";
import { videoToMedia } from "@/lib/utils/mediaMapping";
import { validateSourceUrl } from "@/lib/utils/validateSourceUrl";
import { cn } from "@/lib/utils";
import { StoryboardPlanner, VideoCard, VideoModeBanner } from "@/components/video-studio/video-studio-panels";
import { safeInterval } from "@/lib/safe-interval";

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
    description: "Short clip with gentle motion",
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
    value: "wan_smooth",
    label: "Wan Natural Speed",
    description: "512x320 at 16 frames per second (Wan text-to-video).",
    bestFor: "Realistic motion speed; a 4 s clip takes about 80 seconds.",
  },
  {
    value: "image_to_video_best",
    label: "Image-to-Video Best",
    description: "640x384 with stronger source-image preservation.",
    bestFor: "Best for dogs, people, products, and characters.",
  },
];

// MiniMax H3 effect embeddings (files in ComfyUI models/embeddings). Clicking a chip adds its tag to the prompt.
const H3_EFFECTS: { id: string; label: string }[] = [
  { id: "minimaxh3_art_is_explosion", label: "Art explosion" },
  { id: "minimaxh3_blooming_flowers", label: "Blooming flowers" },
  { id: "minimaxh3_bullet_time", label: "Bullet time" },
  { id: "minimaxh3_dark_magic", label: "Dark magic" },
  { id: "minimaxh3_fire_breath", label: "Fire breath" },
  { id: "minimaxh3_four_seasons", label: "Four seasons" },
  { id: "minimaxh3_kiss_camera", label: "Kiss the camera" },
  { id: "minimaxh3_spiral_ascent", label: "Spiral ascent" },
  { id: "minimaxh3_storm_magic", label: "Storm magic" },
  { id: "minimaxh3_truman_show", label: "Truman show" },
];

// MiniMax H3 has its own quality choices (and makes sound with the picture).
const H3_QUALITY_PRESETS: typeof QUALITY_PRESETS = [
  {
    value: "h3_turbo",
    label: "Fast (turbo)",
    description: "4 steps, about 30-50 seconds for a short clip.",
    bestFor: "Recommended default.",
  },
  {
    value: "h3_full",
    label: "Full quality",
    description: "20 steps without the turbo add-on, several times slower.",
    bestFor: "When detail matters more than speed.",
  },
  {
    value: "h3_reference",
    label: "Keep my subject",
    description: "Uses the picture as a reference, so the same person appears in a brand-new scene.",
    bestFor: "Image -> Video only. Describe the new scene and mention <Picture 1>.",
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
  { id: "local_ltx", label: "Local LTX", badge: "Extend / upscale" },
  { id: "local_wan", label: "Wan 2.1 (local)", badge: "Image → Video" },
  { id: "local_h3", label: "MiniMax H3 (video + sound)", badge: "Default generation" },
  { id: "seedance_api", label: "Seedance / C-Dance 2.0", badge: "Premium" },
];

export function VideosView() {
  const searchParams = useSearchParams();
  const handoffQuery = searchParams.toString();
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
    useState<VideoQualityPreset>("h3_turbo");
  const [briefId, setBriefId] = useState("");
  const [videoModes, setVideoModes] = useState<VideoModeOption[]>([]);
  const [videoMode, setVideoMode] = useState<VideoMode>("image_to_video");
  const [providerChoices, setProviderChoices] = useState<Partial<Record<VideoMode, VideoProvider>>>({});
  const provider = providerChoices[videoMode] ??
    (videoMode === "video_extension" || videoMode === "video_upscale" ? "local_ltx" : "local_h3");

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
    const waiting = peekHandoff();
    const pending = waiting?.targetRoute === "/videos" ? consumeHandoff() : null;
    const sp = new URLSearchParams(handoffQuery);
    const requested = (pending?.targetMode ?? sp.get("mode")) as string | null;
    const src = pending?.sourceUrl ?? sp.get("source");
    const plannedPrompt = sp.get("prompt");
    if (plannedPrompt) setPrompt(plannedPrompt.slice(0, 8000));
    const plannedDuration = Number(sp.get("duration"));
    if ([3, 5, 8, 10].includes(plannedDuration)) setDuration(plannedDuration);
    if (requested && (valid as string[]).includes(requested)) {
      setVideoMode(requested as VideoMode);
      setSceneId("");
      const accept = requested === "image_to_video" ? (["image"] as const) : (["video"] as const);
      if (requested !== "text_to_video" && src && validateSourceUrl(src, [...accept]).ok) {
        setSourceUrl(src);
        setAutoAttachedFrom(pending?.originLabel ?? "from a previous step");
        setError(null);
      } else {
        // Never leave the previous valid clip attached to an incompatible handoff.
        setSourceUrl("");
        setAutoAttachedFrom(null);
        if (src && requested !== "text_to_video") setError("This source is not compatible with the selected video mode. Choose a matching image or video.");
      }
    }
  }, [handoffQuery]);

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
    provider !== "local_ltx" && !selectedProviderReady
      ? selectedProviderReadiness?.note ??
        (provider === "seedance_api"
          ? "Seedance provider is not configured. Admin setup required."
          : provider === "local_h3" ? "MiniMax H3 is not ready for this mode." : "Wan 2.1 is not available for this mode.")
      : null;
  const presets = provider === "local_h3" ? H3_QUALITY_PRESETS : QUALITY_PRESETS;
  const selectedQuality = presets.find((item) => item.value === qualityPreset) ?? presets[provider === "local_h3" ? 0 : 1];

  // Keep the quality choice valid for the provider (H3 and LTX have different lists).
  useEffect(() => {
    if (!presets.some((item) => item.value === qualityPreset)) setQualityPreset(presets[provider === "local_h3" ? 0 : 1].value);
  }, [provider]); // eslint-disable-line react-hooks/exhaustive-deps

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
        setProjectId((current) => current || projectList[0]?.id || "");
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
    const poll = safeInterval(async () => {
      const updates = await Promise.all(active.map((v) => api.getVideo(v.id)));
      setVideos((current) =>
        current.map((v) => updates.find((u) => u.id === v.id) ?? v),
      );
    }, 2500);
    return poll;
  }, [videos]);

  async function trashVideo(id: string) {
    if (
      !await confirmDialog(
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
        await confirmDialog(`${msg}\n\nMove to trash anyway?`)
      ) {
        try {
          await api.trashAsset({ entity_type: "video", entity_id: id, force_referenced: true });
          setVideos((cur) => cur.filter((v) => v.id !== id));
        } catch (retryErr) {
          setError(retryErr instanceof Error ? retryErr.message : "Could not move video to trash");
        }
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
      <p className="text-sm text-muted-foreground">Selected provider: {PROVIDERS.find((item) => item.id === provider)?.label}</p>
      <details className="rounded-lg border border-border bg-card p-4">
        <summary className="cursor-pointer text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">
          Free online video tools
        </summary>
        <p className="mt-3 max-w-prose text-sm text-muted-foreground">
          Keep local generation as your default, or open a free service below.
          Sign in on the provider&apos;s website if needed, choose its free option,
          and download your finished clip. Availability and limits vary by service.
        </p>
        <nav aria-label="Free video services" className="mt-3 flex flex-wrap gap-2">
          {[
            ["ZSky", "https://zsky.ai/create"],
            ["UsefulShelf", "https://usefulshelf.com/en/ai-tools"],
            ["Viggle", "https://viggle.ai/tools"],
            ["GizAI", "https://www.giz.ai/ai-video-generator/"],
          ].map(([name, href]) => (
            <a key={name} href={href} target="_blank" rel="noopener noreferrer"
              className={buttonVariants({ variant: "outline", size: "sm" })}>
              Open {name}<span className="sr-only"> (new tab)</span>
            </a>
          ))}
        </nav>
        <p className="mt-3 text-sm text-muted-foreground">
          These links open external websites. Clips are not automatically imported into Sovereign.
        </p>
      </details>
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
            {presets.map((preset) => (
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
                  onClick={() => available && setProviderChoices((choices) => ({ ...choices, [videoMode]: item.id }))}
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
                    {provider === "local_ltx" ? (mode.available ? mode.backend : "Unavailable") : (mode.providers?.[provider]?.available ? PROVIDERS.find((item) => item.id === provider)?.label : "Unavailable for this provider")}
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
              <p className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
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
          {provider === "local_h3" ? (
            <div>
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Effects (click to add to the prompt)</p>
              <div className="flex flex-wrap gap-1.5">
                {H3_EFFECTS.map((fx) => {
                  const tag = `embedding:${fx.id}`;
                  const on = prompt.includes(tag);
                  return (
                    <button
                      key={fx.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setPrompt((cur) => (cur.includes(tag) ? cur.replace(tag, "").replace(/\s{2,}/g, " ").trim() : `${cur.trim()} ${tag}`.trim()))}
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-xs transition-colors",
                        on ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {fx.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>

        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        {providerBlockReason ? (
          <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
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
