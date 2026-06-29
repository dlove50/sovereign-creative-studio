"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Boxes,
  Check,
  Layers3,
  Loader2,
  Play,
  Trash2,
  XCircle,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  AssetCollection,
  CampaignType,
  CollectionCampaignResult,
  CreativeBrief,
  ProductAsset,
  Project,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);
const CAMPAIGN_TYPES: { value: CampaignType; label: string; hint: string }[] = [
  { value: "product_launch", label: "Product Launch", hint: "Full launch set" },
  { value: "ecommerce", label: "Ecommerce", hint: "Commerce scenes and copy" },
  { value: "social_media", label: "Social Media", hint: "Social ad variants" },
  { value: "fashion_editorial", label: "Fashion Editorial", hint: "Editorial scenes" },
  { value: "luxury_brand", label: "Luxury Brand", hint: "Premium brand set" },
  { value: "custom", label: "Custom", hint: "Compact starter set" },
];
const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function AssetCollectionsView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);
  const [briefId, setBriefId] = useState("");
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [collections, setCollections] = useState<AssetCollection[]>([]);
  const [selectedCollectionId, setSelectedCollectionId] = useState("");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [campaignType, setCampaignType] = useState<CampaignType>("product_launch");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CollectionCampaignResult | null>(null);

  const readyAssets = useMemo(
    () => assets.filter((asset) => READY_ASSET_STATUSES.has(asset.status)),
    [assets],
  );
  const selectedCollection =
    collections.find((collection) => collection.id === selectedCollectionId) ??
    null;
  const selectedAssets = selectedCollection
    ? readyAssets.filter((asset) => selectedCollection.asset_ids.includes(asset.id))
    : readyAssets.filter((asset) => selectedAssetIds.includes(asset.id));

  useEffect(() => {
    api
      .listProjects()
      .then((list) => {
        setProjects(list);
        setProjectId(list[0]?.id ?? "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load projects"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setError(null);
    setResult(null);
    Promise.all([
      api.listBriefs(projectId),
      api.listAssets(projectId, "product_scenes"),
      api.listCollections(projectId),
    ])
      .then(([briefList, assetList, collectionList]) => {
        setBriefs(briefList);
        setAssets(assetList);
        setCollections(collectionList);
        setBriefId(briefList[0]?.id ?? "");
        setSelectedCollectionId(collectionList[0]?.id ?? "");
        setSelectedAssetIds([]);
      })
      .catch((err) => {
        setBriefs([]);
        setAssets([]);
        setCollections([]);
        setError(err instanceof Error ? err.message : "Could not load collections");
      });
  }, [projectId]);

  function toggleAsset(assetId: string) {
    setSelectedAssetIds((current) =>
      current.includes(assetId)
        ? current.filter((id) => id !== assetId)
        : [...current, assetId],
    );
  }

  async function handleCreateCollection() {
    if (!projectId || saving || selectedAssetIds.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const collection = await api.createCollection(projectId, {
        name: name.trim() || "Untitled collection",
        description: description.trim() || null,
        asset_ids: selectedAssetIds,
        status: "active",
      });
      setCollections((current) => [collection, ...current]);
      setSelectedCollectionId(collection.id);
      setName("");
      setDescription("");
      setSelectedAssetIds([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save collection");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteCollection(collectionId: string) {
    if (!projectId) return;
    setError(null);
    try {
      await api.deleteCollection(projectId, collectionId);
      setCollections((current) =>
        current.filter((collection) => collection.id !== collectionId),
      );
      if (selectedCollectionId === collectionId) setSelectedCollectionId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete collection");
    }
  }

  async function handleGenerateCampaign() {
    if (!projectId || !briefId || !selectedCollectionId || generating) return;
    setGenerating(true);
    setError(null);
    try {
      setResult(
        await api.createCollectionCampaign(projectId, selectedCollectionId, {
          collection_id: selectedCollectionId,
          brief_id: briefId,
          campaign_type: campaignType,
        }),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Collection campaign generation failed",
      );
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

  return (
    <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
      <div className="space-y-5">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="space-y-2">
              <Label htmlFor="collection-project">Project</Label>
              <select
                id="collection-project"
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

            {error ? (
              <div className="flex items-center gap-2 rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" />
                {error}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 p-5">
            <div>
              <h2 className="text-sm font-semibold">New collection</h2>
              <p className="text-sm text-muted-foreground">
                Select multiple ready assets to use as one campaign input.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-name">Name</Label>
              <Input
                id="collection-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Spring outerwear set"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-description">Description</Label>
              <Textarea
                id="collection-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Products, visual notes, or campaign purpose"
                rows={3}
              />
            </div>
            <AssetPicker
              assets={readyAssets}
              selectedAssetIds={selectedAssetIds}
              onToggle={toggleAsset}
            />
            <Button
              type="button"
              onClick={handleCreateCollection}
              disabled={!projectId || selectedAssetIds.length === 0 || saving}
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Saving
                </>
              ) : (
                <>
                  <Layers3 className="h-4 w-4" /> Save Collection
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Saved collections</h2>
                <p className="text-sm text-muted-foreground">
                  Choose a collection, brief, and campaign type.
                </p>
              </div>
              <Badge variant="outline">{collections.length} collections</Badge>
            </div>

            {collections.length === 0 ? (
              <EmptyState />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {collections.map((collection) => (
                  <CollectionCard
                    key={collection.id}
                    collection={collection}
                    active={collection.id === selectedCollectionId}
                    assets={readyAssets}
                    onSelect={() => setSelectedCollectionId(collection.id)}
                    onDelete={() => handleDeleteCollection(collection.id)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="collection-brief">Creative brief</Label>
                <select
                  id="collection-brief"
                  value={briefId}
                  onChange={(event) => setBriefId(event.target.value)}
                  className={selectClass}
                >
                  {briefs.length === 0 ? <option value="">No briefs</option> : null}
                  {briefs.map((brief) => (
                    <option key={brief.id} value={brief.id}>
                      {brief.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="collection-campaign-type">Campaign type</Label>
                <select
                  id="collection-campaign-type"
                  value={campaignType}
                  onChange={(event) =>
                    setCampaignType(event.target.value as CampaignType)
                  }
                  className={selectClass}
                >
                  {CAMPAIGN_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-3">
              <Stat label="Assets" value={selectedAssets.length} />
              <Stat
                label="Scenes each"
                value={campaignEstimate(campaignType).scenes}
              />
              <Stat label="Copy each" value={campaignEstimate(campaignType).copy} />
            </div>

            <Button
              type="button"
              size="lg"
              onClick={handleGenerateCampaign}
              disabled={!selectedCollectionId || !briefId || generating}
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Queuing campaign
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" /> Generate Collection Campaign
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {result ? (
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <Check className="h-5 w-5 text-emerald-400" />
                <h2 className="text-sm font-semibold">{result.title}</h2>
                <Badge variant="success" className="capitalize">
                  {result.status}
                </Badge>
              </div>
              <div className="grid gap-2 sm:grid-cols-4">
                <Stat label="Assets" value={result.asset_count} />
                <Stat label="Scenes" value={result.scene_count} />
                <Stat label="Copy" value={result.copy_count} />
                <Stat label="Videos" value={result.video_prompt_count} />
              </div>
              <p className="text-sm text-muted-foreground">
                Jobs are queued with brand and brief context. Follow progress on the
                existing generation pages or in the project workspace.
              </p>
              <div className="flex flex-wrap gap-2">
                <ResultLink href="/product-scenes" label="Product Scenes" />
                <ResultLink href="/copy-studio" label="Copy Studio" />
                <ResultLink href="/videos" label="Videos" />
                <ResultLink
                  href={`/projects/${projectId}`}
                  label="Project Workspace"
                />
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function AssetPicker({
  assets,
  onToggle,
  selectedAssetIds,
}: {
  assets: ProductAsset[];
  onToggle: (assetId: string) => void;
  selectedAssetIds: string[];
}) {
  if (assets.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
        No uploaded or completed product assets are available for this project.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <Label>Assets</Label>
      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {assets.map((asset) => {
          const selected = selectedAssetIds.includes(asset.id);
          return (
            <button
              key={asset.id}
              type="button"
              onClick={() => onToggle(asset.id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md border p-2 text-left transition-colors",
                selected
                  ? "border-primary bg-primary/10"
                  : "border-border hover:bg-muted",
              )}
            >
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded border",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border",
                )}
              >
                {selected ? <Check className="h-3 w-3" /> : null}
              </span>
              <AssetThumb asset={asset} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {asset.filename}
                </span>
                <span className="text-xs text-muted-foreground">{asset.status}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CollectionCard({
  active,
  assets,
  collection,
  onDelete,
  onSelect,
}: {
  active: boolean;
  assets: ProductAsset[];
  collection: AssetCollection;
  onDelete: () => void;
  onSelect: () => void;
}) {
  const collectionAssets = assets.filter((asset) =>
    collection.asset_ids.includes(asset.id),
  );
  return (
    <div
      className={cn(
        "space-y-3 rounded-lg border p-4",
        active ? "border-primary bg-primary/10" : "border-border bg-background/40",
      )}
    >
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{collection.name}</p>
            <p className="line-clamp-2 text-xs text-muted-foreground">
              {collection.description || "No description"}
            </p>
          </div>
          <Badge variant={active ? "default" : "outline"}>
            {collection.asset_ids.length}
          </Badge>
        </div>
        <div className="flex -space-x-2">
          {collectionAssets.slice(0, 5).map((asset) => (
            <AssetThumb key={asset.id} asset={asset} small />
          ))}
        </div>
      </button>
      <div className="flex items-center justify-between gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onSelect}>
          Select
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

function AssetThumb({
  asset,
  small = false,
}: {
  asset: ProductAsset;
  small?: boolean;
}) {
  const url = assetUrl(asset.processed_url || asset.original_url);
  return (
    <span
      className={cn(
        "block shrink-0 overflow-hidden rounded-md border border-border bg-background",
        small ? "h-9 w-9" : "h-12 w-12",
      )}
    >
      {url ? (
        <img src={url} alt="" className="h-full w-full object-cover" />
      ) : (
        <Boxes className="m-2 h-5 w-5 text-muted-foreground" />
      )}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3 text-center">
      <p className="text-xl font-semibold">{value}</p>
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

function EmptyState() {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-center">
      <Layers3 className="h-7 w-7 text-muted-foreground" />
      <p className="text-sm font-medium">No collections yet</p>
      <p className="max-w-md text-sm text-muted-foreground">
        Create a collection from ready product assets, then generate a campaign
        across the whole set.
      </p>
    </div>
  );
}

function campaignEstimate(type: CampaignType) {
  if (type === "product_launch") return { scenes: 3, copy: 3 };
  if (type === "ecommerce") return { scenes: 2, copy: 2 };
  if (type === "social_media") return { scenes: 2, copy: 2 };
  if (type === "fashion_editorial") return { scenes: 3, copy: 1 };
  if (type === "luxury_brand") return { scenes: 2, copy: 1 };
  return { scenes: 1, copy: 1 };
}
