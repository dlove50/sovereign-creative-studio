"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { KEEP_IDENTITY, type LookVariant } from "@/lib/look-templates";

// Looks render as Qwen image-edit generations (about 1-2 minutes each). Pending
// ones are kept in localStorage so they still get filed under their avatar if the
// user leaves the page and comes back.
const STORAGE_KEY = "scs_pending_looks";
const POLL_MS = 4000;

export type PendingLook = {
  generationId: string;
  groupId: string;
  baseName: string;
  label: string;
  claimed?: boolean;
};

function read(): PendingLook[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]") as PendingLook[];
  } catch {
    return [];
  }
}

function write(items: PendingLook[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* storage blocked: pending looks still finish, they just won't survive a reload */
  }
}

/** Start looks for an avatar and file each finished one as a look in its group. */
export function useLookQueue(onLookCreated?: () => void) {
  const [pending, setPending] = useState<PendingLook[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setPending(read()), []);

  const start = useCallback(async (base: AvatarAsset, variants: LookVariant[]) => {
    if (!base.source_file_path) throw new Error("This avatar has no photo to restyle.");
    const groupId = base.group_id || base.id;
    const added: PendingLook[] = [];
    for (const v of variants) {
      const gen = await api.createGeneration({
        prompt: `${v.prompt} ${KEEP_IDENTITY}`,
        media_type: "image",
        provider: "local_comfyui",
        mode: "image_edit",
        source_image_url: base.source_file_path,
      });
      added.push({ generationId: gen.id, groupId, baseName: base.name, label: v.label });
    }
    const next = [...read(), ...added];
    write(next);
    setPending(next);
    return added.length;
  }, []);

  useEffect(() => {
    if (pending.length === 0) return;
    const timer = setInterval(async () => {
      for (const item of read()) {
        if (item.claimed) continue;
        let gen;
        try {
          gen = await api.getGeneration(item.generationId);
        } catch {
          continue;
        }
        if (gen.status !== "completed" && gen.status !== "failed") continue;
        // Claim before creating so a second tab can't file the same look twice.
        write(read().map((p) => (p.generationId === item.generationId ? { ...p, claimed: true } : p)));
        if (gen.status === "completed" && gen.file_url) {
          const form = new FormData();
          form.append("name", `${item.baseName} — ${item.label}`);
          form.append("source_url", gen.file_url);
          form.append("group_id", item.groupId);
          form.append("look_label", item.label);
          try {
            await api.createPhotoAvatar(form);
            onLookCreated?.();
          } catch (e) {
            setError(e instanceof Error ? e.message : "A finished look could not be saved.");
          }
        } else {
          setError(`“${item.label}” failed: ${gen.error || "the image edit did not finish."}`);
        }
        const rest = read().filter((p) => p.generationId !== item.generationId);
        write(rest);
        setPending(rest);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending.length, onLookCreated]);

  return { pending, start, error, clearError: () => setError(null) };
}
