"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Clapperboard, Film, ImageIcon, Loader2, Wand2 } from "lucide-react";

import { api } from "@/lib/api";
import type {
  Generation,
  ImageGenerationMode,
  ImageModeOption,
  ImagePresets,
  ImageProvider,
  MediaType,
  Project,
} from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { GenerationCard } from "@/components/generation-card";
import { MediaActions } from "@/components/media/MediaActions";
import { NextStepCard } from "@/components/media/NextStepCard";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { consumeHandoff } from "@/lib/stores/useMediaHandoff";
import { generationToMedia } from "@/lib/utils/mediaMapping";
import { validateSourceUrl } from "@/lib/utils/validateSourceUrl";
import { cn } from "@/lib/utils";

const MEDIA_OPTIONS: { value: MediaType; label: string; icon: typeof ImageIcon }[] =
  [
    { value: "image", label: "Image", icon: ImageIcon },
    { value: "video", label: "Video", icon: Clapperboard },
  ];

const ACTIVE_STATUSES = new Set(["queued", "running", "pending"]);

const IMAGE_PROVIDERS: { id: ImageProvider; label: string; badge: string }[] = [
  { id: "local_comfyui", label: "Local ComfyUI / Flux", badge: "Default local" },
  { id: "openai_image_api", label: "OpenAI Image API", badge: "Premium" },
];

// Display order for the Model/Preset selector; flux1_krea is the recommended default.
const PRESET_DISPLAY_ORDER = [
  "flux1_krea",
  "krea2_turbo_fp8",
  "z_image_turbo",
  "flux2_klein",
  "flux1_dev",
  "sdxl",
  "illustrious_xl",
  "netayume_anime",
  "local_fast",
] as const;

export function PromptForm() {
  const [prompt, setPrompt] = useState("");
  const [mediaType, setMediaType] = useState<MediaType>("image");
  const [provider, setProvider] = useState<ImageProvider>("local_comfyui");
  const [imageMode, setImageMode] = useState<ImageGenerationMode>("text_to_image");
  const [sourceImageUrl, setSourceImageUrl] = useState("");
  const [imageModes, setImageModes] = useState<ImageModeOption[]>([]);
  const [presets, setPresets] = useState<ImagePresets | null>(null);
  const [qualityPreset, setQualityPreset] = useState<string>("flux1_krea");
  const [projectId, setProjectId] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [uploadingSource, setUploadingSource] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Generation | null>(null);
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Image Studio");

  // Consume an "Edit This Image" handoff (or ?mode=image_edit&source=/storage/...):
  // auto-attach the source image and switch to Image Edit mode. Query-param
  // fallback re-validates the source before applying.
  useEffect(() => {
    const pending = consumeHandoff();
    let src: string | null = null;
    let mode: string | null = null;
    if (pending && (pending.targetRoute === "/create" || pending.targetMode === "image_edit")) {
      src = pending.sourceUrl;
      mode = pending.targetMode;
    } else if (typeof window !== "undefined") {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get("source")) {
        src = sp.get("source");
        mode = sp.get("mode");
      }
    }
    if (mode === "image_edit") setImageMode("image_edit");
    if (src && validateSourceUrl(src, ["image"]).ok) setSourceImageUrl(src);
  }, []);

  const activeGeneration = useMemo(
    () => result !== null && ACTIVE_STATUSES.has(result.status),
    [result],
  );

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
    api.listGenerationModes().then(setImageModes).catch(() => setImageModes([]));
    api
      .listImagePresets()
      .then((p) => {
        setPresets(p);
        // Keep flux1_krea if it is ready (the recommended default).
        // Otherwise fall to the first ready non-fallback preset.
        const kreaReady = p.quality_presets.some((qp) => qp.id === "flux1_krea" && qp.ready);
        if (!kreaReady) {
          const firstReady = p.quality_presets.find((qp) => qp.id !== "local_fast" && qp.ready);
          if (firstReady) setQualityPreset(firstReady.id);
        }
      })
      .catch(() => setPresets(null));
  }, []);

  useEffect(() => {
    if (!result || !ACTIVE_STATUSES.has(result.status)) return;

    const poll = window.setInterval(async () => {
      try {
        const next = await api.getGeneration(result.id);
        setResult(next);
        if (next.status === "failed") {
          setError(next.error || "Generation failed");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not refresh status");
      }
    }, 2500);

    return () => window.clearInterval(poll);
  }, [result]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Video is handled by the dedicated Video Studio (/videos), not the old
    // general Create generator (whose ComfyUI adapter is image-only).
    if (mediaType === "video") return;
    if (!prompt.trim() || submitting || activeGeneration) return;
    setSubmitting(true);
    setError(null);
    try {
      const generation = await api.createGeneration({
        prompt: prompt.trim(),
        media_type: mediaType,
        project_id: projectId || null,
        provider,
        mode: imageMode,
        source_image_url: imageMode === "image_edit" ? sourceImageUrl.trim() : null,
        quality_preset: provider === "local_comfyui" ? qualityPreset : null,
      });
      setResult(generation);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSourceUpload(file: File | null) {
    if (!file) return;
    setUploadingSource(true);
    setError(null);
    try {
      if (projectId) {
        const asset = await api.uploadAsset(projectId, file);
        setSourceImageUrl(asset.processed_url || asset.original_url);
      } else {
        const source = await api.uploadGenerationSource(file);
        setSourceImageUrl(source.source_image_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Source image upload failed");
    } finally {
      setUploadingSource(false);
    }
  }

  const busy = submitting || activeGeneration;
  const selectedPresetInfo = presets?.quality_presets.find((p) => p.id === qualityPreset) ?? null;
  const selectedMode = imageModes.find((mode) => mode.id === imageMode);
  const selectedProviderReadiness = selectedMode?.providers?.[provider];
  const selectedProviderReady = selectedProviderReadiness?.available ?? provider === "local_comfyui";
  const selectedCost = selectedProviderReadiness?.cost ?? (provider === "openai_image_api" ? 15 : 5);
  const providerBlockReason = !selectedProviderReady
    ? selectedProviderReadiness?.note ?? "Provider is not available for this mode."
    : null;
  const busyLabel =
    result?.status === "running"
      ? "Rendering..."
      : result?.status === "queued" || result?.status === "pending"
        ? "Queued..."
        : "Submitting...";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <form
        onSubmit={handleSubmit}
        className="space-y-5 rounded-lg border border-border bg-card p-6"
      >
        <div className="space-y-2">
          <Label htmlFor="prompt">Prompt</Label>
          <Textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe what you want to create, e.g. a luxury perfume bottle on wet marble, cinematic lighting"
            className="min-h-[140px]"
          />
        </div>

        <div className="space-y-2">
          <Label>Output type</Label>
          <div className="flex gap-2">
            {MEDIA_OPTIONS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => setMediaType(value)}
                disabled={busy}
                className={cn(
                  "flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                  mediaType === value
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        </div>

        {mediaType === "video" ? (
          <div className="space-y-3 rounded-md border border-border bg-muted/40 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Film className="h-4 w-4 text-primary" />
              Video generation lives in Video Studio
            </div>
            <p className="text-sm text-muted-foreground">
              Video generation is available in Video Studio. Go to /videos to use
              Text → Video, Image → Video, Video → Video, Upscale, or Extension.
            </p>
            <Link href="/videos" className={cn(buttonVariants(), "gap-2")}>
              Open Video Studio <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        ) : null}

        {mediaType === "image" ? (
          <>
            <div className="space-y-2">
              <Label>Image provider</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {IMAGE_PROVIDERS.map((item) => {
                  const readiness =
                    selectedMode?.providers?.[item.id] ??
                    ({ available: item.id === "local_comfyui", cost: item.id === "openai_image_api" ? 15 : 5, note: null });
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => readiness.available && setProvider(item.id)}
                      disabled={busy || !readiness.available}
                      className={cn(
                        "rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                        provider === item.id
                          ? "border-primary bg-primary/15 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      <span className="flex items-center justify-between gap-2 text-sm font-medium">
                        {item.label}
                        <Badge variant={item.id === "openai_image_api" ? "default" : "outline"}>
                          {item.badge}
                        </Badge>
                      </span>
                      <span className="mt-1 block text-xs">Cost: {readiness.cost} credits</span>
                      {!readiness.available && readiness.note ? (
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {readiness.note}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>

            {provider === "local_comfyui" ? (
              <div className="space-y-2">
                <Label htmlFor="quality-preset">Model / Preset</Label>
                <select
                  id="quality-preset"
                  value={qualityPreset}
                  onChange={(e) => setQualityPreset(e.target.value)}
                  disabled={busy || !presets}
                  className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {presets
                    ? PRESET_DISPLAY_ORDER.flatMap((id) => {
                        const p = presets.quality_presets.find((qp) => qp.id === id);
                        return p ? [p] : [];
                      }).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                          {p.id === "flux1_krea" ? " — Recommended" : ""}
                          {!p.ready ? " (Setup required)" : ""}
                        </option>
                      ))
                    : <option value="flux1_krea">FLUX.1 Krea Dev — Loading…</option>
                  }
                </select>
                {selectedPresetInfo ? (
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <p>
                      Model:{" "}
                      <span className="font-medium text-foreground">{selectedPresetInfo.label}</span>
                      <Badge
                        variant={selectedPresetInfo.ready ? "outline" : "muted"}
                        className="ml-2"
                      >
                        {selectedPresetInfo.ready ? "Ready" : "Setup required"}
                      </Badge>
                    </p>
                    {!selectedPresetInfo.ready ? (
                      <p className="text-amber-700 dark:text-amber-300">{selectedPresetInfo.detail}</p>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Loading model info…</p>
                )}
                {presets?.face_refine ? (
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      disabled
                      title={presets.face_refine.detail}
                      className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground opacity-60"
                    >
                      <Wand2 className="h-3.5 w-3.5" />
                      {presets.face_refine.available ? "Refine face / detail" : "Face / Subject Refine — coming soon"}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="space-y-2">
              <Label>Image mode</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {(imageModes.length
                  ? imageModes
                  : [
                      {
                        id: "text_to_image" as ImageGenerationMode,
                        name: "Text -> Image",
                        description: "Create artwork from a text prompt.",
                        source_required: false,
                        providers: {
                          local_comfyui: { available: true, cost: 5, note: null },
                          openai_image_api: {
                            available: false,
                            cost: 15,
                            note: "OpenAI provider is not configured. Admin setup required.",
                          },
                        },
                      },
                    ]).map((mode) => {
                  const readiness = mode.providers?.[provider];
                  const available = readiness?.available ?? false;
                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => available && setImageMode(mode.id)}
                      disabled={busy || !available}
                      className={cn(
                        "rounded-md border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                        imageMode === mode.id
                          ? "border-primary bg-primary/15 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      <span className="flex items-center justify-between gap-2 text-sm font-medium">
                        {mode.name}
                        <Badge variant={available ? "outline" : "muted"}>
                          {available ? "Ready" : "Unavailable"}
                        </Badge>
                      </span>
                      <span className="mt-1 block text-xs">{mode.description}</span>
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

            {imageMode === "image_edit" ? (
              <div className="space-y-2">
                <Label htmlFor="source-image-file">Upload or select an image to edit</Label>
                <Input
                  id="source-image-file"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  disabled={busy || uploadingSource}
                  onChange={(event) => {
                    void handleSourceUpload(event.target.files?.[0] ?? null);
                    event.currentTarget.value = "";
                  }}
                />
                {!projectId ? (
                  <p className="text-xs text-muted-foreground">
                    Uploading without a project stores a private Image Edit source. Select a project if you want the source associated with that project as a product asset.
                  </p>
                ) : null}
                <Label htmlFor="source-image-url">Source image storage URL</Label>
                <Input
                  id="source-image-url"
                  value={sourceImageUrl}
                  onChange={(event) => setSourceImageUrl(event.target.value)}
                  placeholder="/storage/generated/example.png or /storage/product-scenes/example.png"
                  disabled={busy || uploadingSource}
                />
                <p className="text-xs text-muted-foreground">
                  Local Qwen Image Edit uses this stored image as the edit/reference input.
                  {uploadingSource ? " Uploading source image..." : null}
                </p>
              </div>
            ) : null}
          </>
        ) : null}

        <div className={cn("space-y-2", mediaType === "video" && "hidden")}>
          <Label htmlFor="project">Project (optional)</Label>
          <select
            id="project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={busy}
            className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
          >
            <option value="">No project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {providerBlockReason && mediaType === "image" ? (
          <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
            {providerBlockReason}
          </p>
        ) : null}

        {mediaType === "image" ? (
          <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            size="lg"
            disabled={
              busy ||
              !prompt.trim() ||
              !selectedProviderReady ||
              (imageMode === "image_edit" && !sourceImageUrl.trim())
            }
          >
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> {busyLabel}
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4" /> Generate
              </>
            )}
          </Button>
          <span className="text-sm text-muted-foreground">Cost: {selectedCost} credits</span>
          </div>
        ) : null}
      </form>

      <div className="space-y-4">
        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold">Latest result</h3>
          {result ? (
            <GenerationCard generation={result} />
          ) : (
            <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border text-center text-sm text-muted-foreground">
              <Wand2 className="h-6 w-6" />
              Your generated result will appear here.
            </div>
          )}
          {result && result.status === "completed" && result.media_type === "image" ? (
            <div className="mt-4 space-y-4">
              <div>
                <h4 className="mb-2 text-sm font-semibold">What do you want to do with this?</h4>
                <MediaActions media={generationToMedia(result)} onAction={onAction} />
              </div>
              {toast ? <p className="text-xs text-emerald-600 dark:text-emerald-400">{toast}</p> : null}
            </div>
          ) : null}
        </div>
        {result && result.status === "completed" && result.media_type === "image" ? (
          <NextStepCard media={generationToMedia(result)} onAction={onAction} />
        ) : null}
      </div>
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
    </div>
  );
}
