"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, ImageIcon, Loader2, Megaphone, Shield, Sparkles } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  ProductAsset,
  ProductSceneGeneration,
  ProductSceneMode,
  ProductScenePreset,
  Project,
} from "@/lib/types";
import { ActiveConfigBadge } from "@/components/active-config-badge";
import { Badge } from "@/components/ui/badge";
import { BriefSelect } from "@/components/brief-select";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { consumeHandoff } from "@/lib/stores/useMediaHandoff";
import { productSceneToMedia } from "@/lib/utils/mediaMapping";
import type { HandoffAction } from "@/lib/types/media";
import { cn } from "@/lib/utils";

const PRESETS: ProductScenePreset[] = ["studio", "luxury", "outdoor", "social ad"];

const MODES: { value: ProductSceneMode; label: string; hint: string }[] = [
  // Transform (default path) — Qwen Image Edit.
  { value: "creative_edit", label: "Creative Edit", hint: "Transform: freely change pose, camera angle, environment, clothing, hair, age, lighting, and style. Powered by Qwen Image Edit." },
  { value: "clothing_style_edit", label: "Clothing & Style", hint: "Transform: replace garments, change clothing color, restyle the outfit." },
  { value: "character_reimagination", label: "Character Reimagination", hint: "Transform: fantasy, sci-fi, cyberpunk, superhero, historical, or age-shifted variants while keeping core identity." },
  { value: "fashion_transformation", label: "Fashion Transformation", hint: "Transform: full outfit replacement, color changes, luxury styling, editorial wardrobe." },
  { value: "cinematic_scene_builder", label: "Cinematic Scene Builder", hint: "Transform: film-still compositions with dramatic camera angles, shot types, lighting, and story environments." },
  // Preserve (explicit) — Flux Kontext / composite.
  { value: "segmented_composite_polished", label: "Preserve Product", hint: "Preserve: keeps subject, clothing, pose, and product details mostly unchanged while replacing the background." },
  { value: "creative_fashion_edit", label: "Flux Creative (Preserve-leaning)", hint: "Preserve: Flux Kontext edit that keeps identity strongly; allows moderate pose and background changes." },
  { value: "inpaint", label: "Mask preserve", hint: "Preserve: keeps the masked product, regenerates only the background." },
  { value: "ipadapter", label: "IPAdapter", hint: "Preserve: conditions on the product image for closer identity." },
  { value: "segmented_composite", label: "Segmented composite", hint: "Preserve: RemBG-segments the subject and rebuilds only the background." },
  { value: "fashion_editorial", label: "Fashion editorial", hint: "Preserve: high-end magazine/editorial styling; preserves subject." },
  { value: "advertising_scene", label: "Advertising scene", hint: "Preserve: polished product-ad imagery; looser pose preservation." },
  { value: "img2img", label: "Img2img", hint: "Preserve: fastest. Re-renders the scene around the product." },
  // Pose — SDXL + OpenPose → Qwen refine.
  { value: "pose_edit", label: "Pose Edit", hint: "Pose: SDXL + OpenPose generates the pose (walking, running, sitting, runway, action), then Qwen refines and restyles." },
  // Film — Qwen keyframe → Wan in Video Studio.
  { value: "film_scene", label: "Film Keyframe", hint: "Film: generate a cinematic keyframe with Qwen, then animate it in Video Studio with Wan 2.2." },
];

// Transform / Preserve / Pose / Film groupings for the mode picker.
const MODE_GROUPS: { title: string; blurb: string; modes: ProductSceneMode[] }[] = [
  {
    title: "Transform",
    blurb: "Default. Freely transform the image — pose, clothing, environment, style. Qwen Image Edit.",
    modes: [
      "creative_edit",
      "clothing_style_edit",
      "character_reimagination",
      "fashion_transformation",
      "cinematic_scene_builder",
    ],
  },
  {
    title: "Preserve",
    blurb: "Explicit. Keep subject / clothing / product / composition; change the background. Flux Kontext.",
    modes: [
      "segmented_composite_polished",
      "creative_fashion_edit",
      "inpaint",
      "ipadapter",
      "segmented_composite",
      "fashion_editorial",
      "advertising_scene",
      "img2img",
    ],
  },
  {
    title: "Pose",
    blurb: "Explicit body-position control. SDXL + OpenPose → Qwen refine.",
    modes: ["pose_edit"],
  },
  {
    title: "Film",
    blurb: "Cinematic keyframe for Video Studio. Qwen → Wan 2.2.",
    modes: ["film_scene"],
  },
];

const CREATIVE_EXAMPLES = [
  "Change pants to black tailored trousers while keeping shirt color similar.",
  "Place model walking through a Milan fashion boutique.",
  "Change pose to confident runway stance.",
  "Create Vogue-style editorial lighting and framing.",
  "Reimagine this person as a cyberpunk film protagonist.",
  "Create a wide cinematic shot in a rainy neon street.",
];
const TRANSFORMATION_MODES = new Set<ProductSceneMode>([
  "creative_edit",
  "clothing_style_edit",
  "character_reimagination",
  "fashion_transformation",
  "cinematic_scene_builder",
  "pose_edit",
  "film_scene",
]);

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);

export function ProductScenesView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [preset, setPreset] = useState<ProductScenePreset>("studio");
  // Transform Mode is the default Creative Edit path (policy: transform-first).
  const [mode, setMode] = useState<ProductSceneMode>("creative_edit");
  const [briefId, setBriefId] = useState("");
  const [maskFile, setMaskFile] = useState<File | null>(null);
  const [modeAvailability, setModeAvailability] = useState<
    Record<string, { available: boolean; note: string | null }>
  >({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<ProductSceneGeneration | null>(null);
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Product Scenes");
  const [handoffNote, setHandoffNote] = useState<string | null>(null);

  // A "Use in Product Scene" handoff carries an image. Product scenes are
  // project + asset based, so we surface a friendly note rather than silently
  // changing the working asset selector.
  useEffect(() => {
    const pending = consumeHandoff();
    if (pending?.sourceUrl && pending.sourceType === "image") {
      setHandoffNote(
        `Image carried over ${pending.originLabel ?? ""}. Upload it as a product asset (or pick an existing asset) to use it here.`,
      );
    }
  }, []);

  const readyAssets = useMemo(
    () =>
      assets.filter(
        (asset) =>
          asset.project_id === projectId && READY_ASSET_STATUSES.has(asset.status),
      ),
    [assets, projectId],
  );

  const activeScene = latest?.status === "queued" || latest?.status === "running";

  useEffect(() => {
    async function load() {
      try {
        const [projectList, assetList, sceneList] = await Promise.all([
          api.listProjects(),
          api.listAssets(undefined, "product_scenes"),
          api.listProductScenes(),
        ]);
        setProjects(projectList);
        setAssets(assetList);
        setScenes(sceneList);
        // Scene-mode availability (which creative modes are usable right now).
        api
          .getWorkflowManagerModels()
          .then((m) =>
            setModeAvailability(
              Object.fromEntries(
                m.scene_modes.map((sm) => [
                  sm.id,
                  { available: sm.available, note: sm.note },
                ]),
              ),
            ),
          )
          .catch(() => setModeAvailability({}));
        const initialProjectId =
          assetList.find((asset) => READY_ASSET_STATUSES.has(asset.status))
            ?.project_id ??
          projectList[0]?.id ??
          "";
        setProjectId(initialProjectId);
        setAssetId(
          assetList.find(
            (asset) =>
              asset.project_id === initialProjectId &&
              READY_ASSET_STATUSES.has(asset.status),
          )?.id ?? "",
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load product scenes");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    setAssetId((current) =>
      readyAssets.some((asset) => asset.id === current)
        ? current
        : readyAssets[0]?.id ?? "",
    );
  }, [readyAssets]);

  useEffect(() => {
    const active = scenes.filter(
      (scene) => scene.status === "queued" || scene.status === "running",
    );
    if (latest?.status === "queued" || latest?.status === "running") {
      active.push(latest);
    }
    const unique = Array.from(new Map(active.map((scene) => [scene.id, scene])).values());
    if (unique.length === 0) return;

    const poll = window.setInterval(async () => {
      const updates = await Promise.all(
        unique.map((scene) => api.getProductScene(scene.id)),
      );
      setScenes((current) =>
        current.map((scene) => updates.find((item) => item.id === scene.id) ?? scene),
      );
      setLatest((current) =>
        current ? updates.find((item) => item.id === current.id) ?? current : current,
      );
    }, 2500);

    return () => window.clearInterval(poll);
  }, [latest, scenes]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !assetId || !prompt.trim() || submitting || activeScene) return;
    setSubmitting(true);
    setError(null);
    try {
      // For inpaint, attach the mask to the asset before queueing the scene.
      if (mode === "inpaint" && maskFile) {
        const updated = await api.uploadAssetMask(assetId, maskFile);
        setAssets((current) =>
          current.map((asset) => (asset.id === updated.id ? updated : asset)),
        );
      }
      const scene = await api.createProductScene({
        project_id: projectId,
        asset_id: assetId,
        prompt: prompt.trim(),
        preset,
        mode,
        brief_id: briefId || null,
      });
      setLatest(scene);
      setScenes((current) => [scene, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scene generation failed");
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

  const selectedAsset = assets.find((asset) => asset.id === assetId);
  const selectedAssetUrl = assetUrl(
    selectedAsset?.processed_url ?? selectedAsset?.original_url ?? null,
  );

  return (
    <div className="space-y-6">
      <ActiveConfigBadge fields={["image_model", "scene_mode"]} />
      {handoffNote ? (
        <p className="flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
          {handoffNote}
        </p>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-lg border border-border bg-card p-6"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="scene-project">Project</Label>
              <select
                id="scene-project"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="scene-asset">Product asset</Label>
              <select
                id="scene-asset"
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {readyAssets.length === 0 ? (
                  <option value="">No ready assets</option>
                ) : null}
                {readyAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.filename}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Preset</Label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {PRESETS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setPreset(item)}
                  className={cn(
                    "rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors",
                    preset === item
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <Label>Scene edit mode</Label>
            <div className="rounded-md border border-border bg-background/40 p-3 text-sm text-muted-foreground">
              <p>
                <span className="font-medium text-foreground">Transform</span>{" "}
                (default) freely changes pose, clothing, environment, and style.
              </p>
              <p>
                <span className="font-medium text-foreground">Preserve</span>{" "}
                keeps subject and clothing intact — select it explicitly.
              </p>
            </div>
            {MODE_GROUPS.map((group) => (
              <div key={group.title} className="space-y-1.5">
                <div className="flex items-baseline gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-foreground">
                    {group.title}
                  </span>
                  <span className="text-[11px] text-muted-foreground">{group.blurb}</span>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {group.modes.map((value) => {
                    const item = MODES.find((m) => m.value === value);
                    if (!item) return null;
                    // Default available until availability loads.
                    const avail = modeAvailability[value]?.available ?? true;
                    const disabled = !avail && mode !== value;
                    return (
                      <button
                        key={value}
                        type="button"
                        disabled={disabled}
                        title={
                          disabled
                            ? modeAvailability[value]?.note ?? "Unavailable"
                            : undefined
                        }
                        onClick={() => setMode(value)}
                        className={cn(
                          "rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors",
                          mode === value
                            ? "border-primary bg-primary/15 text-primary"
                            : disabled
                              ? "border-border text-muted-foreground opacity-50"
                              : "border-border text-muted-foreground hover:bg-muted",
                        )}
                      >
                        {item.label}
                        {!avail ? " ·" : ""}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              {MODES.find((item) => item.value === mode)?.hint}
            </p>
            {TRANSFORMATION_MODES.has(mode) ? (
              <div className="rounded-md border border-primary/20 bg-primary/10 p-3">
                <p className="mb-2 text-xs font-medium text-primary">
                  Creative transformation prompt examples
                </p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {CREATIVE_EXAMPLES.map((example) => (
                    <li key={example}>{example}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {modeAvailability[mode] && !modeAvailability[mode].available ? (
              <p className="text-xs text-destructive">
                {modeAvailability[mode].note ??
                  "This mode is currently unavailable; generation may fail."}
              </p>
            ) : null}
          </div>

          {mode === "inpaint" ? (
            <div className="space-y-2 rounded-md border border-border bg-background/40 p-3">
              <Label htmlFor="scene-mask" className="flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-primary" /> Product mask (optional)
              </Label>
              <input
                id="scene-mask"
                type="file"
                accept="image/*"
                onChange={(e) => setMaskFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-1.5 file:text-primary"
              />
              <p className="text-xs text-muted-foreground">
                White = product. Without a mask, this falls back to the configured
                mode (img2img by default).
              </p>
            </div>
          ) : null}

          <BriefSelect
            projectId={projectId}
            value={briefId}
            onChange={setBriefId}
            id="scene-brief"
          />

          <div className="space-y-2">
            <Label htmlFor="scene-prompt">Scene prompt</Label>
            <Textarea
              id="scene-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the ad scene, e.g. product on polished stone with dramatic side light"
              className="min-h-[130px]"
            />
          </div>

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button
            type="submit"
            size="lg"
            disabled={!projectId || !assetId || !prompt.trim() || submitting || activeScene}
          >
            {submitting || activeScene ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {latest?.status === "running" ? "Rendering..." : "Queued..."}
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" /> Generate ad scene
              </>
            )}
          </Button>
        </form>

        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold">Selected product</h3>
          <div className="aspect-square overflow-hidden rounded-md border border-border bg-background/60">
            {selectedAssetUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={selectedAssetUrl}
                alt={selectedAsset?.filename ?? ""}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <ImageIcon className="h-7 w-7" />
                Upload a ready product asset first.
              </div>
            )}
          </div>
          {latest ? (
            <div className="mt-4">
              <SceneCard scene={latest} featured onAction={onAction} />
            </div>
          ) : null}
        </div>
      </div>

      <div>
        <h3 className="mb-4 text-sm font-semibold">Scene history</h3>
        {scenes.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <Megaphone className="h-7 w-7" />
            No product scenes yet.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {scenes.map((scene) => (
              <SceneCard key={scene.id} scene={scene} onAction={onAction} />
            ))}
          </div>
        )}
      </div>
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function SceneCard({
  scene,
  featured = false,
  onAction,
}: {
  scene: ProductSceneGeneration;
  featured?: boolean;
  onAction: (action: HandoffAction) => void;
}) {
  const src = assetUrl(scene.result_url);
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="relative aspect-square bg-background/60">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={scene.prompt} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Megaphone className="h-7 w-7" />
            {scene.status}
          </div>
        )}
        <Badge
          variant={STATUS_VARIANT[scene.status]}
          className="absolute right-2 top-2 capitalize"
        >
          {scene.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="capitalize">{scene.preset}</span>
          {featured ? <span>Latest</span> : null}
        </div>
        {scene.mode ? (
          <Badge variant="outline" className="capitalize">
            {scene.mode.replaceAll("_", " ")}
          </Badge>
        ) : null}
        <p className="line-clamp-2 text-sm text-foreground/90">{scene.prompt}</p>
        {scene.status === "failed" && scene.error ? (
          <p className="line-clamp-2 text-xs text-destructive">{scene.error}</p>
        ) : null}
        {scene.status === "completed" ? (
          <a
            href={api.exportSceneUrl(scene.id)}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "w-full")}
          >
            <Download className="h-4 w-4" /> Download
          </a>
        ) : (
          <button
            type="button"
            disabled
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "w-full",
            )}
          >
            <Download className="h-4 w-4" /> Download
          </button>
        )}
        {scene.status === "completed" && scene.result_url ? (
          <div className="border-t border-border/60 pt-2">
            <MediaActions media={productSceneToMedia(scene)} onAction={onAction} compact />
          </div>
        ) : null}
      </div>
    </div>
  );
}
