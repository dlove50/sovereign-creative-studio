"use client";

import { useState } from "react";
import { Clapperboard, ImageIcon, Loader2, Trash2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { Generation } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  pending: "muted",
  failed: "destructive",
} as const;

export function GenerationCard({ generation, onDeleted }: { generation: Generation; onDeleted?: (id: string) => void }) {
  const src = assetUrl(generation.file_url);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const inProgress = generation.status === "queued" || generation.status === "running";

  async function remove() {
    if (!window.confirm("Delete this picture? It moves to the trash, where an admin can restore it.")) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteGeneration(generation.id);
      onDeleted?.(generation.id);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "It could not be deleted.");
      setDeleting(false);
    }
  }

  return (
    <div className="group overflow-hidden rounded-lg border border-border bg-card transition-colors hover:border-primary/50">
      <div className={`relative aspect-square w-full bg-background/60${inProgress ? " job-shimmer" : ""}`}>
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={generation.prompt}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            {generation.media_type === "video" ? (
              <Clapperboard className="h-8 w-8" />
            ) : (
              <ImageIcon className="h-8 w-8" />
            )}
          </div>
        )}
        {!inProgress ? (
          <button
            type="button"
            onClick={remove}
            disabled={deleting}
            aria-label={`Delete ${generation.media_type}: ${generation.prompt.slice(0, 60)}`}
            className="absolute left-2 top-2 rounded-full bg-black/70 p-1.5 text-white opacity-0 transition hover:bg-destructive focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-100 [@media(hover:none)]:opacity-100"
          >
            {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          </button>
        ) : null}
        <Badge
          variant={STATUS_VARIANT[generation.status]}
          className="absolute right-2 top-2 capitalize"
        >
          {generation.status}
        </Badge>
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm text-foreground/90">
          {generation.prompt}
        </p>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="capitalize">{generation.media_type}</span>
          <span className={cn(generation.credits_cost > 0 && "text-primary")}>
            {generation.credits_cost > 0 ? `-${generation.credits_cost} cr` : "-"}
          </span>
        </div>
        {deleteError ? <p role="alert" className="text-xs text-destructive">{deleteError}</p> : null}
        {generation.status === "failed" && generation.error ? (
          <p className="line-clamp-2 text-xs text-destructive">
            {generation.error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
