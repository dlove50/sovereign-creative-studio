"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
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

const STATUS_VARIANT = {
  uploaded: "muted",
  processing: "default",
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;
export function Overview({
  allItems,
  onPreview,
  workspace,
}: {
  allItems: LibraryItem[];
  onPreview: (item: LibraryItem) => void;
  workspace: ProjectWorkspace;
}) {
  const latestUpload = workspace.uploaded_assets[0];
  const latestScene = workspace.product_scenes[0];
  const latestCopy = workspace.copy_generations[0];
  const latestVideo = workspace.video_generations[0];

  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <QuickLink href="/upload" icon={Upload} label="Upload asset" />
        <QuickLink href="/product-scenes" icon={Sparkles} label="Generate scene" />
        <QuickLink href="/copy-studio" icon={PenLine} label="Generate copy" />
        <QuickLink href="/videos" icon={PlaySquare} label="Generate video" />
        <QuickLink
          href={`/assets-library?project_id=${workspace.id}`}
          icon={Layers}
          label="Project library"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <LatestCard title="Latest upload" item={latestUpload} onPreview={onPreview} />
        <LatestCard title="Latest scene" item={latestScene} onPreview={onPreview} />
        <LatestCard title="Latest copy" item={latestCopy} onPreview={onPreview} />
        <LatestCard title="Latest video" item={latestVideo} onPreview={onPreview} />
      </div>

      <BrandSummary brandKit={workspace.brand_kit} />

      <section>
        <h3 className="mb-3 text-sm font-semibold">Recent activity</h3>
        {allItems.length === 0 ? (
          <EmptyState message="No activity yet." />
        ) : (
          <div className="space-y-2">
            {allItems.slice(0, 8).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onPreview(item)}
                className="flex w-full items-center justify-between gap-4 rounded-md border border-border bg-card px-3 py-2 text-left hover:bg-muted/60"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {item.title}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {item.prompt || item.description || typeLabel(item.type)}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge variant={statusVariant(item.status)} className="capitalize">
                    {item.status}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(item.created_at)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function BrandSummary({ brandKit }: { brandKit: BrandKit }) {
  const rows = [
    ["Brand", brandKit.brand_name],
    ["Voice", brandKit.brand_voice],
    ["Audience", brandKit.target_audience],
    ["Colors", brandKit.primary_colors],
    ["Style", brandKit.style_keywords],
    ["Avoid", brandKit.negative_keywords],
  ].filter(([, value]) => value);

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Brand kit summary</h3>
        <Badge variant={rows.length ? "success" : "muted"}>
          {rows.length ? "Configured" : "Empty"}
        </Badge>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Add brand direction to guide scenes, copy, and campaign prompts.
        </p>
      ) : (
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="rounded-md border border-border bg-background/40 p-3"
            >
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="mt-1 line-clamp-2 text-sm">{value}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function BrandKitEditor({
  onSaved,
  projectId,
  value,
}: {
  onSaved: (brandKit: BrandKit) => void;
  projectId: string;
  value: BrandKit;
}) {
  const [form, setForm] = useState<BrandKit>(value);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setForm(value);
  }, [value]);

  function setField(field: keyof BrandKit, next: string) {
    setForm((current) => ({ ...current, [field]: next }));
  }

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.updateBrandKit(projectId, form);
      onSaved(saved);
      setMessage("Brand kit saved.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not save brand kit");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSave}
      className="space-y-5 rounded-lg border border-border bg-card p-5"
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Brand name"
          value={form.brand_name}
          onChange={(next) => setField("brand_name", next)}
          placeholder="Maison Atlas"
        />
        <TextField
          label="Target audience"
          value={form.target_audience}
          onChange={(next) => setField("target_audience", next)}
          placeholder="Urban professionals, premium shoppers"
        />
      </div>
      <TextAreaField
        label="Brand voice"
        value={form.brand_voice}
        onChange={(next) => setField("brand_voice", next)}
        placeholder="Luxury, refined, confident, editorial"
      />
      <TextAreaField
        label="Primary colors"
        value={form.primary_colors}
        onChange={(next) => setField("primary_colors", next)}
        placeholder="Black, gold, ivory"
      />
      <TextAreaField
        label="Style keywords"
        value={form.style_keywords}
        onChange={(next) => setField("style_keywords", next)}
        placeholder="Minimal, architectural, premium, cinematic"
      />
      <TextAreaField
        label="Negative keywords"
        value={form.negative_keywords}
        onChange={(next) => setField("negative_keywords", next)}
        placeholder="Cartoon, cheap, cluttered, distorted anatomy"
      />
      <TextAreaField
        label="Product positioning"
        value={form.product_positioning}
        onChange={(next) => setField("product_positioning", next)}
        placeholder="Premium everyday apparel for confident professionals"
      />
      <TextAreaField
        label="Campaign notes"
        value={form.campaign_notes}
        onChange={(next) => setField("campaign_notes", next)}
        placeholder="Focus on boutique retail, Milan-inspired editorial scenes"
      />
      {message ? (
        <p className="text-sm text-muted-foreground">{message}</p>
      ) : null}
      <Button type="submit" disabled={saving}>
        {saving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Save brand kit
      </Button>
    </form>
  );
}

export function TextField({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string | null;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

export function TextAreaField({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string | null;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Textarea
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-h-[86px]"
      />
    </div>
  );
}

function QuickLink({
  href,
  icon: Icon,
  label,
}: {
  href: string;
  icon: typeof Upload;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-3 text-sm font-medium hover:bg-muted"
    >
      <Icon className="h-4 w-4 text-primary" />
      {label}
      <ExternalLink className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
    </Link>
  );
}

function LatestCard({
  item,
  onPreview,
  title,
}: {
  item?: LibraryItem;
  onPreview: (item: LibraryItem) => void;
  title: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <p className="text-xs text-muted-foreground">{title}</p>
        {item ? (
          <>
            <button
              type="button"
              onClick={() => onPreview(item)}
              className="relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden rounded-md bg-background/60"
            >
              <ItemPreview item={item} />
            </button>
            <p className="line-clamp-2 text-sm font-medium">{item.title}</p>
          </>
        ) : (
          <div className="flex aspect-[4/3] items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
            Empty
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ItemGrid({
  empty,
  items,
  onPreview,
}: {
  empty: string;
  items: LibraryItem[];
  onPreview: (item: LibraryItem) => void;
}) {
  if (items.length === 0) return <EmptyState message={empty} />;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <WorkspaceCard key={item.id} item={item} onPreview={() => onPreview(item)} />
      ))}
    </div>
  );
}

function WorkspaceCard({
  item,
  onPreview,
}: {
  item: LibraryItem;
  onPreview: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onPreview}
        className="relative flex aspect-[4/3] w-full items-center justify-center bg-background/60 text-muted-foreground"
      >
        <ItemPreview item={item} />
        <Badge className="absolute left-2 top-2 capitalize">{typeLabel(item.type)}</Badge>
        <Badge
          variant={statusVariant(item.status)}
          className="absolute right-2 top-2 capitalize"
        >
          {item.status}
        </Badge>
      </button>
      <CardContent className="space-y-3 p-4">
        <div>
          <p className="truncate text-sm font-semibold">{item.title}</p>
          <p className="text-xs text-muted-foreground">{formatDate(item.created_at)}</p>
        </div>
        <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
          {item.prompt || item.description || "No description"}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onPreview}>
            {previewIcon(item)}
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
        </div>
      </CardContent>
    </Card>
  );
}

function ItemPreview({ item }: { item: LibraryItem }) {
  if (item.type === "video" && item.asset_url) {
    return <video src={`${assetUrl(item.asset_url)}#t=0.5`} muted preload="metadata" className="h-full w-full object-cover" />;
  }
  const thumbnail = assetUrl(item.thumbnail_url);
  if (thumbnail) {
    return <img src={thumbnail} alt="" className="h-full w-full object-cover" />;
  }
  if (item.type === "copy") {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center">
        <FileText className="h-8 w-8" />
        <span className="line-clamp-4 text-sm">{item.description || item.prompt}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center gap-2">
      {previewIcon(item, "h-8 w-8")}
      <span className="text-sm capitalize">{typeLabel(item.type)}</span>
    </div>
  );
}

export function PreviewModal({
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
  const isAudio = item.source_entity_type === "music_song" && mediaUrl;
  const isImage = !isVideo && !isAudio && mediaUrl;

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={item.title} className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
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
          <Button type="button" variant="outline" size="sm" aria-label="Close preview" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="grid min-h-0 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-h-64 items-center justify-center rounded-md bg-background/60">
            {isAudio ? <audio src={mediaUrl || undefined} controls className="w-full p-4" /> : isVideo ? (
              <video
                src={mediaUrl}
                controls
                playsInline
                className="max-h-[62vh] w-full bg-black object-contain"
              />
            ) : isImage ? (
              <img src={mediaUrl} alt="" className="max-h-[62vh] w-full object-contain" />
            ) : imageUrl ? (
              <img src={imageUrl} alt="" className="max-h-[62vh] w-full object-contain" />
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
              {item.type === "copy" && item.description ? (
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
    </div>, document.body
  );
}

export function CampaignBundleList({ bundles }: { bundles: CampaignBundle[] }) {
  if (bundles.length === 0) {
    return (
      <EmptyState message="No campaign bundles yet. Use the Campaign Builder to generate one." />
    );
  }
  return (
    <div className="space-y-3">
      {bundles.map((bundle) => (
        <div
          key={bundle.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-4"
        >
          <div className="min-w-0">
            <div className="mb-1 flex items-center gap-2">
              <span className="truncate text-sm font-semibold">{bundle.title}</span>
              <Badge variant="success" className="capitalize">
                {bundle.status}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {bundle.campaign_type.replace("_", " ")} · {formatDate(bundle.created_at)}
            </p>
          </div>
          <div className="flex gap-2 text-xs text-muted-foreground">
            <Badge variant="muted">{bundle.scene_ids.length} scenes</Badge>
            <Badge variant="muted">{bundle.copy_ids.length} copy</Badge>
            <Badge variant="muted">{bundle.video_ids.length} video</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-center">
      <PackagePlus className="h-7 w-7 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

function previewIcon(item: LibraryItem, className = "h-4 w-4") {
  if (item.type === "copy") return <FileText className={className} />;
  if (item.type === "video") return <Film className={className} />;
  return <ImageIcon className={className} />;
}

function statusVariant(status: string): React.ComponentProps<typeof Badge>["variant"] {
  return STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? "outline";
}

function typeLabel(type: string) {
  return type.replace("_", " ");
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
