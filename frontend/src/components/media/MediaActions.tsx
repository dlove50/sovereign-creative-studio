"use client";

import { assetUrl } from "@/lib/api";
import { getActionsForMedia, type CompatibilityContext } from "@/lib/mediaCompatibility";
import type { ActionDef, HandoffAction, MediaObject } from "@/lib/types/media";
import { cn } from "@/lib/utils";
import { ACTION_ICONS, STATUS_LABEL } from "@/components/media/actionIcons";

interface Props {
  media: MediaObject;
  context?: CompatibilityContext;
  onAction: (action: HandoffAction) => void;
  primaryAction?: string | null;
  compact?: boolean;
  disabledActions?: string[];
}

/** Renders the prominent primary action + smaller secondary actions for a media
 *  item. Pure: it never calls an API or navigates — it only emits onAction(). */
export function MediaActions({
  media,
  context = {},
  onAction,
  primaryAction,
  compact = false,
  disabledActions = [],
}: Props) {
  if (!media || media.status === "failed") return null;

  const actions = getActionsForMedia(media, context).filter((a) => !disabledActions.includes(a.id));
  if (actions.length === 0) return null;

  let primary = actions.find((a) => a.primary) ?? null;
  if (primaryAction) primary = actions.find((a) => a.id === primaryAction) ?? primary;
  const secondary = actions.filter((a) => a.id !== primary?.id);

  function emit(action: ActionDef) {
    if (action.status !== "available") return;
    onAction({
      actionId: action.id,
      media,
      targetRoute: action.targetRoute,
      targetMode: action.targetMode,
      label: action.label,
    });
  }

  return (
    <div className={cn("space-y-3", compact && "space-y-2")}>
      {primary && primary.status === "available" ? (
        <PrimaryButton action={primary} onClick={() => emit(primary!)} compact={compact} />
      ) : null}
      <div className="flex flex-wrap gap-2">
        {secondary.map((a) => (
          <SecondaryButton key={a.id} action={a} onClick={() => emit(a)} />
        ))}
      </div>
    </div>
  );
}

function PrimaryButton({ action, onClick, compact }: { action: ActionDef; onClick: () => void; compact: boolean }) {
  const Icon = ACTION_ICONS[action.id];
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md bg-primary font-medium text-primary-foreground hover:opacity-90",
        compact ? "px-3 py-1.5 text-sm" : "w-full px-4 py-2.5 text-sm",
      )}
    >
      <Icon className="h-4 w-4" />
      {action.label}
    </button>
  );
}

function SecondaryButton({ action, onClick }: { action: ActionDef; onClick: () => void }) {
  const Icon = ACTION_ICONS[action.id];
  const disabled = action.status !== "available";
  const statusLabel = STATUS_LABEL[action.status];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={disabled ? statusLabel : undefined}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors",
        disabled
          ? "cursor-not-allowed border-border/60 text-muted-foreground opacity-60"
          : "border-border text-foreground hover:bg-muted",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {action.label}
      {disabled && statusLabel ? (
        <span className="ml-1 rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-400">
          {statusLabel}
        </span>
      ) : null}
    </button>
  );
}

// --- shared page-side handler helpers (so pages don't reimplement inline ops) --
export function runInlineMediaAction(action: HandoffAction): string | null {
  const { actionId, media } = action;
  if (actionId === "copy_url") {
    const u = assetUrl(media.storageUrl);
    const full = u && !u.startsWith("http") && typeof window !== "undefined" ? `${window.location.origin}${u}` : u;
    if (full) void navigator.clipboard.writeText(full);
    return "Copied URL";
  }
  if (actionId === "copy_text") {
    const text = media.metadata.transcriptText ?? "";
    if (text) void navigator.clipboard.writeText(text);
    return "Copied transcript text";
  }
  if (actionId === "download" || actionId === "download_transcript") {
    const url = assetUrl(media.storageUrl);
    if (url) {
      const a = document.createElement("a");
      a.href = url;
      a.download = media.filename ?? "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    return "Download started";
  }
  return null;
}
