"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useMemo, useState } from "react";
import type React from "react";
import {
  Archive,
  Check,
  Clipboard,
  Download,
  FileText,
  Film,
  ImageIcon,
  Loader2,
  Package,
  Search,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { LibraryItem, LibraryItemType } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { assetToMedia } from "@/lib/utils/mediaMapping";
import type { HandoffAction } from "@/lib/types/media";
import { cn } from "@/lib/utils";

type TypeFilter = "all" | LibraryItemType;
type StatusFilter = "all" | "completed" | "failed";

const TYPE_FILTERS: { value: TypeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "upload", label: "Uploads" },
  { value: "image", label: "Images" },
  { value: "scene", label: "Scenes" },
  { value: "copy", label: "Copy" },
  { value: "transcript", label: "Transcripts" },
  { value: "video", label: "Videos" },
  { value: "campaign", label: "Campaigns" },
];

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Any status" },
  { value: "completed", label: "Completed only" },
  { value: "failed", label: "Failed only" },
];

const STATUS_VARIANT = {
  uploaded: "muted",
  processing: "default",
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

export function AssetsLibraryView() {
  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Asset Library");
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const projectId = params.get("project_id");
    setProjectFilter(projectId);
    api
      .listLibrary(projectId ?? undefined)
      .then(setItems)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Unable to load library"),
      );
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((item) => {
      if (typeFilter !== "all" && item.type !== typeFilter) return false;
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (!q) return true;
      return [
        item.title,
        item.prompt,
        item.description,
        item.project_name,
        item.type,
        item.status,
      ]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(q));
    });
  }, [items, query, statusFilter, typeFilter]);

  async function trashItem(item: LibraryItem) {
    const map: Record<string, "upload" | "scene" | "video"> = {
      product_asset: "upload",
      product_scene: "scene",
      video_generation: "video",
    };
    const entityType = map[item.source_entity_type];
    if (!entityType) return;
    if (
      !await confirmDialog(
        "Move this asset to trash? This will remove it from the gallery but keep a recoverable copy.",
      )
    )
      return;
    const drop = () =>
      setItems((cur) =>
        cur
          ? cur.filter(
              (i) =>
                !(
                  i.source_entity_type === item.source_entity_type &&
                  i.source_entity_id === item.source_entity_id
                ),
            )
          : cur,
      );
    try {
      await api.trashAsset({ entity_type: entityType, entity_id: item.source_entity_id });
      drop();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not move asset to trash";
      const needsForce = /original|referenced/i.test(msg);
      if (needsForce && await confirmDialog(`${msg}\n\nMove to trash anyway?`)) {
        await api.trashAsset({
          entity_type: entityType,
          entity_id: item.source_entity_id,
          force_original: true,
          force_referenced: true,
        });
        drop();
      } else {
        setError(msg);
      }
    }
  }

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

  if (items === null) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        {projectFilter ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/20 bg-primary/10 px-3 py-2">
            <p className="text-sm text-primary">
              Showing assets for the selected project.
            </p>
            <a href="/assets-library" className="text-sm text-muted-foreground hover:text-foreground">
              Clear project filter
            </a>
          </div>
        ) : null}
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search prompt, filename, project, type"
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {TYPE_FILTERS.map((filter) => (
            <FilterButton
              key={filter.value}
              active={typeFilter === filter.value}
              onClick={() => setTypeFilter(filter.value)}
            >
              {filter.label}
            </FilterButton>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((filter) => (
            <FilterButton
              key={filter.value}
              active={statusFilter === filter.value}
              onClick={() => setStatusFilter(filter.value)}
            >
              {filter.label}
            </FilterButton>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No assets yet"
          description="Uploads, scenes, copy, and videos will appear here as you create them."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No matching assets"
          description="Try a different search or filter."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((item) => (
            <LibraryCard
              key={item.id}
              item={item}
              onPreview={() => setSelected(item)}
              onTrash={() => trashItem(item)}
              onAction={onAction}
            />
          ))}
        </div>
      )}

      {selected ? (
        <PreviewModal
          item={selected}
          copied={copied}
          onCopy={copySelectedText}
          onClose={() => setSelected(null)}
        />
      ) : null}
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function FilterButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "border-primary bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

const TRASHABLE_SOURCES = new Set([
  "product_asset",
  "product_scene",
  "video_generation",
]);

function LibraryCard({
  item,
  onPreview,
  onTrash,
  onAction,
}: {
  item: LibraryItem;
  onPreview: () => void;
  onTrash: () => void;
  onAction: (action: HandoffAction) => void;
}) {
  const canTrash = TRASHABLE_SOURCES.has(item.source_entity_type);
  const showActions =
    item.source_entity_type !== "local_audio" &&
    item.status === "completed" &&
    !!item.asset_url &&
    ["image", "video", "scene", "transcript", "upload", "processed_asset"].includes(item.type);
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onPreview}
        className="relative flex aspect-[4/3] w-full items-center justify-center bg-background/60 text-muted-foreground"
      >
        <CardPreview item={item} />
        <Badge className="absolute left-2 top-2 capitalize">{typeLabel(item.type)}</Badge>
        <Badge
          variant={statusVariant(item.status)}
          className="absolute right-2 top-2 capitalize"
        >
          {item.status}
        </Badge>
      </button>
      <CardContent className="space-y-3 p-4">
        <div className="space-y-1">
          <p className="truncate text-sm font-semibold">{item.title}</p>
          <p className="text-xs text-muted-foreground">
            {item.project_name ?? "No project"} · {formatDate(item.created_at)}
          </p>
        </div>
        <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
          {item.prompt || item.description || "No description"}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onPreview}>
            {previewIcon(item.type)}
            Preview
          </Button>
          {item.download_url ? (
            <a
              href={assetUrl(item.download_url) ?? "#"}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              <Download className="h-4 w-4" />
              Download
            </a>
          ) : null}
          {canTrash ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onTrash}
              className="text-destructive hover:text-destructive"
              title="Move to trash (recoverable)"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
        {showActions ? (
          <div className="border-t border-border/60 pt-2">
            <MediaActions media={assetToMedia(item)} onAction={onAction} context={{ inAssets: true }} compact />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CardPreview({ item }: { item: LibraryItem }) {
  const thumbnail = assetUrl(item.thumbnail_url);
  if (thumbnail) {
    return (
      <img
        src={thumbnail}
        alt=""
        className="h-full w-full object-cover"
      />
    );
  }
  if (item.type === "copy" || item.type === "transcript") {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center">
        <FileText className="h-8 w-8" />
        <span className="line-clamp-4 text-sm">{item.description || item.prompt}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center gap-2">
      {previewIcon(item.type, "h-8 w-8")}
      <span className="text-sm capitalize">{typeLabel(item.type)}</span>
    </div>
  );
}

function PreviewModal({
  copied,
  item,
  onClose,
  onCopy,
}: {
  copied: boolean;
  item: LibraryItem;
  onClose: () => void;
  onCopy: () => void;
}) {
  const mediaUrl = assetUrl(item.asset_url);
  const imageUrl = assetUrl(item.thumbnail_url);
  const isVideo = item.type === "video" && mediaUrl;
  const isAudio = item.source_entity_type === "local_audio" && mediaUrl;
  const isImage = !isVideo && !isAudio && mediaUrl;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-border p-4">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap gap-2">
              <Badge className="capitalize">{typeLabel(item.type)}</Badge>
              <Badge variant={statusVariant(item.status)} className="capitalize">
                {item.status}
              </Badge>
            </div>
            <h2 className="truncate text-base font-semibold">{item.title}</h2>
            <p className="text-sm text-muted-foreground">
              {item.project_name ?? "No project"} · {formatDate(item.created_at)}
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="grid min-h-0 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-h-64 items-center justify-center rounded-md bg-background/60">
            {isAudio ? (
              <audio src={mediaUrl || undefined} controls className="w-full p-4" />
            ) : isVideo ? (
              <video
                src={mediaUrl}
                controls
                playsInline
                className="max-h-[62vh] w-full bg-black object-contain"
              />
            ) : isImage ? (
              <img
                src={mediaUrl}
                alt=""
                className="max-h-[62vh] w-full object-contain"
              />
            ) : imageUrl ? (
              <img
                src={imageUrl}
                alt=""
                className="max-h-[62vh] w-full object-contain"
              />
            ) : (
              <pre className="max-h-[62vh] w-full overflow-auto whitespace-pre-wrap p-4 text-sm text-foreground">
                {item.description || item.prompt || "No preview available"}
              </pre>
            )}
          </div>
          <aside className="space-y-4">
            <div>
              <p className="mb-1 text-xs text-muted-foreground">Prompt</p>
              <p className="text-sm">{item.prompt || "None"}</p>
            </div>
            <div>
              <p className="mb-1 text-xs text-muted-foreground">Description</p>
              <p className="whitespace-pre-wrap text-sm">
                {item.description || "None"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(item.type === "copy" || item.type === "transcript") && item.description ? (
                <Button type="button" variant="outline" size="sm" onClick={onCopy}>
                  {copied ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Clipboard className="h-4 w-4" />
                  )}
                  {copied ? "Copied" : "Copy text"}
                </Button>
              ) : null}
              {item.download_url ? (
                <a
                  href={assetUrl(item.download_url) ?? "#"}
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                >
                  <Download className="h-4 w-4" />
                  Download
                </a>
              ) : null}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  description,
  title,
}: {
  description: string;
  title: string;
}) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-center">
      <Archive className="h-7 w-7 text-muted-foreground" />
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

function previewIcon(type: LibraryItemType, className = "h-4 w-4") {
  if (type === "copy" || type === "transcript") return <FileText className={className} />;
  if (type === "video") return <Film className={className} />;
  if (type === "upload" || type === "processed_asset" || type === "image" || type === "scene") {
    return <ImageIcon className={className} />;
  }
  return <Package className={className} />;
}

function statusVariant(status: string): React.ComponentProps<typeof Badge>["variant"] {
  return (
    STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? "outline"
  );
}

function typeLabel(type: LibraryItemType) {
  return type.replace("_", " ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
