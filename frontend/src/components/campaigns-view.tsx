"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Download, ImageIcon, Loader2, Package, Rocket } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  CampaignPreset,
  CampaignResult,
  ProductAsset,
  Project,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { BriefSelect } from "@/components/brief-select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);
const DEFAULT_PRODUCT = "your product";
const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function CampaignsView() {
  const [presets, setPresets] = useState<CampaignPreset[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);

  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [productName, setProductName] = useState("");
  const [presetId, setPresetId] = useState("");
  const [briefId, setBriefId] = useState("");

  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [campaign, setCampaign] = useState<CampaignResult | null>(null);

  const projectAssets = useMemo(
    () =>
      assets.filter(
        (a) => a.project_id === projectId && READY_ASSET_STATUSES.has(a.status),
      ),
    [assets, projectId],
  );
  const selectedPreset = presets.find((p) => p.id === presetId) ?? null;
  const previewPrompt = selectedPreset
    ? selectedPreset.scene_prompt_template.replace(
        "{product}",
        productName.trim() || DEFAULT_PRODUCT,
      )
    : "";

  useEffect(() => {
    async function load() {
      try {
        const [presetList, projectList, assetList] = await Promise.all([
          api.listPresets(),
          api.listProjects(),
          api.listAssets(undefined, "product_scenes"),
        ]);
        setPresets(presetList);
        setProjects(projectList);
        setAssets(assetList);
        setProjectId(assetList[0]?.project_id ?? projectList[0]?.id ?? "");
        setPresetId(presetList[0]?.id ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load campaigns");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    setAssetId(projectAssets[0]?.id ?? "");
  }, [projectAssets]);

  // Poll the linked scene + copy jobs until both settle.
  useEffect(() => {
    if (!campaign) return;
    const sceneActive = ["queued", "running"].includes(campaign.scene_job.status);
    const copyActive = ["queued", "running"].includes(campaign.copy_job.status);
    if (!sceneActive && !copyActive) return;

    const poll = window.setInterval(async () => {
      const [scene, copy] = await Promise.all([
        api.getProductScene(campaign.scene_job.id),
        api.getCopy(campaign.copy_job.id),
      ]);
      setCampaign((current) =>
        current ? { ...current, scene_job: scene, copy_job: copy } : current,
      );
    }, 2500);
    return () => window.clearInterval(poll);
  }, [campaign]);

  async function handleLaunch() {
    if (!projectId || !assetId || !presetId || launching) return;
    setLaunching(true);
    setError(null);
    try {
      const result = await api.createCampaignFromPreset({
        project_id: projectId,
        asset_id: assetId,
        preset_id: presetId,
        product_name: productName.trim() || null,
        brief_id: briefId || null,
      });
      setCampaign(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start campaign");
    } finally {
      setLaunching(false);
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
    <div className="space-y-8">
      {/* Preset gallery */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {presets.map((preset) => {
          const active = preset.id === presetId;
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => setPresetId(preset.id)}
              className={cn(
                "rounded-lg border p-5 text-left transition-colors",
                active
                  ? "border-primary bg-primary/10"
                  : "border-border bg-card hover:border-primary/50",
              )}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium">{preset.name}</span>
                {active ? <Check className="h-4 w-4 text-primary" /> : null}
              </div>
              <p className="mb-3 text-sm text-muted-foreground">
                {preset.description}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="muted" className="capitalize">
                  {preset.scene_preset}
                </Badge>
                <Badge variant="muted">{preset.scene_mode}</Badge>
                <Badge variant="muted">{preset.copy_type.replace("_", " ")}</Badge>
                <Badge variant="muted" className="capitalize">
                  {preset.tone}
                </Badge>
              </div>
            </button>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        {/* Setup */}
        <div className="h-fit space-y-5 rounded-lg border border-border bg-card p-6">
          <div className="space-y-2">
            <Label htmlFor="campaign-project">Project</Label>
            <select
              id="campaign-project"
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

          <div className="space-y-2">
            <Label htmlFor="campaign-asset">Product asset</Label>
            <select
              id="campaign-asset"
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              className={selectClass}
            >
              {projectAssets.length === 0 ? (
                <option value="">No ready assets</option>
              ) : null}
              {projectAssets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.filename}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="campaign-product">Product name (optional)</Label>
            <Input
              id="campaign-product"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder="e.g. glow serum"
            />
          </div>

          <BriefSelect
            projectId={projectId}
            value={briefId}
            onChange={setBriefId}
            id="campaign-brief"
          />

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button
            size="lg"
            onClick={handleLaunch}
            disabled={!projectId || !assetId || !presetId || launching}
          >
            {launching ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Starting…
              </>
            ) : (
              <>
                <Rocket className="h-4 w-4" /> Start campaign
              </>
            )}
          </Button>
        </div>

        {/* Preview + results */}
        <div className="space-y-4">
          {selectedPreset ? (
            <div className="rounded-lg border border-border bg-card p-6">
              <h3 className="mb-3 text-sm font-semibold">
                Preview · {selectedPreset.name}
              </h3>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-muted-foreground">Scene prompt</dt>
                  <dd className="text-foreground/90">{previewPrompt}</dd>
                </div>
                <div className="flex gap-6">
                  <div>
                    <dt className="text-muted-foreground">Copy</dt>
                    <dd className="capitalize">
                      {selectedPreset.copy_type.replace("_", " ")} ·{" "}
                      {selectedPreset.tone}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Audience</dt>
                    <dd>{selectedPreset.audience_hint}</dd>
                  </div>
                </div>
              </dl>
            </div>
          ) : null}

          {campaign ? (
            <CampaignResultView campaign={campaign} />
          ) : (
            <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
              <Rocket className="h-6 w-6" />
              Start a campaign to see the generated scene and copy here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CampaignResultView({ campaign }: { campaign: CampaignResult }) {
  const [copied, setCopied] = useState(false);
  const [bundling, setBundling] = useState(false);
  const [bundleError, setBundleError] = useState<string | null>(null);
  const scene = campaign.scene_job;
  const copy = campaign.copy_job;
  const sceneSrc = assetUrl(scene.result_url);
  const canBundle =
    scene.status === "completed" || copy.status === "completed";

  async function handleCopy() {
    if (!copy.result_text) return;
    await navigator.clipboard.writeText(copy.result_text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  async function handleBundle() {
    if (!canBundle || bundling) return;
    setBundling(true);
    setBundleError(null);
    try {
      await api.downloadCampaignBundle({
        scene_id: scene.status === "completed" ? scene.id : null,
        copy_id: copy.status === "completed" ? copy.id : null,
      });
    } catch (err) {
      setBundleError(err instanceof Error ? err.message : "Bundle export failed");
    } finally {
      setBundling(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <Button
          variant="outline"
          onClick={handleBundle}
          disabled={!canBundle || bundling}
        >
          {bundling ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Package className="h-4 w-4" />
          )}
          Download bundle (.zip)
        </Button>
        {bundleError ? (
          <span className="text-sm text-destructive">{bundleError}</span>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">Scene</h4>
          <Badge variant={STATUS_VARIANT[scene.status]} className="capitalize">
            {scene.status}
          </Badge>
        </div>
        <div className="aspect-square overflow-hidden rounded-md border border-border bg-background/60">
          {sceneSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={sceneSrc}
              alt={scene.prompt}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              {scene.status === "failed" ? (
                <span className="px-3 text-center text-destructive">
                  {scene.error ?? "Scene failed"}
                </span>
              ) : (
                <>
                  <ImageIcon className="h-7 w-7" />
                  <Loader2 className="h-4 w-4 animate-spin" />
                </>
              )}
            </div>
          )}
        </div>
        {scene.status === "completed" ? (
          <a
            href={api.exportSceneUrl(scene.id)}
            className={cn(
              buttonVariants({ variant: "outline", size: "sm" }),
              "mt-3 w-full",
            )}
          >
            <Download className="h-4 w-4" /> Download image
          </a>
        ) : null}
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">Copy</h4>
          <div className="flex items-center gap-2">
            <Badge variant={STATUS_VARIANT[copy.status]} className="capitalize">
              {copy.status}
            </Badge>
            {copy.status === "completed" && copy.result_text ? (
              <>
                <Button variant="ghost" size="sm" onClick={handleCopy}>
                  {copied ? (
                    <>
                      <Check className="h-4 w-4" /> Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4" /> Copy
                    </>
                  )}
                </Button>
                <a
                  href={api.exportCopyUrl(copy.id)}
                  className={buttonVariants({ variant: "ghost", size: "sm" })}
                >
                  <Download className="h-4 w-4" /> .txt
                </a>
              </>
            ) : null}
          </div>
        </div>
        {copy.status === "completed" && copy.result_text ? (
          <pre className="whitespace-pre-wrap rounded-md bg-background/50 p-3 text-sm text-foreground/90">
            {copy.result_text}
          </pre>
        ) : copy.status === "failed" ? (
          <p className="text-sm text-destructive">{copy.error ?? "Copy failed"}</p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {copy.status === "running" ? "Writing…" : "Queued…"}
          </p>
        )}
      </div>
      </div>
    </div>
  );
}
