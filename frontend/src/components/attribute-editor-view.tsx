"use client";

import { useEffect, useMemo, useState } from "react";
import { Archive, Download, Eye, ImageIcon, Loader2, Scissors, Shield } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { ProductAsset, ProductSceneGeneration, Project } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type MaskSource = "auto" | "manual" | "existing";
type Route = "human-parse" | "groundingdino-sam" | "manual-mask";

const CUSTOM = "__custom__";
const TARGETS: { label: string; value: string }[] = [
  { label: "Pants / Trousers", value: "pants" },
  { label: "Shirt", value: "shirt" },
  { label: "Jacket / Coat / Blazer", value: "jacket" },
  { label: "Shoes", value: "shoes" },
  { label: "Hair", value: "hair" },
  { label: "Face", value: "face" },
  { label: "Hat", value: "hat" },
  { label: "Dress", value: "dress" },
  { label: "Skirt", value: "skirt" },
  { label: "Glasses", value: "glasses" },
  { label: "Tie", value: "tie" },
  { label: "Accessories", value: "accessories" },
  { label: "Custom text target…", value: CUSTOM },
];

// Client mirror of the backend routing (see resolve_parse_class / resolve_seg).
const HUMAN_PARSE = new Set([
  "pants", "trousers", "shoes", "shoe", "footwear", "face", "makeup", "hair",
  "hairstyle", "haircut", "dress", "skirt", "hat", "jacket", "coat", "blazer",
  "outerwear", "upper garment", "upper-clothes",
]);
const AMBIGUOUS = new Set([
  "shirt", "dress shirt", "button-down", "button-down shirt", "button down shirt",
]);

function routeFor(target: string, maskSource: MaskSource): Route {
  if (maskSource !== "auto") return "manual-mask";
  const t = target.trim().toLowerCase();
  if (!t || AMBIGUOUS.has(t)) return "manual-mask";
  if (HUMAN_PARSE.has(t)) return "human-parse";
  return "groundingdino-sam";
}

function routeForScene(scene: ProductSceneGeneration): Route {
  if (!scene.target_attribute) return "manual-mask";
  return routeFor(scene.target_attribute, "auto");
}

const ROUTE_LABEL: Record<Route, string> = {
  "human-parse": "Human-parse",
  "groundingdino-sam": "GroundingDINO+SAM",
  "manual-mask": "Manual mask",
};

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const READY = new Set(["uploaded", "completed"]);
const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function AttributeEditorView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [targetValue, setTargetValue] = useState("pants");
  const [customTarget, setCustomTarget] = useState("");
  const [prompt, setPrompt] = useState("");
  const [maskSource, setMaskSource] = useState<MaskSource>("auto");
  const [maskFile, setMaskFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<ProductSceneGeneration | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewNote, setPreviewNote] = useState<string | null>(null);

  const readyAssets = useMemo(
    () => assets.filter((a) => a.project_id === projectId && READY.has(a.status)),
    [assets, projectId],
  );
  const selectedAsset = assets.find((a) => a.id === assetId);
  const effectiveTarget =
    targetValue === CUSTOM ? customTarget.trim() : targetValue;
  const route = routeFor(effectiveTarget, maskSource);
  const attributeScenes = useMemo(
    () => scenes.filter((s) => s.mode === "attribute_edit"),
    [scenes],
  );

  useEffect(() => {
    async function load() {
      try {
        const [projectList, assetList, sceneList] = await Promise.all([
          api.listProjects(),
          api.listAssets(),
          api.listProductScenes(),
        ]);
        setProjects(projectList);
        setAssets(assetList);
        setScenes(sceneList);
        const pid =
          assetList.find((a) => READY.has(a.status))?.project_id ??
          projectList[0]?.id ??
          "";
        setProjectId(pid);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    setAssetId((cur) =>
      readyAssets.some((a) => a.id === cur) ? cur : readyAssets[0]?.id ?? "",
    );
  }, [readyAssets]);

  useEffect(() => {
    const active = attributeScenes.filter(
      (s) => s.status === "queued" || s.status === "running",
    );
    if (latest && (latest.status === "queued" || latest.status === "running")) {
      active.push(latest);
    }
    const unique = Array.from(new Map(active.map((s) => [s.id, s])).values());
    if (unique.length === 0) return;
    const poll = window.setInterval(async () => {
      const updates = await Promise.all(unique.map((s) => api.getProductScene(s.id)));
      setScenes((cur) => cur.map((s) => updates.find((u) => u.id === s.id) ?? s));
      setLatest((cur) =>
        cur ? updates.find((u) => u.id === cur.id) ?? cur : cur,
      );
    }, 2500);
    return () => window.clearInterval(poll);
  }, [latest, attributeScenes]);

  const activeJob = latest?.status === "queued" || latest?.status === "running";

  // A changed target/asset/mask source invalidates a shown preview.
  useEffect(() => {
    setPreviewUrl(null);
    setPreviewNote(null);
  }, [assetId, targetValue, customTarget, maskSource]);

  async function handlePreview() {
    setPreviewNote(null);
    setError(null);
    if (!assetId) {
      setError("Select an asset first.");
      return;
    }
    if (maskSource === "manual") {
      if (!maskFile) {
        setError("Upload a mask to preview it.");
        return;
      }
      setPreviewUrl(URL.createObjectURL(maskFile));
      return;
    }
    if (maskSource === "existing") {
      if (!selectedAsset?.mask_url) {
        setError("This asset has no existing mask.");
        return;
      }
      setPreviewUrl(assetUrl(selectedAsset.mask_url));
      return;
    }
    if (!effectiveTarget) {
      setError("Pick a target attribute to preview.");
      return;
    }
    setPreviewing(true);
    try {
      const res = await api.previewMask({
        asset_id: assetId,
        target_attribute: effectiveTarget,
      });
      if (res.mask_url) {
        setPreviewUrl(assetUrl(res.mask_url));
      } else {
        setPreviewUrl(null);
        setPreviewNote(
          "This target needs a manual mask — switch Mask source to Manual.",
        );
      }
    } catch (err) {
      setPreviewUrl(null);
      setError(err instanceof Error ? err.message : "Mask preview failed");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !assetId || !prompt.trim() || submitting || activeJob) return;
    if (maskSource === "auto" && !effectiveTarget) {
      setError("Pick a target attribute (or switch to a manual mask).");
      return;
    }
    if (maskSource === "manual" && !maskFile) {
      setError("Manual mask mode needs a mask image. Upload one or pick Auto.");
      return;
    }
    if (maskSource === "existing" && !selectedAsset?.mask_url) {
      setError("This asset has no existing mask. Upload one or pick Auto.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (maskSource === "manual" && maskFile) {
        const updated = await api.uploadAssetMask(assetId, maskFile);
        setAssets((cur) => cur.map((a) => (a.id === updated.id ? updated : a)));
      }
      // Auto routes by target_attribute (human-parse / GroundingDINO). Manual and
      // existing-mask omit target_attribute to force the manual masked workflow.
      const scene = await api.createProductScene({
        project_id: projectId,
        asset_id: assetId,
        prompt: prompt.trim(),
        preset: "studio",
        mode: "attribute_edit",
        target_attribute: maskSource === "auto" ? effectiveTarget : null,
      });
      setLatest(scene);
      setScenes((cur) => [scene, ...cur]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attribute edit failed");
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

  const selectedUrl = assetUrl(
    selectedAsset?.processed_url ?? selectedAsset?.original_url ?? null,
  );
  const isShirt = effectiveTarget.trim().toLowerCase() === "shirt";
  const isHair = effectiveTarget.trim().toLowerCase() === "hair";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-lg border border-border bg-card p-6"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ae-project">Project</Label>
              <select
                id="ae-project"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className={selectClass}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ae-asset">Product asset</Label>
              <select
                id="ae-asset"
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                className={selectClass}
              >
                {readyAssets.length === 0 ? <option value="">No ready assets</option> : null}
                {readyAssets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.filename}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ae-target">Target attribute</Label>
              <select
                id="ae-target"
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value)}
                className={selectClass}
              >
                {TARGETS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              {targetValue === CUSTOM ? (
                <input
                  value={customTarget}
                  onChange={(e) => setCustomTarget(e.target.value)}
                  placeholder="e.g. necklace, watch, logo"
                  className={selectClass}
                />
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="ae-mask">Mask source</Label>
              <select
                id="ae-mask"
                value={maskSource}
                onChange={(e) => setMaskSource(e.target.value as MaskSource)}
                className={selectClass}
              >
                <option value="auto">Auto (human-parse / GroundingDINO)</option>
                <option value="manual">Manual mask upload</option>
                <option value="existing" disabled={!selectedAsset?.mask_url}>
                  Existing mask{selectedAsset?.mask_url ? "" : " (none)"}
                </option>
              </select>
              <p className="text-xs text-muted-foreground">
                Route: <span className="font-medium text-foreground">{ROUTE_LABEL[route]}</span>
              </p>
            </div>
          </div>

          {maskSource === "manual" ? (
            <div className="space-y-2 rounded-md border border-border bg-background/40 p-3">
              <Label htmlFor="ae-maskfile" className="flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-primary" /> Mask image (white = edit region)
              </Label>
              <input
                id="ae-maskfile"
                type="file"
                accept="image/*"
                onChange={(e) => setMaskFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-1.5 file:text-primary"
              />
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="ae-prompt">Edit prompt</Label>
            <Textarea
              id="ae-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Change only the tan pants to black tailored trousers. Keep the shirt, jacket, shoes, face, pose, and background unchanged."
              className="min-h-[110px]"
            />
          </div>

          <div className="space-y-1.5 rounded-md border border-border bg-background/40 p-3 text-xs text-muted-foreground">
            <p><span className="font-medium text-foreground">Human parsing</span> is used for standard body/clothing parts (pants, shoes, face, hair, dress, single upper garment).</p>
            <p><span className="font-medium text-foreground">GroundingDINO/SAM</span> handles open-vocabulary targets (tie, glasses, accessories, custom text).</p>
            <p><span className="font-medium text-foreground">Manual mask</span> is required for ambiguous overlapping garments and gives the most control.</p>
            <p>Shirt under a held or overlapping jacket may require a manual mask. Hair edits use face protection when possible.</p>
          </div>

          {isShirt ? (
            <p className="rounded-md bg-amber-500/15 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
              If the shirt overlaps with a jacket, automatic segmentation may not isolate it. Use a manual mask for best results.
            </p>
          ) : null}
          {isHair ? (
            <p className="rounded-md bg-primary/10 px-3 py-2 text-xs text-primary">
              Hair edits preserve the face by subtracting the face region from the mask. Dramatic hairstyle changes may need a larger manual mask.
            </p>
          ) : null}

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handlePreview}
              disabled={previewing || submitting || activeJob}
            >
              {previewing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
              Preview mask
            </Button>
            <Button
              type="submit"
              size="lg"
              disabled={
                !projectId || !assetId || !prompt.trim() || submitting || activeJob
              }
            >
              {submitting || activeJob ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {latest?.status === "running" ? "Editing…" : "Queued…"}
                </>
              ) : (
                <>
                  <Scissors className="h-4 w-4" /> Run attribute edit
                </>
              )}
            </Button>
          </div>
        </form>

        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold">Source &amp; mask preview</h3>
          <div className="relative aspect-square overflow-hidden rounded-md border border-border bg-background/60">
            {selectedUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={selectedUrl} alt={selectedAsset?.filename ?? ""} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <ImageIcon className="h-7 w-7" />
                Upload a ready product asset first.
              </div>
            )}
            {previewUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewUrl}
                alt="mask preview"
                className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-70"
                style={{ mixBlendMode: "screen" }}
              />
            ) : null}
          </div>
          {previewUrl ? (
            <p className="mt-2 text-xs text-primary">
              Mask preview overlaid — the highlighted region is what will be edited.
            </p>
          ) : null}
          {previewNote ? (
            <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{previewNote}</p>
          ) : null}
          {latest ? (
            <div className="mt-4">
              <SceneCard scene={latest} featured />
            </div>
          ) : null}
        </div>
      </div>

      <div>
        <h3 className="mb-4 text-sm font-semibold">Attribute edit history</h3>
        {attributeScenes.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <Scissors className="h-7 w-7" />
            No attribute edits yet.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {attributeScenes.map((scene) => (
              <SceneCard key={scene.id} scene={scene} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SceneCard({
  scene,
  featured = false,
}: {
  scene: ProductSceneGeneration;
  featured?: boolean;
}) {
  const src = assetUrl(scene.result_url);
  const route = routeForScene(scene);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function saveToLibrary() {
    setSaving(true);
    try {
      await api.saveSceneAsAsset(scene.id);
      setSaved(true);
    } catch {
      /* surfaced by disabled state staying off */
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="relative aspect-square bg-background/60">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={scene.prompt} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Scissors className="h-7 w-7" />
            {scene.status}
          </div>
        )}
        <Badge variant={STATUS_VARIANT[scene.status]} className="absolute right-2 top-2 capitalize">
          {scene.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <Badge variant="outline">{ROUTE_LABEL[route]}</Badge>
          {scene.target_attribute ? (
            <Badge variant="outline" className="capitalize">{scene.target_attribute}</Badge>
          ) : null}
        </div>
        <p className="line-clamp-2 text-sm text-foreground/90">{scene.prompt}</p>
        {scene.status === "failed" && scene.error ? (
          <p className="line-clamp-3 text-xs text-destructive">{scene.error}</p>
        ) : null}
        {scene.status === "completed" ? (
          <div className="flex gap-2">
            <a
              href={api.exportSceneUrl(scene.id)}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}
            >
              <Download className="h-4 w-4" /> Download
            </a>
            <button
              type="button"
              onClick={saveToLibrary}
              disabled={saving || saved}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}
            >
              <Archive className="h-4 w-4" /> {saved ? "Saved" : saving ? "Saving…" : "Save to Library"}
            </button>
          </div>
        ) : null}
        {featured ? <span className="text-xs text-muted-foreground">Latest</span> : null}
      </div>
    </div>
  );
}
