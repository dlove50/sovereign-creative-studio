"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, FileArchive, Loader2, PackageCheck } from "lucide-react";

import { api } from "@/lib/api";
import type { CampaignBundle, CreativeBrief, Project, ProjectWorkspace } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const PLATFORMS = ["instagram", "facebook", "linkedin", "x"];

export function ExportStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [projectId, setProjectId] = useState("");
  const [briefId, setBriefId] = useState("");
  const [bundleId, setBundleId] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(["instagram", "facebook"]);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((loaded) => {
        setProjects(loaded);
        setProjectId(loaded[0]?.id ?? "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load projects"),
      );
  }, []);

  useEffect(() => {
    if (!projectId) {
      setWorkspace(null);
      return;
    }
    api
      .getProjectWorkspace(projectId)
      .then((loaded) => {
        setWorkspace(loaded);
        setBriefId((current) =>
          loaded.creative_briefs.some((brief) => brief.id === current)
            ? current
            : loaded.creative_briefs[0]?.id ?? "",
        );
        setBundleId((current) =>
          loaded.campaign_bundles.some((bundle) => bundle.id === current)
            ? current
            : loaded.campaign_bundles[0]?.id ?? "",
        );
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load workspace"),
      );
  }, [projectId]);

  const counts = useMemo(() => {
    if (!workspace) return { scenes: 0, copy: 0, videos: 0, briefs: 0 };
    return {
      scenes: workspace.product_scenes.length,
      copy: workspace.copy_generations.length,
      videos: workspace.video_generations.length,
      briefs: workspace.creative_briefs.length,
    };
  }, [workspace]);

  function togglePlatform(platform: string) {
    setPlatforms((current) =>
      current.includes(platform)
        ? current.filter((item) => item !== platform)
        : [...current, platform],
    );
  }

  async function download(kind: "social" | "marketing") {
    if (!projectId || downloading) return;
    setDownloading(kind);
    setError(null);
    try {
      const input = {
        project_id: projectId,
        brief_id: briefId || null,
        campaign_bundle_id: bundleId || null,
        platforms: kind === "social" ? platforms : [],
      };
      if (kind === "social") await api.downloadSocialBundle(input);
      else await api.downloadMarketingBundle(input);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDownloading(null);
    }
  }

  if (projects.length === 0 && !error) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Package settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="export-project">Project</Label>
            <select
              id="export-project"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              className={selectClass}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>

          <SelectBrief briefs={workspace?.creative_briefs ?? []} value={briefId} onChange={setBriefId} />
          <SelectBundle bundles={workspace?.campaign_bundles ?? []} value={bundleId} onChange={setBundleId} />

          <div className="space-y-2">
            <Label>Social platforms</Label>
            <div className="grid grid-cols-2 gap-2">
              {PLATFORMS.map((platform) => (
                <button
                  key={platform}
                  type="button"
                  onClick={() => togglePlatform(platform)}
                  className={cn(
                    "rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors",
                    platforms.includes(platform)
                      ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:bg-muted",
                  )}
                >
                  {platform}
                </button>
              ))}
            </div>
          </div>

          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-4">
          <CountCard label="Scenes" value={counts.scenes} />
          <CountCard label="Copy" value={counts.copy} />
          <CountCard label="Videos" value={counts.videos} />
          <CountCard label="Briefs" value={counts.briefs} />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <ExportCard
            title="Social Bundle"
            description="Creates platform folders for Instagram, Facebook, LinkedIn, and X with copy, scene images, video prompts, brand kit, brief, and metadata."
            badge="Social"
            loading={downloading === "social"}
            disabled={!projectId || platforms.length === 0}
            onDownload={() => download("social")}
          />
          <ExportCard
            title="Marketing Bundle"
            description="Packages project scenes, campaign copy, video prompts, briefs, brand kit, and metadata for broader campaign handoff."
            badge="Marketing"
            loading={downloading === "marketing"}
            disabled={!projectId}
            onDownload={() => download("marketing")}
          />
        </div>
      </div>
    </div>
  );
}

function SelectBrief({
  briefs,
  onChange,
  value,
}: {
  briefs: CreativeBrief[];
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="export-brief">Creative brief</Label>
      <select
        id="export-brief"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={selectClass}
      >
        <option value="">No brief</option>
        {briefs.map((brief) => (
          <option key={brief.id} value={brief.id}>
            {brief.title}
          </option>
        ))}
      </select>
    </div>
  );
}

function SelectBundle({
  bundles,
  onChange,
  value,
}: {
  bundles: CampaignBundle[];
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="export-bundle">Campaign bundle</Label>
      <select
        id="export-bundle"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={selectClass}
      >
        <option value="">No campaign bundle</option>
        {bundles.map((bundle) => (
          <option key={bundle.id} value={bundle.id}>
            {bundle.title}
          </option>
        ))}
      </select>
    </div>
  );
}

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ExportCard({
  badge,
  description,
  disabled,
  loading,
  onDownload,
  title,
}: {
  badge: string;
  description: string;
  disabled: boolean;
  loading: boolean;
  onDownload: () => void;
  title: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <FileArchive className="h-5 w-5 text-primary" />
              <h3 className="font-semibold">{title}</h3>
            </div>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          <Badge variant="outline">{badge}</Badge>
        </div>
        <Button type="button" disabled={disabled || loading} onClick={onDownload}>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Download ZIP
        </Button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <PackageCheck className="h-4 w-4" />
          Uses existing generated files and metadata; no new generation is run.
        </div>
      </CardContent>
    </Card>
  );
}
