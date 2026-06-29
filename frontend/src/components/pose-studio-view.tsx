"use client";

import { useEffect, useMemo, useState } from "react";
import { Archive, Download, ImageIcon, Loader2, PersonStanding } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { ProductAsset, ProductSceneGeneration, ProductSceneMode, Project } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type PoseSource = "preset" | "reference";
type PoseMode = Extract<ProductSceneMode, "pose_edit" | "pose_stylized">;

const POSE_MODES: { value: PoseMode; label: string; hint: string }[] = [
  {
    value: "pose_edit",
    label: "Identity Pose",
    hint: "Preferred: SDXL + OpenPose + IPAdapter preserves identity before Qwen refine.",
  },
  {
    value: "pose_stylized",
    label: "Stylized Pose",
    hint: "Fallback: SDXL + OpenPose then Qwen refine; identity is approximate.",
  },
];

const PRESETS: { label: string; value: string }[] = [
  { label: "Standing", value: "standing" },
  { label: "Walking", value: "walking" },
  { label: "Sitting", value: "sitting" },
  { label: "Runway", value: "runway" },
  { label: "Crossed arms", value: "crossed_arms" },
  { label: "Hands in pockets", value: "hands_in_pockets" },
  { label: "Action pose", value: "action" },
];

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const READY = new Set(["uploaded", "completed"]);
const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function PoseStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [poseMode, setPoseMode] = useState<PoseMode>("pose_edit");
  const [poseSource, setPoseSource] = useState<PoseSource>("preset");
  const [preset, setPreset] = useState("walking");
  const [refFile, setRefFile] = useState<File | null>(null);
  const [refPreview, setRefPreview] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<ProductSceneGeneration | null>(null);

  const readyAssets = useMemo(
    () => assets.filter((a) => a.project_id === projectId && READY.has(a.status)),
    [assets, projectId],
  );
  const selectedAsset = assets.find((a) => a.id === assetId);
  const poseScenes = useMemo(
    () => scenes.filter((s) => s.mode === "pose_edit" || s.mode === "pose_stylized"),
    [scenes],
  );
  const activeJob = latest?.status === "queued" || latest?.status === "running";
  // Preset skeletons are served statically; reference shows the uploaded photo.
  const posePreview =
    poseSource === "preset"
      ? assetUrl(`/storage/pose_presets/${preset}.png`)
      : refPreview;

  useEffect(() => {
    async function load() {
      try {
        const [p, a, s] = await Promise.all([
          api.listProjects(),
          api.listAssets(),
          api.listProductScenes(),
        ]);
        setProjects(p);
        setAssets(a);
        setScenes(s);
        const pid =
          a.find((x) => READY.has(x.status))?.project_id ?? p[0]?.id ?? "";
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
    const active = poseScenes.filter(
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
      setLatest((cur) => (cur ? updates.find((u) => u.id === cur.id) ?? cur : cur));
    }, 2500);
    return () => window.clearInterval(poll);
  }, [latest, poseScenes]);

  function onRefChange(file: File | null) {
    setRefFile(file);
    setRefPreview(file ? URL.createObjectURL(file) : null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !assetId || !prompt.trim() || submitting || activeJob) return;
    if (poseSource === "reference" && !refFile) {
      setError("Upload a pose reference image, or choose a preset.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (poseSource === "reference" && refFile) {
        // The reference photo rides the asset mask slot; the backend DWPose-s it.
        const updated = await api.uploadAssetMask(assetId, refFile);
        setAssets((cur) => cur.map((a) => (a.id === updated.id ? updated : a)));
      }
      const scene = await api.createProductScene({
        project_id: projectId,
        asset_id: assetId,
        prompt: prompt.trim(),
        preset: "studio",
        mode: poseMode,
        target_attribute: poseSource === "preset" ? preset : null,
      });
      setLatest(scene);
      setScenes((cur) => [scene, ...cur]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pose edit failed");
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

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-lg border border-border bg-card p-6"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ps-project">Project</Label>
              <select id="ps-project" value={projectId} onChange={(e) => setProjectId(e.target.value)} className={selectClass}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ps-asset">Source image</Label>
              <select id="ps-asset" value={assetId} onChange={(e) => setAssetId(e.target.value)} className={selectClass}>
                {readyAssets.length === 0 ? <option value="">No ready assets</option> : null}
                {readyAssets.map((a) => (
                  <option key={a.id} value={a.id}>{a.filename}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Pose mode</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              {POSE_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setPoseMode(m.value)}
                  className={cn(
                    "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                    poseMode === m.value
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  <span className="block font-medium text-foreground">{m.label}</span>
                  <span className="mt-1 block text-xs leading-5">{m.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Pose source</Label>
            <div className="grid grid-cols-2 gap-2">
              {(["preset", "reference"] as PoseSource[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setPoseSource(s)}
                  className={cn(
                    "rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors",
                    poseSource === s
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  {s === "preset" ? "Pose preset" : "Reference image"}
                </button>
              ))}
            </div>
          </div>

          {poseSource === "preset" ? (
            <div className="space-y-2">
              <Label htmlFor="ps-preset">Pose preset</Label>
              <select id="ps-preset" value={preset} onChange={(e) => setPreset(e.target.value)} className={selectClass}>
                {PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
          ) : (
            <div className="space-y-2 rounded-md border border-border bg-background/40 p-3">
              <Label htmlFor="ps-ref">Pose reference image</Label>
              <input
                id="ps-ref"
                type="file"
                accept="image/*"
                onChange={(e) => onRefChange(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-1.5 file:text-primary"
              />
              <p className="text-xs text-muted-foreground">
                The reference&apos;s body pose (via OpenPose) drives the new pose.
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="ps-prompt">Prompt</Label>
            <Textarea
              id="ps-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the subject and scene, e.g. a man in a brown shirt and tan trousers, studio backdrop, editorial fashion photo."
              className="min-h-[100px]"
            />
          </div>

          <p className="rounded-md bg-background/40 px-3 py-2 text-xs text-muted-foreground">
            Identity Pose uses IPAdapter to preserve the source person before Qwen
            refinement. If IPAdapter is unavailable, use Stylized Pose as the
            approximate-identity fallback.
          </p>

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
          ) : null}

          <Button type="submit" size="lg" disabled={!projectId || !assetId || !prompt.trim() || submitting || activeJob}>
            {submitting || activeJob ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {latest?.status === "running" ? "Posingâ€¦" : "Queuedâ€¦"}
              </>
            ) : (
              <>
                <PersonStanding className="h-4 w-4" /> Generate pose
              </>
            )}
          </Button>
        </form>

        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="mb-3 text-sm font-semibold">Source</h3>
          <div className="aspect-square overflow-hidden rounded-md border border-border bg-background/60">
            {selectedUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={selectedUrl} alt={selectedAsset?.filename ?? ""} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <ImageIcon className="h-7 w-7" /> Upload a ready asset first.
              </div>
            )}
          </div>
          <h3 className="mb-2 mt-4 text-sm font-semibold">Target pose (OpenPose)</h3>
          <div className="aspect-square overflow-hidden rounded-md border border-border bg-black">
            {posePreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={posePreview} alt="pose preview" className="h-full w-full object-contain" />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                Pick a preset or upload a reference.
              </div>
            )}
          </div>
          {latest ? (
            <div className="mt-4">
              <PoseCard scene={latest} featured />
            </div>
          ) : null}
        </div>
      </div>

      <div>
        <h3 className="mb-4 text-sm font-semibold">Pose history</h3>
        {poseScenes.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <PersonStanding className="h-7 w-7" /> No pose generations yet.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {poseScenes.map((s) => (
              <PoseCard key={s.id} scene={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PoseCard({ scene, featured = false }: { scene: ProductSceneGeneration; featured?: boolean }) {
  const src = assetUrl(scene.result_url);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  async function saveToLibrary() {
    setSaving(true);
    try {
      await api.saveSceneAsAsset(scene.id);
      setSaved(true);
    } catch {
      /* button stays enabled */
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
            <PersonStanding className="h-7 w-7" /> {scene.status}
          </div>
        )}
        <Badge variant={STATUS_VARIANT[scene.status]} className="absolute right-2 top-2 capitalize">
          {scene.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        {scene.target_attribute ? (
          <Badge variant="outline" className="capitalize">{scene.target_attribute.replaceAll("_", " ")}</Badge>
        ) : (
          <Badge variant="outline">reference pose</Badge>
        )}
        <Badge variant="outline">{scene.mode === "pose_stylized" ? "Stylized Pose" : "Identity Pose"}</Badge>
        <p className="line-clamp-2 text-sm text-foreground/90">{scene.prompt}</p>
        {scene.status === "failed" && scene.error ? (
          <p className="line-clamp-3 text-xs text-destructive">{scene.error}</p>
        ) : null}
        {scene.status === "completed" ? (
          <div className="flex gap-2">
            <a href={api.exportSceneUrl(scene.id)} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}>
              <Download className="h-4 w-4" /> Download
            </a>
            <button type="button" onClick={saveToLibrary} disabled={saving || saved} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "flex-1")}>
              <Archive className="h-4 w-4" /> {saved ? "Saved" : saving ? "Savingâ€¦" : "Save"}
            </button>
          </div>
        ) : null}
        {featured ? <span className="text-xs text-muted-foreground">Latest</span> : null}
      </div>
    </div>
  );
}
