"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Boxes, Check, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type {
  BrandKit,
  CampaignBuilderResult,
  CampaignType,
  CreativeBrief,
  ProductAsset,
  Project,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const CAMPAIGN_TYPES: { value: CampaignType; label: string; hint: string }[] = [
  { value: "product_launch", label: "Product Launch", hint: "3 scenes · 3 copy · 1 video" },
  { value: "ecommerce", label: "Ecommerce", hint: "2 scenes · 2 copy" },
  { value: "social_media", label: "Social Media", hint: "2 scenes · 2 copy" },
  { value: "fashion_editorial", label: "Fashion Editorial", hint: "3 scenes · 1 copy" },
  { value: "luxury_brand", label: "Luxury Brand", hint: "2 scenes · 1 copy" },
  { value: "custom", label: "Custom", hint: "1 scene · 1 copy" },
];

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);
const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function CampaignBuilderView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [brandKit, setBrandKit] = useState<BrandKit | null>(null);

  const [projectId, setProjectId] = useState("");
  const [briefId, setBriefId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [campaignType, setCampaignType] = useState<CampaignType>("product_launch");

  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CampaignBuilderResult | null>(null);

  const projectAssets = useMemo(
    () => assets.filter((a) => READY_ASSET_STATUSES.has(a.status)),
    [assets],
  );
  const selectedBrief = briefs.find((b) => b.id === briefId) ?? null;

  useEffect(() => {
    Promise.all([api.listProjects(), api.listAssets(undefined, "product_scenes")])
      .then(([list, readyAssets]) => {
        setProjects(list);
        setProjectId(readyAssets[0]?.project_id ?? list[0]?.id ?? "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load projects"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setResult(null);
    Promise.all([
      api.listBriefs(projectId),
      api.listAssets(projectId, "product_scenes"),
      api.getBrandKit(projectId),
    ])
      .then(([briefList, assetList, kit]) => {
        setBriefs(briefList);
        setAssets(assetList);
        setBrandKit(kit);
        setBriefId(briefList[0]?.id ?? "");
        setAssetId(
          assetList.find((a) => READY_ASSET_STATUSES.has(a.status))?.id ?? "",
        );
      })
      .catch(() => {
        setBriefs([]);
        setAssets([]);
        setBrandKit(null);
      });
  }, [projectId]);

  async function handleGenerate() {
    if (!projectId || !briefId || !assetId || generating) return;
    setGenerating(true);
    setError(null);
    try {
      setResult(
        await api.createCampaign(projectId, {
          brief_id: briefId,
          asset_id: assetId,
          campaign_type: campaignType,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Campaign generation failed");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  const brandRows = brandKit
    ? ([
        ["Brand", brandKit.brand_name],
        ["Voice", brandKit.brand_voice],
        ["Audience", brandKit.target_audience],
        ["Style", brandKit.style_keywords],
      ].filter(([, v]) => v) as [string, string][])
    : [];

  return (
    <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
      {/* Setup */}
      <div className="h-fit space-y-5 rounded-lg border border-border bg-card p-6">
        <div className="space-y-2">
          <Label htmlFor="cb-project">Project</Label>
          <select
            id="cb-project"
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
          <Label htmlFor="cb-brief">Creative brief</Label>
          <select
            id="cb-brief"
            value={briefId}
            onChange={(e) => setBriefId(e.target.value)}
            className={selectClass}
          >
            {briefs.length === 0 ? <option value="">No briefs</option> : null}
            {briefs.map((b) => (
              <option key={b.id} value={b.id}>
                {b.title}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="cb-asset">Product asset</Label>
          <select
            id="cb-asset"
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
          <Label>Campaign type</Label>
          <div className="grid grid-cols-2 gap-2">
            {CAMPAIGN_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setCampaignType(t.value)}
                className={cn(
                  "rounded-md border px-3 py-2 text-left text-sm font-medium transition-colors",
                  campaignType === t.value
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                <span className="block">{t.label}</span>
                <span className="block text-xs font-normal">{t.hint}</span>
              </button>
            ))}
          </div>
        </div>

        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button
          size="lg"
          onClick={handleGenerate}
          disabled={!projectId || !briefId || !assetId || generating}
        >
          {generating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Generating campaign…
            </>
          ) : (
            <>
              <Boxes className="h-4 w-4" /> Generate Campaign
            </>
          )}
        </Button>
      </div>

      {/* Context + results */}
      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-3 p-5">
            <h3 className="text-sm font-semibold">Brand kit</h3>
            {brandRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No brand kit yet — campaigns still run, just with less guidance.
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {brandRows.map(([label, value]) => (
                  <div key={label} className="rounded-md border border-border bg-background/40 p-2">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="line-clamp-2 text-sm">{value}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2 p-5">
            <h3 className="text-sm font-semibold">Creative brief</h3>
            {selectedBrief ? (
              <>
                <p className="text-sm font-medium">{selectedBrief.title}</p>
                <p className="text-sm text-muted-foreground">
                  {selectedBrief.campaign_goal || "No campaign goal set."}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Select a brief to guide the campaign.
              </p>
            )}
          </CardContent>
        </Card>

        {result ? (
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-2">
                <Check className="h-5 w-5 text-emerald-400" />
                <h3 className="text-sm font-semibold">{result.title}</h3>
                <Badge variant="success" className="capitalize">
                  {result.status}
                </Badge>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Scenes" value={result.scene_count} />
                <Stat label="Copy" value={result.copy_count} />
                <Stat label="Videos" value={result.video_prompt_count} />
              </div>
              <p className="text-sm text-muted-foreground">
                Jobs are queued and running. Track them on the generation pages:
              </p>
              <div className="flex flex-wrap gap-2">
                <ResultLink href="/product-scenes" label="Product Scenes" />
                <ResultLink href="/copy-studio" label="Copy Studio" />
                <ResultLink href="/videos" label="Videos" />
                <ResultLink
                  href={`/projects/${projectId}`}
                  label="Project workspace"
                />
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3 text-center">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function ResultLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className={cn(buttonVariants({ variant: "outline", size: "sm" }))}>
      {label}
    </Link>
  );
}
