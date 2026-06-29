"use client";

import { useState } from "react";
import { Copy, X } from "lucide-react";

import { assetUrl } from "@/lib/api";
import type { MediaObject } from "@/lib/types/media";

interface Props {
  media: MediaObject | null;
  open: boolean;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex justify-between gap-3 border-b border-border/50 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[60%] truncate text-right font-medium">{value}</span>
    </div>
  );
}

export function MediaDetailsDrawer({ media, open, onClose }: Props) {
  const [copied, setCopied] = useState(false);
  if (!open || !media) return null;

  const m = media.metadata;
  const fullUrl = (() => {
    const u = assetUrl(media.storageUrl);
    if (!u) return null;
    return u.startsWith("http") || typeof window === "undefined" ? u : `${window.location.origin}${u}`;
  })();

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold">Details</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          {media.thumbnailUrl && media.type !== "video" && media.type !== "avatar_video" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={assetUrl(media.thumbnailUrl) ?? undefined} alt={media.filename ?? "preview"} className="w-full rounded-lg border border-border" />
          ) : null}

          <div>
            {fullUrl ? (
              <div className="space-y-1.5">
                <span className="text-xs font-medium text-muted-foreground">Storage URL</span>
                <div className="flex items-center gap-2">
                  <code className="flex-1 truncate rounded border border-border bg-background/60 px-2 py-1 text-xs">
                    {media.storageUrl}
                  </code>
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard.writeText(fullUrl).then(() => {
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 1500);
                      });
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div>
            <Row label="Filename" value={media.filename} />
            <Row label="Type" value={media.type} />
            <Row label="Source workflow" value={media.sourceWorkflow} />
            <Row label="Provider / model" value={media.provider} />
            <Row label="Generation mode" value={media.generationMode} />
            <Row label="Job ID" value={media.jobId} />
            <Row label="Credits charged" value={media.creditsCharged} />
            <Row label="Created" value={media.createdAt} />
            <Row label="Project" value={media.projectId} />
            <Row label="Owner" value={media.ownerId} />
            <Row label="Dimensions" value={m.width && m.height ? `${m.width}×${m.height}` : null} />
            <Row label="Duration" value={m.duration != null ? `${m.duration}s` : null} />
            <Row label="FPS" value={m.fps} />
            <Row label="Resolution" value={m.resolution} />
            <Row label="Language" value={m.language} />
          </div>

          {media.prompt ? (
            <div>
              <span className="text-xs font-medium text-muted-foreground">Prompt / brief</span>
              <p className="mt-1 rounded-md bg-muted/50 p-2 text-xs">{media.prompt}</p>
            </div>
          ) : null}

          {m.transcriptText ? (
            <div>
              <span className="text-xs font-medium text-muted-foreground">Transcript</span>
              <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/50 p-2 text-xs">
                {m.transcriptText}
              </p>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
