// Ephemeral, in-memory handoff state (no localStorage, no persistence). Dependency
// -free store via React's useSyncExternalStore. MediaActions.onAction sets the
// handoff, the parent routes to the target page, and the target page consumes it
// once on mount (consume clears it). A query-param fallback is handled separately.

import { useSyncExternalStore } from "react";
import type { MediaObject, MediaType } from "@/lib/types/media";

export interface HandoffState {
  sourceUrl: string | null;
  sourceType: MediaType | null;
  mediaId: string | null;
  targetMode: string | null;
  targetRoute: string | null;
  prefill: Record<string, unknown> | null;
  projectId: string | null;
  originLabel: string | null;
  media: MediaObject | null;
}

export interface SetHandoffInput {
  sourceUrl?: string | null;
  sourceType?: MediaType | null;
  mediaId?: string | null;
  targetMode?: string | null;
  targetRoute?: string | null;
  prefill?: Record<string, unknown> | null;
  projectId?: string | null;
  originLabel?: string | null;
  media?: MediaObject | null;
}

let state: HandoffState | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function setHandoff(input: SetHandoffInput): void {
  state = {
    sourceUrl: input.sourceUrl ?? input.media?.storageUrl ?? null,
    sourceType: input.sourceType ?? input.media?.type ?? null,
    mediaId: input.mediaId ?? input.media?.mediaId ?? null,
    targetMode: input.targetMode ?? null,
    targetRoute: input.targetRoute ?? null,
    prefill: input.prefill ?? null,
    projectId: input.projectId ?? input.media?.projectId ?? null,
    originLabel: input.originLabel ?? null,
    media: input.media ?? null,
  };
  emit();
}

/** Read the pending handoff and clear it (read-once semantics). */
export function consumeHandoff(): HandoffState | null {
  const current = state;
  if (current) {
    state = null;
    emit();
  }
  return current;
}

export function peekHandoff(): HandoffState | null {
  return state;
}

export function clearHandoff(): void {
  if (state) {
    state = null;
    emit();
  }
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot(): HandoffState | null {
  return state;
}

/** Reactive read of the pending handoff (does not consume). */
export function useMediaHandoff(): HandoffState | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
