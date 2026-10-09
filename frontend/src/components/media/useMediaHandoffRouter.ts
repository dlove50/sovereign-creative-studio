"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import type { HandoffAction, MediaObject } from "@/lib/types/media";
import { setHandoff } from "@/lib/stores/useMediaHandoff";
import { runInlineMediaAction } from "@/components/media/MediaActions";

let handoffSequence = 0;

// One hook the pages use to turn a MediaActions/NextStepCard onAction() into the
// right effect: inline copy/download, open details drawer, or set the ephemeral
// handoff + navigate (with a query-param fallback the target re-validates).
export function useMediaHandoffRouter(originLabel: string) {
  const router = useRouter();
  const [detailsMedia, setDetailsMedia] = useState<MediaObject | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  function flash(msg: string | null) {
    if (!msg) return;
    setToast(msg);
    window.setTimeout(() => setToast(null), 1600);
  }

  function onAction(action: HandoffAction) {
    // Pure in-place actions (clipboard / download).
    const inline = runInlineMediaAction(action);
    if (inline) {
      flash(inline);
      return;
    }
    if (action.actionId === "view_details") {
      setDetailsMedia(action.media);
      return;
    }
    if (action.actionId === "open_in_assets") {
      router.push("/assets-library");
      return;
    }
    if (!action.targetRoute) return;

    // Routing handoff: set ephemeral state AND a query-param fallback.
    setHandoff({
      media: action.media,
      sourceUrl: action.media.storageUrl,
      sourceType: action.media.type,
      mediaId: action.media.mediaId,
      targetRoute: action.targetRoute,
      targetMode: action.targetMode,
      originLabel,
    });
    const params = new URLSearchParams();
    // A repeated action is a new handoff even when its mode/source are identical.
    params.set("handoff", `${Date.now()}-${++handoffSequence}`);
    if (action.targetMode) params.set("mode", action.targetMode);
    if (action.media.storageUrl) params.set("source", action.media.storageUrl);
    const qs = params.toString();
    router.push(qs ? `${action.targetRoute}?${qs}` : action.targetRoute);
  }

  return {
    onAction,
    detailsMedia,
    closeDetails: () => setDetailsMedia(null),
    toast,
  };
}
