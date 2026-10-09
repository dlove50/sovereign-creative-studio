"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Clipboard,
  Download,
  Film,
  ImageIcon,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Video,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  ProductAsset,
  ProductSceneGeneration,
  Project,
  Shot,
  Storyboard,
  VideoGeneration,
  VideoMotionPreset,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);
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
const MOTION_PRESETS: { value: VideoMotionPreset; label: string }[] = [
  { value: "cinematic_push", label: "Cinematic push" },
  { value: "runway_walk", label: "Runway walk" },
  { value: "product_motion", label: "Product motion" },
  { value: "parallax", label: "Parallax" },
  { value: "slow_zoom", label: "Slow zoom" },
];

export function StoryboardStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [storyboards, setStoryboards] = useState<Storyboard[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [shots, setShots] = useState<Shot[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [assetId, setAssetId] = useState("");
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [videos, setVideos] = useState<VideoGeneration[]>([]);
  const [shotSceneIds, setShotSceneIds] = useState<Record<string, string>>({});
  const [shotVideoIds, setShotVideoIds] = useState<Record<string, string>>({});

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("draft");
  const [shotDescription, setShotDescription] = useState("");
  const [cameraNotes, setCameraNotes] = useState("");
  const [continuityNotes, setContinuityNotes] = useState(
    "Preserve the same character identity, outfit, colors, and proportions across shots.",
  );
  const [generationPrompt, setGenerationPrompt] = useState("");
  const [duration, setDuration] = useState(5);
  const [motionPreset, setMotionPreset] =
    useState<VideoMotionPreset>("cinematic_push");

  const [loading, setLoading] = useState(true);
  const [savingBoard, setSavingBoard] = useState(false);
  const [savingShot, setSavingShot] = useState(false);
  const [generatingShotId, setGeneratingShotId] = useState("");
  const [animatingShotId, setAnimatingShotId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = storyboards.find((item) => item.id === selectedId) ?? null;
  const orderedShots = useMemo(
    () => [...shots].sort((a, b) => a.shot_number - b.shot_number),
    [shots],
  );
  const completedVideos = videos.filter((video) => video.status === "completed");
  const readyAssets = assets.filter((asset) =>
    READY_ASSET_STATUSES.has(asset.status),
  );
  const totalDuration = orderedShots.reduce(
    (total, shot) => total + shot.duration_seconds,
    0,
  );

  useEffect(() => {
    loadInitial();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    loadProject(projectId);
  }, [projectId]);

  useEffect(() => {
    setAssetId((current) =>
      readyAssets.some((asset) => asset.id === current)
        ? current
        : readyAssets[0]?.id ?? "",
    );
  }, [readyAssets]);

  useEffect(() => {
    if (!selectedId) {
      setShots([]);
      return;
    }
    api
      .listShots(selectedId)
      .then((loaded) => {
        setShots(loaded);
        setShotSceneIds(
          Object.fromEntries(
            loaded
              .filter((shot) => shot.product_scene_id)
              .map((shot) => [shot.id, shot.product_scene_id as string]),
          ),
        );
        setShotVideoIds(
          Object.fromEntries(
            loaded
              .filter((shot) => shot.video_id)
              .map((shot) => [shot.id, shot.video_id as string]),
          ),
        );
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load shots"),
      );
  }, [selectedId]);

  useEffect(() => {
    const activeScenes = scenes.filter(
      (scene) => scene.status === "queued" || scene.status === "running",
    );
    if (activeScenes.length === 0) return;
    const poll = window.setInterval(async () => {
      const updates = await Promise.all(
        activeScenes.map((scene) => api.getProductScene(scene.id)),
      );
      setScenes((current) =>
        current.map(
          (scene) => updates.find((update) => update.id === scene.id) ?? scene,
        ),
      );
    }, 2500);
    return () => window.clearInterval(poll);
  }, [scenes]);

  useEffect(() => {
    const activeVideos = videos.filter(
      (video) => video.status === "queued" || video.status === "running",
    );
    if (activeVideos.length === 0) return;
    const poll = window.setInterval(async () => {
      const updates = await Promise.all(
        activeVideos.map((video) => api.getVideo(video.id)),
      );
      setVideos((current) =>
        current.map(
          (video) => updates.find((update) => update.id === video.id) ?? video,
        ),
      );
    }, 3000);
    return () => window.clearInterval(poll);
  }, [videos]);

  async function loadInitial() {
    setLoading(true);
    setError(null);
    try {
      const projectList = await api.listProjects();
      setProjects(projectList);
      setProjectId(projectList[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load projects");
    } finally {
      setLoading(false);
    }
  }

  async function loadProject(id: string) {
    setError(null);
    setNotice(null);
    try {
      const [boardList, assetList, sceneList, videoList] = await Promise.all([
        api.listStoryboards(id),
        api.listAssets(id, "product_scenes"),
        api.listProductScenes(id),
        api.listVideos(id),
      ]);
      setStoryboards(boardList);
      setAssets(assetList);
      setScenes(sceneList.filter((scene) => scene.mode === "film_scene"));
      setVideos(videoList);
      setSelectedId((current) =>
        boardList.some((board) => board.id === current)
          ? current
          : boardList[0]?.id ?? "",
      );
    } catch (err) {
      setStoryboards([]);
      setAssets([]);
      setScenes([]);
      setVideos([]);
      setError(err instanceof Error ? err.message : "Could not load storyboard data");
    }
  }

  async function saveStoryboard(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId || !title.trim()) return;
    setSavingBoard(true);
    setError(null);
    setNotice(null);
    try {
      const board = await api.createStoryboard(projectId, {
        title: title.trim(),
        description: description.trim() || null,
        status,
      });
      setStoryboards((current) => [board, ...current]);
      setSelectedId(board.id);
      setTitle("");
      setDescription("");
      setStatus("draft");
      setNotice("Storyboard created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save storyboard");
    } finally {
      setSavingBoard(false);
    }
  }

  async function deleteStoryboard(board: Storyboard) {
    if (!window.confirm(`Delete the storyboard "${board.title}" and all of its shots? This cannot be undone.`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.deleteStoryboard(projectId, board.id);
      setStoryboards((current) => current.filter((item) => item.id !== board.id));
      setSelectedId((current) =>
        current === board.id
          ? storyboards.find((item) => item.id !== board.id)?.id ?? ""
          : current,
      );
      setNotice("Storyboard deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete storyboard");
    }
  }

  function composedPrompt() {
    return [
      generationPrompt.trim(),
      continuityNotes.trim(),
      cameraNotes.trim() ? `Camera: ${cameraNotes.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  }

  async function addShot(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId || (!shotDescription.trim() && !generationPrompt.trim())) return;
    setSavingShot(true);
    setError(null);
    setNotice(null);
    try {
      const shot = await api.createShot(selectedId, {
        shot_number: orderedShots.length + 1,
        description: shotDescription.trim() || null,
        camera_notes: cameraNotes.trim() || null,
        generation_prompt: composedPrompt() || null,
        duration_seconds: duration,
      });
      setShots((current) => [...current, shot]);
      setShotDescription("");
      setCameraNotes("");
      setGenerationPrompt("");
      setDuration(5);
      setNotice("Shot added to sequence.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add shot");
    } finally {
      setSavingShot(false);
    }
  }

  async function moveShot(shot: Shot, direction: -1 | 1) {
    const index = orderedShots.findIndex((item) => item.id === shot.id);
    const swap = orderedShots[index + direction];
    if (!selectedId || !swap) return;
    const [updatedShot, updatedSwap] = await Promise.all([
      api.updateShot(selectedId, shot.id, { shot_number: swap.shot_number }),
      api.updateShot(selectedId, swap.id, { shot_number: shot.shot_number }),
    ]);
    setShots((current) =>
      current.map((item) => {
        if (item.id === updatedShot.id) return updatedShot;
        if (item.id === updatedSwap.id) return updatedSwap;
        return item;
      }),
    );
  }

  async function deleteShot(shot: Shot) {
    if (!selectedId) return;
    if (!window.confirm(`Delete shot ${shot.shot_number}? This cannot be undone.`)) return;
    setError(null);
    try {
      await api.deleteShot(selectedId, shot.id);
      setShots((current) => current.filter((item) => item.id !== shot.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the shot.");
    }
  }

  function shotPrompt(shot: Shot) {
    return [
      shot.generation_prompt || shot.description || "Cinematic storyboard shot",
      "cinematic keyframe, fashion film still, professional production design",
      "preserve character continuity, wardrobe details, face, body proportions, and product styling",
    ].join(", ");
  }

  async function generateShotKeyframe(shot: Shot) {
    if (!projectId || !assetId || generatingShotId) return;
    setGeneratingShotId(shot.id);
    setError(null);
    setNotice(null);
    try {
      const scene = await api.createProductScene({
        project_id: projectId,
        asset_id: assetId,
        prompt: shotPrompt(shot),
        preset: "studio",
        mode: "film_scene",
      });
      const updatedShot = await api.updateShot(selectedId, shot.id, {
        product_scene_id: scene.id,
      });
      setScenes((current) => [scene, ...current]);
      setShots((current) =>
        current.map((item) => (item.id === updatedShot.id ? updatedShot : item)),
      );
      setShotSceneIds((current) => ({ ...current, [shot.id]: scene.id }));
      setNotice(`Shot ${shot.shot_number} keyframe queued.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate keyframe");
    } finally {
      setGeneratingShotId("");
    }
  }

  async function animateShot(shot: Shot, scene: ProductSceneGeneration) {
    if (!projectId || scene.status !== "completed" || animatingShotId) return;
    setAnimatingShotId(shot.id);
    setError(null);
    setNotice(null);
    try {
      const video = await api.createVideo({
        project_id: projectId,
        product_scene_id: scene.id,
        prompt: [
          scene.prompt,
          `${motionPreset.replaceAll("_", " ")} camera movement`,
          "preserve the same person, styling, clothing colors, and product details across the storyboard sequence",
          "no duplicated subject, no warped anatomy",
        ].join(", "),
        motion_preset: motionPreset,
        duration_seconds: Math.min(Math.max(shot.duration_seconds, 2), 30),
        mode: "image_to_video",
      });
      const updatedShot = await api.updateShot(selectedId, shot.id, {
        video_id: video.id,
      });
      setVideos((current) => [video, ...current]);
      setShots((current) =>
        current.map((item) => (item.id === updatedShot.id ? updatedShot : item)),
      );
      setShotVideoIds((current) => ({ ...current, [shot.id]: video.id }));
      setNotice(`Shot ${shot.shot_number} video queued.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not animate shot");
    } finally {
      setAnimatingShotId("");
    }
  }

  async function copySummary() {
    const text = [
      selected?.title ?? "Storyboard",
      selected?.description ?? "",
      "",
      ...orderedShots.map(
        (shot) =>
          `${shot.shot_number}. ${shot.description || "Untitled shot"} (${shot.duration_seconds}s)\n${shot.camera_notes || ""}\n${shot.generation_prompt || ""}`,
      ),
    ].join("\n");
    await navigator.clipboard.writeText(text);
    setNotice("Storyboard summary copied.");
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card>
          <CardContent className="space-y-5 p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold">Project boards</h2>
              <Button type="button" variant="outline" size="sm" onClick={() => projectId && loadProject(projectId)}>
                <RefreshCw className="h-4 w-4" /> Refresh
              </Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="storyboard-project">Project</Label>
              <select
                id="storyboard-project"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                className={selectClass}
              >
                {projects.length === 0 ? <option value="">No projects</option> : null}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>

            <form onSubmit={saveStoryboard} className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="storyboard-title">New storyboard</Label>
                <Input
                  id="storyboard-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Luxury launch sequence"
                />
              </div>
              <Textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Campaign arc, character continuity, and visual objective"
                className="min-h-[84px]"
              />
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className={selectClass}
              >
                <option value="draft">Draft</option>
                <option value="planning">Planning</option>
                <option value="approved">Approved</option>
              </select>
              <Button type="submit" disabled={!projectId || !title.trim() || savingBoard} className="w-full">
                {savingBoard ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Create storyboard
              </Button>
            </form>

            <div className="space-y-2">
              {storyboards.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                  No storyboards yet.
                </p>
              ) : (
                storyboards.map((board) => (
                  <button
                    key={board.id}
                    type="button"
                    onClick={() => setSelectedId(board.id)}
                    className={cn(
                      "w-full rounded-md border p-3 text-left transition-colors",
                      selectedId === board.id ? "border-primary bg-primary/10" : "border-border hover:bg-muted",
                    )}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium">{board.title}</span>
                      <Badge variant="outline">{board.status}</Badge>
                    </span>
                    <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">
                      {board.description || "No description"}
                    </span>
                  </button>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardContent className="space-y-5 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold">
                    {selected?.title ?? "Select a storyboard"}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {orderedShots.length} shots - {totalDuration}s planned - {completedVideos.length} completed videos available
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selected ? (
                    <>
                      <Button type="button" variant="outline" onClick={copySummary}>
                        <Clipboard className="h-4 w-4" /> Copy summary
                      </Button>
                      <a
                        href={api.exportStoryboardUrl(projectId, selected.id)}
                        className={cn(buttonVariants({ variant: "outline" }))}
                      >
                        <Download className="h-4 w-4" /> Export
                      </a>
                      <Button type="button" variant="destructive" onClick={() => deleteStoryboard(selected)}>
                        <Trash2 className="h-4 w-4" /> Delete
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>

              {error ? (
                <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
              ) : null}
              {notice ? (
                <p className="rounded-md bg-emerald-500/15 px-3 py-2 text-sm text-emerald-300">{notice}</p>
              ) : null}

              <div className="grid gap-3 rounded-md border border-border bg-background/40 p-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="storyboard-asset">Film source asset</Label>
                  <select
                    id="storyboard-asset"
                    value={assetId}
                    onChange={(event) => setAssetId(event.target.value)}
                    className={selectClass}
                  >
                    {readyAssets.length === 0 ? <option value="">No ready assets</option> : null}
                    {readyAssets.map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.filename}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="storyboard-motion">Shot motion preset</Label>
                  <select
                    id="storyboard-motion"
                    value={motionPreset}
                    onChange={(event) => setMotionPreset(event.target.value as VideoMotionPreset)}
                    className={selectClass}
                  >
                    {MOTION_PRESETS.map((preset) => (
                      <option key={preset.value} value={preset.value}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <form onSubmit={addShot} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
                <div className="space-y-3">
                  <Textarea
                    value={shotDescription}
                    onChange={(event) => setShotDescription(event.target.value)}
                    placeholder="Shot description, e.g. model exits a black car outside a Milan boutique"
                    className="min-h-[86px]"
                  />
                  <Textarea
                    value={generationPrompt}
                    onChange={(event) => setGenerationPrompt(event.target.value)}
                    placeholder="Generation prompt for Film Studio or Videos"
                    className="min-h-[86px]"
                  />
                  <Textarea
                    value={continuityNotes}
                    onChange={(event) => setContinuityNotes(event.target.value)}
                    placeholder="Character continuity notes"
                    className="min-h-[70px]"
                  />
                </div>
                <div className="space-y-3">
                  <Input
                    value={cameraNotes}
                    onChange={(event) => setCameraNotes(event.target.value)}
                    placeholder="Camera notes"
                  />
                  <div className="space-y-2">
                    <Label htmlFor="shot-duration">Duration seconds</Label>
                    <Input
                      id="shot-duration"
                      type="number"
                      min={2}
                      max={30}
                      value={duration}
                      onChange={(event) => setDuration(Number(event.target.value))}
                    />
                  </div>
                  <Button
                    type="submit"
                    disabled={!selectedId || savingShot || (!shotDescription.trim() && !generationPrompt.trim())}
                    className="w-full"
                  >
                    {savingShot ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    Add shot
                  </Button>
                  <Link href="/film-studio" className={cn(buttonVariants({ variant: "outline" }), "w-full")}>
                    <Film className="h-4 w-4" /> Open Film Studio
                  </Link>
                </div>
              </form>
            </CardContent>
          </Card>

          <div className="grid gap-4">
            {orderedShots.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-5 text-sm text-muted-foreground">
                Add shots to build the sequence.
              </p>
            ) : (
              orderedShots.map((shot, index) => (
                <StoryboardShotCard
                  key={shot.id}
                  shot={shot}
                  index={index}
                  total={orderedShots.length}
                  scene={scenes.find((scene) => scene.id === shotSceneIds[shot.id]) ?? null}
                  video={videos.find((video) => video.id === shotVideoIds[shot.id]) ?? null}
                  canGenerate={Boolean(assetId)}
                  generating={generatingShotId === shot.id}
                  animating={animatingShotId === shot.id}
                  onGenerate={() => generateShotKeyframe(shot)}
                  onAnimate={(scene) => animateShot(shot, scene)}
                  onMoveUp={() => moveShot(shot, -1)}
                  onMoveDown={() => moveShot(shot, 1)}
                  onDelete={() => deleteShot(shot)}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StoryboardShotCard({
  animating,
  canGenerate,
  generating,
  index,
  onAnimate,
  onDelete,
  onGenerate,
  onMoveDown,
  onMoveUp,
  scene,
  shot,
  total,
  video,
}: {
  animating: boolean;
  canGenerate: boolean;
  generating: boolean;
  index: number;
  onAnimate: (scene: ProductSceneGeneration) => void;
  onDelete: () => void;
  onGenerate: () => void;
  onMoveDown: () => void;
  onMoveUp: () => void;
  scene: ProductSceneGeneration | null;
  shot: Shot;
  total: number;
  video: VideoGeneration | null;
}) {
  const sceneUrl = assetUrl(scene?.result_url ?? null);
  const videoUrl = assetUrl(video?.result_url ?? null);

  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="grid gap-4 md:grid-cols-[120px_minmax(0,1fr)_170px]">
          <div className="space-y-2">
            <Badge variant="muted">Shot {shot.shot_number}</Badge>
            <p className="text-sm text-muted-foreground">{shot.duration_seconds}s</p>
          </div>
          <div className="space-y-2">
            <h3 className="font-medium">{shot.description || "Untitled shot"}</h3>
            <p className="text-sm text-muted-foreground">{shot.camera_notes || "No camera notes"}</p>
            <p className="whitespace-pre-line rounded-md bg-background/50 p-3 text-sm">
              {shot.generation_prompt || "No generation prompt"}
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-2 md:justify-end">
            <Button type="button" variant="outline" size="icon" disabled={index === 0} onClick={onMoveUp}>
              <ArrowUp className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="icon" disabled={index === total - 1} onClick={onMoveDown}>
              <ArrowDown className="h-4 w-4" />
            </Button>
            <Button type="button" variant="destructive" size="icon" onClick={onDelete}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <div className="overflow-hidden rounded-md border border-border bg-background/40">
            <div className="relative aspect-video">
              {sceneUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={sceneUrl} alt={shot.description ?? "Storyboard shot"} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                  <ImageIcon className="h-6 w-6" />
                  No keyframe yet
                </div>
              )}
              {scene ? (
                <Badge variant={SCENE_STATUS_VARIANT[scene.status]} className="absolute right-2 top-2 capitalize">
                  {scene.status}
                </Badge>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2 p-3">
              <Button type="button" size="sm" onClick={onGenerate} disabled={!canGenerate || generating}>
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Generate keyframe
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => scene && onAnimate(scene)}
                disabled={!scene || scene.status !== "completed" || animating}
              >
                {animating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Animate
              </Button>
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-border bg-background/40">
            <div className="relative aspect-video">
              {videoUrl ? (
                <video src={videoUrl} controls className="h-full w-full object-contain" />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Video className="h-6 w-6" />
                  No clip yet
                </div>
              )}
              {video ? (
                <Badge variant={VIDEO_STATUS_VARIANT[video.status]} className="absolute right-2 top-2 capitalize">
                  {video.status}
                </Badge>
              ) : null}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
