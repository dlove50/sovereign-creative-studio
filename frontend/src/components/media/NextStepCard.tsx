"use client";

import { getActionsForMedia } from "@/lib/mediaCompatibility";
import type { ActionId, HandoffAction, MediaObject } from "@/lib/types/media";
import { ACTION_ICONS } from "@/components/media/actionIcons";

interface Props {
  media: MediaObject;
  onAction: (action: HandoffAction) => void;
  maxSteps?: number;
}

// Preferred suggestion order per media type (only "available" ones are shown).
const ORDER: Record<string, ActionId[]> = {
  image: ["animate_image", "edit_image", "product_scene", "download"],
  video: ["upscale_video", "transcribe_video", "download", "open_in_assets"],
  transcript: ["summarize_transcript", "send_to_copy_studio", "download_transcript", "copy_text"],
  product_scene: ["animate_scene", "download", "open_in_assets"],
  audio: ["use_for_avatar_voice", "download"],
  avatar_video: ["download", "open_in_assets"],
};

export function NextStepCard({ media, onAction, maxSteps = 4 }: Props) {
  if (!media || media.status === "failed") return null;

  const actions = getActionsForMedia(media);
  const order = ORDER[media.type] ?? [];
  const available = actions.filter((a) => a.status === "available");
  const ranked = order
    .map((id) => available.find((a) => a.id === id))
    .filter((a): a is NonNullable<typeof a> => Boolean(a))
    .slice(0, maxSteps);
  if (ranked.length === 0) return null;

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h3 className="mb-3 text-sm font-semibold">Next steps</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {ranked.map((a) => {
          const Icon = ACTION_ICONS[a.id];
          return (
            <button
              key={a.id}
              type="button"
              onClick={() =>
                onAction({
                  actionId: a.id,
                  media,
                  targetRoute: a.targetRoute,
                  targetMode: a.targetMode,
                  label: a.label,
                })
              }
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-left text-sm font-medium hover:bg-muted"
            >
              <Icon className="h-4 w-4 text-primary" />
              {a.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
