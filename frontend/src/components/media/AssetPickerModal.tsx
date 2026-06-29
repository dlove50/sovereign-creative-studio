"use client";

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { LibraryItem } from "@/lib/types";
import type { MediaObject, MediaType } from "@/lib/types/media";
import { assetToMedia } from "@/lib/utils/mediaMapping";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (media: MediaObject) => void;
  filterTypes: MediaType[];
  title?: string;
}

const TYPE_MATCH: Record<MediaType, (item: LibraryItem) => boolean> = {
  image: (i) => ["image", "upload", "processed_asset", "scene"].includes(i.type),
  product_scene: (i) => i.type === "scene",
  video: (i) => i.type === "video",
  transcript: (i) => i.type === "transcript",
  audio: () => false,
  avatar_video: (i) => i.type === "video",
};

export function AssetPickerModal({ open, onClose, onSelect, filterTypes, title }: Props) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .listLibrary()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const matches = items.filter(
    (i) => i.status === "completed" && i.asset_url && filterTypes.some((t) => TYPE_MATCH[t]?.(i)),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold">{title ?? "Choose from Assets"}</h2>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : matches.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No matching media found. Generate or upload one first.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {matches.map((item) => {
                const thumb = assetUrl(item.thumbnail_url ?? item.asset_url);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      onSelect(assetToMedia(item));
                      onClose();
                    }}
                    className="group overflow-hidden rounded-lg border border-border bg-background/60 text-left hover:border-primary"
                  >
                    <div className="flex aspect-square items-center justify-center bg-muted">
                      {thumb && item.type !== "video" ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={thumb} alt={item.title} className="h-full w-full object-cover" />
                      ) : (
                        <span className="text-xs uppercase text-muted-foreground">{item.type}</span>
                      )}
                    </div>
                    <div className="p-2">
                      <p className="truncate text-xs font-medium">{item.title}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
