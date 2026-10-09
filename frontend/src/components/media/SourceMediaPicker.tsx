"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, ImageIcon, Loader2, X } from "lucide-react";

import { assetUrl } from "@/lib/api";
import type { MediaObject, MediaType } from "@/lib/types/media";
import { emptyMediaMetadata } from "@/lib/types/media";
import { validateSourceUrl } from "@/lib/utils/validateSourceUrl";
import { AssetPickerModal } from "@/components/media/AssetPickerModal";
import { cn } from "@/lib/utils";

interface Props {
  acceptTypes: MediaType[];
  value: MediaObject | null;
  onChange: (media: MediaObject | null) => void;
  /** Origin label when the value was auto-attached via handoff (shows green badge). */
  autoAttachedFrom?: string | null;
  showAdvancedUrl?: boolean;
  label?: string;
  /** Optional uploader (the picker itself makes no API calls). */
  onUpload?: (file: File) => Promise<MediaObject>;
  /** Set when an auto-attached source does not match acceptTypes. */
  incompatibleWarning?: string | null;
}

function mediaFromUrl(url: string, acceptTypes: MediaType[]): MediaObject {
  const filename = url.split("/").filter(Boolean).pop() ?? null;
  const type: MediaType = acceptTypes[0] ?? "image";
  return {
    mediaId: url,
    type,
    filename,
    storageUrl: url,
    thumbnailUrl: type === "image" || type === "product_scene" ? url : null,
    sourceWorkflow: null,
    projectId: null,
    ownerId: null,
    createdAt: null,
    provider: null,
    generationMode: null,
    prompt: null,
    creditsCharged: null,
    jobId: null,
    status: "completed",
    metadata: emptyMediaMetadata(),
  };
}

export function SourceMediaPicker({
  acceptTypes,
  value,
  onChange,
  autoAttachedFrom = null,
  showAdvancedUrl = true,
  label = "Source media",
  onUpload,
  incompatibleWarning = null,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [urlMode, setUrlMode] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const accept = acceptTypes
    .flatMap((t) => (t === "video" || t === "avatar_video" ? ["video/*"] : t === "audio" ? ["audio/*"] : ["image/*"]))
    .join(",");

  function applyUrl() {
    const res = validateSourceUrl(urlValue, acceptTypes);
    if (!res.ok) {
      setError(res.error); // keep the user's input
      return;
    }
    setError(null);
    setUrlMode(false);
    onChange(mediaFromUrl(urlValue.trim(), acceptTypes));
  }

  async function handleFile(file: File | undefined) {
    if (!file || !onUpload) return;
    setUploading(true);
    setError(null);
    try {
      onChange(await onUpload(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>

      {incompatibleWarning ? (
        <p className="flex items-center gap-1.5 rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          <AlertCircle className="h-3.5 w-3.5" /> {incompatibleWarning}
        </p>
      ) : null}

      {value ? (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-3">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
            {value.thumbnailUrl && value.type !== "video" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={assetUrl(value.thumbnailUrl) ?? undefined} alt={value.filename ?? "source"} className="h-full w-full object-cover" />
            ) : (
              <ImageIcon className="h-5 w-5 text-muted-foreground" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{value.filename ?? "Attached source"}</p>
            <p className="text-xs text-muted-foreground">{value.type}</p>
            {autoAttachedFrom ? (
              <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
                <CheckCircle2 className="h-3 w-3" /> Auto-attached{` ${autoAttachedFrom}`}
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={() => setPickerOpen(true)} className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted">
              Change
            </button>
            <button type="button" onClick={() => onChange(null)} className="rounded-md border border-border px-2 py-1 text-xs text-destructive hover:bg-muted">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-4">
          <p className="mb-3 text-sm text-muted-foreground">No source attached yet.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setPickerOpen(true)} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
              Choose from Assets
            </button>
            {onUpload ? (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted disabled:opacity-60"
              >
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Upload File
              </button>
            ) : null}
            {showAdvancedUrl ? (
              <button type="button" onClick={() => setUrlMode((v) => !v)} className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted">
                Paste URL (Advanced)
              </button>
            ) : null}
          </div>

          {urlMode ? (
            <div className="mt-3 flex gap-2">
              <input
                value={urlValue}
                onChange={(e) => setUrlValue(e.target.value)}
                placeholder="/storage/generated/abc.png"
                className="flex h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <button type="button" onClick={applyUrl} className="rounded-md border border-border px-3 text-sm font-medium hover:bg-muted">
                Attach
              </button>
            </div>
          ) : null}
        </div>
      )}

      {error ? (
        <p className="flex items-center gap-1.5 rounded-md bg-destructive/15 px-3 py-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5" /> {error}
        </p>
      ) : null}

      <input
        ref={fileRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      <AssetPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(m) => {
          setError(null);
          onChange(m);
        }}
        filterTypes={acceptTypes}
        title={`Choose ${acceptTypes.join(" / ")}`}
      />
    </div>
  );
}
