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

function Overview({
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

function BrandKitEditor({
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

function TextField({
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

function TextAreaField({
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

function ItemGrid({
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
  const isImage = !isVideo && mediaUrl;

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
            {isVideo ? (
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
    </div>
  );
}

const EMPTY_BRIEF: CreativeBriefInput = {
  title: "",
  campaign_goal: "",
  target_channels: "",
  deliverables: "",
  key_messages: "",
  creative_direction: "",
  reference_notes: "",
  selected_asset_ids: [],
  status: "draft",
};

const BRIEF_STATUSES = ["draft", "in_review", "approved", "archived"];

function buildBriefSummary(brief: CreativeBrief): string {
  const lines = [`# ${brief.title}`, `Status: ${brief.status}`];
  const add = (label: string, value: string | null) => {
    if (value && value.trim()) lines.push(`\n${label}:\n${value.trim()}`);
  };
  add("Goal", brief.campaign_goal);
  add("Channels", brief.target_channels);
  add("Deliverables", brief.deliverables);
  add("Key messages", brief.key_messages);
  add("Creative direction", brief.creative_direction);
  add("Reference notes", brief.reference_notes);
  return lines.join("\n");
}

function CreativeBriefsTab({
  briefs,
  onChange,
  projectId,
}: {
  briefs: CreativeBrief[];
  onChange: (next: CreativeBrief[]) => void;
  projectId: string;
}) {
  const [mode, setMode] = useState<"list" | "edit">("list");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CreativeBriefInput>(EMPTY_BRIEF);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryOf, setSummaryOf] = useState<CreativeBrief | null>(null);
  const [copied, setCopied] = useState(false);

  function setField(field: keyof CreativeBriefInput, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function startNew() {
    setForm(EMPTY_BRIEF);
    setEditingId(null);
    setError(null);
    setMode("edit");
  }

  function startEdit(brief: CreativeBrief) {
    setForm({
      title: brief.title,
      campaign_goal: brief.campaign_goal ?? "",
      target_channels: brief.target_channels ?? "",
      deliverables: brief.deliverables ?? "",
      key_messages: brief.key_messages ?? "",
      creative_direction: brief.creative_direction ?? "",
      reference_notes: brief.reference_notes ?? "",
      selected_asset_ids: brief.selected_asset_ids,
      status: brief.status,
    });
    setEditingId(brief.id);
    setError(null);
    setMode("edit");
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        const updated = await api.updateBrief(projectId, editingId, form);
        onChange(briefs.map((b) => (b.id === updated.id ? updated : b)));
      } else {
        const created = await api.createBrief(projectId, form);
        onChange([created, ...briefs]);
      }
      setMode("list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save brief");
    } finally {
      setSaving(false);
    }
  }

  async function remove(brief: CreativeBrief) {
    if (!window.confirm(`Delete brief "${brief.title}"?`)) return;
    try {
      await api.deleteBrief(projectId, brief.id);
      onChange(briefs.filter((b) => b.id !== brief.id));
      if (summaryOf?.id === brief.id) setSummaryOf(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete brief");
    }
  }

  async function copySummary(brief: CreativeBrief) {
    await navigator.clipboard.writeText(buildBriefSummary(brief));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (mode === "edit") {
    return (
      <form
        onSubmit={save}
        className="space-y-5 rounded-lg border border-border bg-card p-5"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            {editingId ? "Edit brief" : "New brief"}
          </h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMode("list")}
          >
            <X className="h-4 w-4" />
            Cancel
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label="Title"
            value={form.title ?? ""}
            onChange={(next) => setField("title", next)}
            placeholder="Spring launch campaign"
          />
          <div className="space-y-2">
            <Label>Status</Label>
            <select
              value={form.status ?? "draft"}
              onChange={(event) => setField("status", event.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {BRIEF_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
        </div>
        <TextAreaField
          label="Campaign goal"
          value={form.campaign_goal ?? ""}
          onChange={(next) => setField("campaign_goal", next)}
          placeholder="What should this campaign achieve?"
        />
        <TextField
          label="Target channels"
          value={form.target_channels ?? ""}
          onChange={(next) => setField("target_channels", next)}
          placeholder="Instagram, TikTok, email"
        />
        <TextAreaField
          label="Deliverables"
          value={form.deliverables ?? ""}
          onChange={(next) => setField("deliverables", next)}
          placeholder="3 product scenes, 2 captions, 1 short video"
        />
        <TextAreaField
          label="Key messages"
          value={form.key_messages ?? ""}
          onChange={(next) => setField("key_messages", next)}
          placeholder="Premium, limited edition, sustainably made"
        />
        <TextAreaField
          label="Creative direction"
          value={form.creative_direction ?? ""}
          onChange={(next) => setField("creative_direction", next)}
          placeholder="Bright daylight, pastel palette, editorial framing"
        />
        <TextAreaField
          label="Reference notes"
          value={form.reference_notes ?? ""}
          onChange={(next) => setField("reference_notes", next)}
          placeholder="Links or notes for inspiration"
        />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" disabled={saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {editingId ? "Save brief" : "Create brief"}
        </Button>
      </form>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Plan a campaign before generating. A selected brief can be attached to
          scene and copy generation to keep outputs on-plan.
        </p>
        <Button type="button" onClick={startNew}>
          <Plus className="h-4 w-4" />
          New brief
        </Button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {briefs.length === 0 ? (
        <EmptyState message="No creative briefs yet. Create one to plan a campaign." />
      ) : (
        <div className="space-y-3">
          {briefs.map((brief) => (
            <div
              key={brief.id}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <ClipboardList className="h-4 w-4 text-primary" />
                    <span className="truncate text-sm font-semibold">
                      {brief.title}
                    </span>
                    <Badge
                      variant={brief.status === "approved" ? "success" : "muted"}
                      className="capitalize"
                    >
                      {brief.status.replace("_", " ")}
                    </Badge>
                  </div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {brief.campaign_goal || "No campaign goal yet."}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {brief.target_channels ? (
                      <span>Channels: {brief.target_channels}</span>
                    ) : null}
                    {brief.deliverables ? (
                      <span className="line-clamp-1">
                        Deliverables: {brief.deliverables}
                      </span>
                    ) : null}
                    <span>Updated {formatDate(brief.updated_at)}</span>
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setSummaryOf((current) =>
                        current?.id === brief.id ? null : brief,
                      )
                    }
                  >
                    <FileText className="h-4 w-4" />
                    Summary
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => startEdit(brief)}
                  >
                    <Pencil className="h-4 w-4" />
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => remove(brief)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              {summaryOf?.id === brief.id ? (
                <div className="mt-3 space-y-2 rounded-md border border-border bg-background/50 p-3">
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => copySummary(brief)}
                    >
                      {copied ? (
                        <Check className="h-4 w-4" />
                      ) : (
                        <Clipboard className="h-4 w-4" />
                      )}
                      {copied ? "Copied" : "Copy summary"}
                    </Button>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-foreground/90">
                    {buildBriefSummary(brief)}
                  </pre>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CampaignBundleList({ bundles }: { bundles: CampaignBundle[] }) {
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

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}
