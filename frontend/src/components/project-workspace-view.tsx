"use client";

import { useEffect, useMemo, useState } from "react";
import type React from "react";
import Link from "next/link";
import {
  Check,
  ClipboardList,
  Clipboard,
  Download,
  ExternalLink,
  FileText,
  Film,
  ImageIcon,
  Layers,
  Loader2,
  PackagePlus,
  Pencil,
  PenLine,
  PlaySquare,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
  X,
  XCircle,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  BrandKit,
  CampaignBundle,
  CreativeBrief,
  CreativeBriefInput,
  LibraryItem,
  ProjectWorkspace,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { CreativeBriefsTab } from "@/components/project-workspace/project-briefs-panel";
import { BrandKitEditor, CampaignBundleList, formatDate, ItemGrid, Overview, PreviewModal } from "@/components/project-workspace/project-workspace-sections";

type WorkspaceTab =
  | "overview"
  | "brand"
  | "briefs"
  | "bundles"
  | "uploads"
  | "scenes"
  | "copy"
  | "videos"
  | "campaigns";

const TABS: { value: WorkspaceTab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "brand", label: "Brand Kit" },
  { value: "briefs", label: "Creative Briefs" },
  { value: "bundles", label: "Campaign Bundles" },
  { value: "uploads", label: "Uploads" },
  { value: "scenes", label: "Product Scenes" },
  { value: "copy", label: "Copy" },
  { value: "videos", label: "Videos" },
  { value: "campaigns", label: "Campaigns / Bundles" },
];

const STATUS_VARIANT = {
  uploaded: "muted",
  processing: "default",
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

export function ProjectWorkspaceView({ projectId }: { projectId: string }) {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getProjectWorkspace(projectId)
      .then(setWorkspace)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Unable to load project"),
      );
  }, [projectId]);

  const allItems = useMemo(() => {
    if (!workspace) return [];
    return [
      ...workspace.uploaded_assets,
      ...workspace.processed_assets,
      ...workspace.product_scenes,
      ...workspace.copy_generations,
      ...workspace.video_generations,
      ...workspace.campaign_items,
    ].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
  }, [workspace]);

  async function copySelectedText() {
    if (!selected?.description) return;
    await navigator.clipboard.writeText(selected.description);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (error) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <XCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!workspace) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <h2 className="text-xl font-semibold">{workspace.name}</h2>
            <p className="max-w-3xl text-sm text-muted-foreground">
              {workspace.description || "No project description yet."}
            </p>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>Created {formatDate(workspace.created_at)}</span>
              <span>Latest activity {formatDate(workspace.latest_activity_at)}</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {Object.entries(workspace.counts_by_type).map(([key, value]) => (
              <div
                key={key}
                className="rounded-md border border-border bg-background/40 px-3 py-2 text-center"
              >
                <p className="text-base font-semibold">{value}</p>
                <p className="text-xs text-muted-foreground">{key.replace("_", " ")}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setActiveTab(tab.value)}
            className={cn(
              "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
              activeTab === tab.value
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:bg-muted",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" ? (
        <Overview workspace={workspace} allItems={allItems} onPreview={setSelected} />
      ) : null}
      {activeTab === "brand" ? (
        <BrandKitEditor
          projectId={workspace.id}
          value={workspace.brand_kit}
          onSaved={(brandKit) =>
            setWorkspace((current) =>
              current ? { ...current, brand_kit: brandKit } : current,
            )
          }
        />
      ) : null}
      {activeTab === "briefs" ? (
        <CreativeBriefsTab
          projectId={workspace.id}
          briefs={workspace.creative_briefs}
          onChange={(next) =>
            setWorkspace((current) =>
              current ? { ...current, creative_briefs: next } : current,
            )
          }
        />
      ) : null}
      {activeTab === "bundles" ? (
        <CampaignBundleList bundles={workspace.campaign_bundles} />
      ) : null}
      {activeTab === "uploads" ? (
        <ItemGrid
          empty="No uploaded or processed assets yet."
          items={[...workspace.uploaded_assets, ...workspace.processed_assets]}
          onPreview={setSelected}
        />
      ) : null}
      {activeTab === "scenes" ? (
        <ItemGrid
          empty="No product scenes yet."
          items={workspace.product_scenes}
          onPreview={setSelected}
        />
      ) : null}
      {activeTab === "copy" ? (
        <ItemGrid
          empty="No copy generations yet."
          items={workspace.copy_generations}
          onPreview={setSelected}
        />
      ) : null}
      {activeTab === "videos" ? (
        <ItemGrid
          empty="No videos yet."
          items={workspace.video_generations}
          onPreview={setSelected}
        />
      ) : null}
      {activeTab === "campaigns" ? (
        <ItemGrid
          empty="No stored campaign bundle records yet. Campaign-generated scenes and copy appear in their sections."
          items={workspace.campaign_items}
          onPreview={setSelected}
        />
      ) : null}

      {selected ? (
        <PreviewModal
          copied={copied}
          item={selected}
          onClose={() => setSelected(null)}
          onCopy={copySelectedText}
        />
      ) : null}
    </div>
  );
}
