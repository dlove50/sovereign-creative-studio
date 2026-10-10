"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Download,
  Film,
  ImageIcon,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  Video,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  ProductAsset,
  ProductSceneGeneration,
  Project,
  VideoGeneration,
  VideoMotionPreset,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { safeInterval } from "@/lib/safe-interval";

type ShotType = "wide" | "medium" | "closeup" | "tracking" | "hero";
type FilmMood = "luxury" | "noir" | "sunset" | "neon" | "studio";

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);

const SHOT_TYPES: { value: ShotType; label: string; prompt: string }[] = [
  { value: "wide", label: "Wide", prompt: "wide establishing shot, full body composition" },
  { value: "medium", label: "Medium", prompt: "medium shot, waist-up cinematic framing" },
  { value: "closeup", label: "Closeup", prompt: "close-up fashion film frame, expressive face and styling" },
  { value: "tracking", label: "Tracking", prompt: "tracking-shot feel, subject moving through the scene" },
  { value: "hero", label: "Hero", prompt: "premium hero shot, dramatic campaign composition" },
];

const MOODS: { value: FilmMood; label: string; prompt: string }[] = [
  { value: "luxury", label: "Luxury", prompt: "luxury fashion campaign, refined premium lighting" },
  { value: "noir", label: "Noir", prompt: "cinematic noir lighting, deep contrast, elegant shadows" },
  { value: "sunset", label: "Sunset", prompt: "golden hour light, warm editorial atmosphere" },
  { value: "neon", label: "Neon", prompt: "rainy neon city ambience, reflective cinematic color" },
  { value: "studio", label: "Studio", prompt: "controlled studio set, polished commercial lighting" },
];

const MOTIONS: { value: VideoMotionPreset; label: string }[] = [
  { value: "product_motion", label: "Product Motion" },
  { value: "cinematic_push", label: "Cinematic Push" },
  { value: "runway_walk", label: "Runway Walk" },
  { value: "dolly_in", label: "Dolly In" },
  { value: "parallax", label: "Parallax" },
  { value: "slow_zoom", label: "Slow Zoom" },
  { value: "handheld", label: "Handheld" },
  { value: "orbit", label: "Orbit" },
  { value: "product_reveal", label: "Reveal" },
  { value: "subtle_breathing", label: "Subtle Breathing" },
];

const SCENE_STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const VIDEO_STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function FilmStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [videos, setVideos] = useState<VideoGeneration[]>([]);
  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [shotType, setShotType] = useState<ShotType>("wide");
  const [mood, setMood] = useState<FilmMood>("luxury");
  const [motion, setMotion] = useState<VideoMotionPreset>("product_motion");
  const [characterLock, setCharacterLock] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [submittingScene, setSubmittingScene] = useState(false);
  const [submittingVideo, setSubmittingVideo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [latestSceneId, setLatestSceneId] = useState("");
  const [latestVideoId, setLatestVideoId] = useState("");

  const readyAssets = useMemo(
    () =>
      assets.filter(
        (asset) =>
          asset.project_id === projectId && READY_ASSET_STATUSES.has(asset.status),
      ),
    [assets, projectId],
  );
  const selectedAsset = readyAssets.find((asset) => asset.id === assetId) ?? null;
  const filmScenes = useMemo(
    () => scenes.filter((scene) => scene.project_id === projectId && scene.mode === "film_scene"),
    [projectId, scenes],
  );
  const projectVideos = useMemo(
    () => videos.filter((video) => video.project_id === projectId),
    [projectId, videos],
  );
  const latestScene =
    scenes.find((scene) => scene.id === latestSceneId) ?? filmScenes[0] ?? null;
  const latestVideo =
    videos.find((video) => video.id === latestVideoId) ??
    projectVideos.find((video) => video.product_scene_id === latestScene?.id) ??
    null;
  const activeScene = latestScene?.status === "queued" || latestScene?.status === "running";
  const activeVideo = latestVideo?.status === "queued" || latestVideo?.status === "running";

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    setAssetId((current) =>
      readyAssets.some((asset) => asset.id === current)
        ? current
        : readyAssets[0]?.id ?? "",
    );
  }, [readyAssets]);

  useEffect(() => {
    const activeScenes = scenes.filter(
      (scene) =>
        scene.mode === "film_scene" &&
        (scene.status === "queued" || scene.status === "running"),
    );
    if (activeScenes.length === 0) return;
    const poll = safeInterval(async () => {
      const updates = await Promise.all(activeScenes.map((scene) => api.getProductScene(scene.id)));
      setScenes((current) =>
        current.map((scene) => updates.find((update) => update.id === scene.id) ?? scene),
      );
    }, 2500);
    return poll;
  }, [scenes]);

  useEffect(() => {
    const activeVideos = videos.filter(
      (video) => video.status === "queued" || video.status === "running",
    );
    if (activeVideos.length === 0) return;
    const poll = safeInterval(async () => {
      const updates = await Promise.all(activeVideos.map((video) => api.getVideo(video.id)));
      setVideos((current) =>
        current.map((video) => updates.find((update) => update.id === video.id) ?? video),
      );
    }, 3000);
    return poll;
  }, [videos]);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [projectList, assetList, sceneList, videoList] = await Promise.all([
        api.listProjects(),
        api.listAssets(undefined, "product_scenes"),
        api.listProductScenes(),
        api.listVideos(),
      ]);
      setProjects(projectList);
      setAssets(assetList);
      setScenes(sceneList);
      setVideos(videoList);
      const firstProject =
        assetList.find((asset) => READY_ASSET_STATUSES.has(asset.status))?.project_id ??
        projectList[0]?.id ??
        "";
      setProjectId(firstProject);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load Film Studio");
    } finally {
      setLoading(false);
    }
  }

  function filmPrompt() {
    const shot = SHOT_TYPES.find((item) => item.value === shotType)?.prompt ?? "";
    const moodText = MOODS.find((item) => item.value === mood)?.prompt ?? "";
    return [
      prompt.trim(),
      shot,
      moodText,
      "cinematic keyframe, fashion film still, professional production design",
    ]
      .filter(Boolean)
      .join(", ");
  }

  async function generateKeyframe(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId || !assetId || !prompt.trim() || submittingScene || activeScene) return;
    setSubmittingScene(true);
    setError(null);
    setNotice(null);
    try {
      const scene = await api.createProductScene({
        project_id: projectId,
        asset_id: assetId,
        prompt: filmPrompt(),
        preset: "studio",
        mode: "film_scene",
      });
      setScenes((current) => [scene, ...current]);
      setLatestSceneId(scene.id);
      setNotice("Film keyframe queued.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create film keyframe");
    } finally {
      setSubmittingScene(false);
    }
  }

  async function animateKeyframe() {
    if (!latestScene || latestScene.status !== "completed" || submittingVideo || activeVideo) return;
    setSubmittingVideo(true);
    setError(null);
    setNotice(null);
    try {
      const video = await api.createVideo({
        project_id: latestScene.project_id,
        product_scene_id: latestScene.id,
        prompt: [
          latestScene.prompt,
          `${motion.replaceAll("_", " ")} camera movement`,
          characterLock
            ? "preserve the same person, face, body proportions, outfit, colors, and product details from the source keyframe"
            : "allow moderate cinematic transformation while keeping the shot coherent",
          "production-ready fashion film clip, no duplicated subject, no warped anatomy",
        ].join(", "),
        motion_preset: motion,
        duration_seconds: 3,
        mode: "image_to_video",
      });
      setVideos((current) => [video, ...current]);
      setLatestVideoId(video.id);
      setNotice("Video clip queued.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not animate keyframe");
    } finally {
      setSubmittingVideo(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const sourceUrl = assetUrl(selectedAsset?.processed_url ?? selectedAsset?.original_url ?? null);
  const keyframeUrl = assetUrl(latestScene?.result_url ?? null);
  const videoUrl = assetUrl(latestVideo?.result_url ?? null);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <form onSubmit={generateKeyframe} className="space-y-5 rounded-lg border border-border bg-card p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Cinematic keyframe</h2>
              <p className="text-sm text-muted-foreground">
                Build a film still from a product asset, then send it to Video Studio.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={loadAll}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="film-project">Project</Label>
              <select id="film-project" value={projectId} onChange={(event) => setProjectId(event.target.value)} className={selectClass}>
                {projects.length === 0 ? <option value="">No projects</option> : null}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="film-asset">Source asset</Label>
              <select id="film-asset" value={assetId} onChange={(event) => setAssetId(event.target.value)} className={selectClass}>
                {readyAssets.length === 0 ? <option value="">No ready assets</option> : null}
                {readyAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>{asset.filename}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="film-shot">Shot</Label>
              <select id="film-shot" value={shotType} onChange={(event) => setShotType(event.target.value as ShotType)} className={selectClass}>
                {SHOT_TYPES.map((shot) => (
                  <option key={shot.value} value={shot.value}>{shot.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="film-mood">Look</Label>
              <select id="film-mood" value={mood} onChange={(event) => setMood(event.target.value as FilmMood)} className={selectClass}>
                {MOODS.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="film-motion">Motion</Label>
              <select id="film-motion" value={motion} onChange={(event) => setMotion(event.target.value as VideoMotionPreset)} className={selectClass}>
                {MOTIONS.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </div>
          </div>

          <label className="flex items-start gap-3 rounded-md border border-border bg-background/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={characterLock}
              onChange={(event) => setCharacterLock(event.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="block font-medium">Character consistency lock</span>
              <span className="text-muted-foreground">
                Preserve the same person, styling, clothing colors, and product details while adding motion.
              </span>
            </span>
          </label>

          <div className="space-y-2">
            <Label htmlFor="film-prompt">Scene direction</Label>
            <Textarea
              id="film-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="min-h-[120px]"
              placeholder="A fashion protagonist entering a Milan boutique, premium campaign film, confident expression"
            />
          </div>

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
          ) : null}
          {notice ? (
            <p className="rounded-md bg-emerald-500/15 px-3 py-2 text-sm text-emerald-300">{notice}</p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!projectId || !assetId || !prompt.trim() || submittingScene || activeScene}>
              {submittingScene || activeScene ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Creating keyframe
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" /> Generate keyframe
                </>
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={animateKeyframe}
              disabled={!latestScene || latestScene.status !== "completed" || submittingVideo || activeVideo}
            >
              {submittingVideo || activeVideo ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Animating
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" /> Animate keyframe
                </>
              )}
            </Button>
          </div>
        </form>

        <div className="space-y-5">
          <PreviewCard title="Source" status={selectedAsset?.status} url={sourceUrl} empty="Select a ready asset." />
          <PreviewCard title="Latest keyframe" status={latestScene?.status} url={keyframeUrl} empty="Generate a film keyframe." />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Film keyframes</h2>
              <Badge variant="outline">{filmScenes.length}</Badge>
            </div>
            {filmScenes.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                No film keyframes yet.
              </p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {filmScenes.map((scene) => (
                  <button
                    type="button"
                    key={scene.id}
                    onClick={() => setLatestSceneId(scene.id)}
                    className={cn(
                      "overflow-hidden rounded-md border text-left transition-colors",
                      latestScene?.id === scene.id ? "border-primary" : "border-border hover:bg-muted",
                    )}
                  >
                    <div className="relative aspect-video bg-background/60">
                      {scene.result_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={assetUrl(scene.result_url) ?? ""} alt={scene.prompt} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-muted-foreground">
                          <ImageIcon className="h-6 w-6" />
                        </div>
                      )}
                      <Badge variant={SCENE_STATUS_VARIANT[scene.status]} className="absolute right-2 top-2 capitalize">
                        {scene.status}
                      </Badge>
                    </div>
                    <p className="line-clamp-2 p-3 text-sm">{scene.prompt}</p>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Latest clip</h2>
              {latestVideo ? (
                <Badge variant={VIDEO_STATUS_VARIANT[latestVideo.status]} className="capitalize">{latestVideo.status}</Badge>
              ) : null}
            </div>
            <div className="aspect-video overflow-hidden rounded-md border border-border bg-background/60">
              {videoUrl ? (
                <video src={videoUrl} controls className="h-full w-full object-contain" />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Video className="h-7 w-7" />
                  Animate a completed keyframe.
                </div>
              )}
            </div>
            {latestVideo?.status === "completed" ? (
              <a href={api.exportVideoUrl(latestVideo.id)} className={cn(buttonVariants({ variant: "outline" }), "w-full")}>
                <Download className="h-4 w-4" /> Download clip
              </a>
            ) : null}
            {latestVideo?.status === "failed" && latestVideo.error ? (
              <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{latestVideo.error}</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Video assets</h2>
            <Badge variant="outline">{projectVideos.length}</Badge>
          </div>
          {projectVideos.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
              No video assets for this project yet.
            </p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {projectVideos.map((video) => {
                const url = assetUrl(video.result_url ?? null);
                return (
                  <button
                    type="button"
                    key={video.id}
                    onClick={() => setLatestVideoId(video.id)}
                    className={cn(
                      "overflow-hidden rounded-md border text-left transition-colors",
                      latestVideo?.id === video.id ? "border-primary" : "border-border hover:bg-muted",
                    )}
                  >
                    <div className="relative aspect-video bg-background/60">
                      {url ? (
                        <video src={url} className="h-full w-full object-cover" muted />
                      ) : (
                        <div className="flex h-full items-center justify-center text-muted-foreground">
                          <Video className="h-6 w-6" />
                        </div>
                      )}
                      <Badge variant={VIDEO_STATUS_VARIANT[video.status]} className="absolute right-2 top-2 capitalize">
                        {video.status}
                      </Badge>
                    </div>
                    <div className="space-y-1 p-3">
                      <p className="line-clamp-2 text-sm">{video.prompt}</p>
                      <p className="text-xs text-muted-foreground">
                        {video.motion_preset.replaceAll("_", " ")} - {video.duration_seconds}s
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PreviewCard({
  empty,
  status,
  title,
  url,
}: {
  empty: string;
  status?: string | null;
  title: string;
  url: string | null;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">{title}</h2>
          {status ? <Badge variant="outline" className="capitalize">{status}</Badge> : null}
        </div>
        <div className="aspect-video overflow-hidden rounded-md border border-border bg-background/60">
          {url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={title} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <Film className="h-7 w-7" />
              {empty}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
