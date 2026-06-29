"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ImageIcon, Loader2, UploadCloud, Wand2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { ProductAsset, ProductAssetStatus, Project } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

const STATUS_VARIANT = {
  uploaded: "muted",
  processing: "default",
  completed: "success",
  failed: "destructive",
} as const satisfies Record<ProductAssetStatus, string>;

export function UploadView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewUrl = useMemo(() => {
    if (!file) return null;
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    async function load() {
      try {
        const [projectList, assetList] = await Promise.all([
          api.listProjects(),
          api.listAssets(),
        ]);
        setProjects(projectList);
        setProjectId(projectList[0]?.id ?? "");
        setAssets(assetList);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load uploads");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    const active = assets.filter((asset) => asset.status === "processing");
    if (active.length === 0) return;

    const poll = window.setInterval(async () => {
      const updates = await Promise.all(active.map((asset) => api.getAsset(asset.id)));
      setAssets((current) =>
        current.map((asset) => updates.find((item) => item.id === asset.id) ?? asset),
      );
    }, 2500);

    return () => window.clearInterval(poll);
  }, [assets]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !file || saving) return;
    setSaving(true);
    setError(null);
    try {
      const uploaded = await api.uploadAsset(projectId, file);
      setAssets((current) => [uploaded, ...current]);
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSaving(false);
    }
  }

  async function removeBackground(asset: ProductAsset) {
    setError(null);
    try {
      const updated = await api.removeBackground(asset.id);
      setAssets((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Background removal failed");
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
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <form
        onSubmit={handleUpload}
        className="space-y-5 rounded-lg border border-border bg-card p-6"
      >
        <div className="space-y-2">
          <Label htmlFor="asset-project">Project</Label>
          <select
            id="asset-project"
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
          {projects.length === 0 ? (
            <Link href="/projects" className={buttonVariants({ variant: "outline" })}>
              Create a project first
            </Link>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="asset-file">Product image</Label>
          <input
            id="asset-file"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary"
          />
        </div>

        <div className="aspect-square overflow-hidden rounded-md border border-dashed border-border bg-background/60">
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <ImageIcon className="h-7 w-7" />
              Preview
            </div>
          )}
        </div>

        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button type="submit" disabled={!projectId || !file || saving}>
          {saving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Uploading...
            </>
          ) : (
            <>
              <UploadCloud className="h-4 w-4" /> Upload asset
            </>
          )}
        </Button>
      </form>

      <div className="space-y-4">
        {assets.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <UploadCloud className="h-7 w-7" />
            No product assets uploaded yet.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            {assets.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                onRemoveBackground={() => removeBackground(asset)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AssetCard({
  asset,
  onRemoveBackground,
}: {
  asset: ProductAsset;
  onRemoveBackground: () => void;
}) {
  const src = assetUrl(asset.processed_url ?? asset.original_url);
  const busy = asset.status === "processing";

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="relative aspect-square bg-background/60">
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={asset.filename} className="h-full w-full object-cover" />
        ) : null}
        <Badge
          variant={STATUS_VARIANT[asset.status]}
          className="absolute right-2 top-2 capitalize"
        >
          {asset.status}
        </Badge>
      </div>
      <div className="space-y-3 p-3">
        <p className="truncate text-sm text-foreground/90">{asset.filename}</p>
        {asset.status === "failed" && asset.error ? (
          <p className="line-clamp-2 text-xs text-destructive">{asset.error}</p>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRemoveBackground}
          disabled={busy || asset.status === "completed"}
          className="w-full"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Processing...
            </>
          ) : (
            <>
              <Wand2 className="h-4 w-4" /> Remove background
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
