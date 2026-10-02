"use client";

import { useState } from "react";
import { Loader2, Shirt } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { cn } from "@/lib/utils";

// Appended to every look so the edit changes clothes/scene, never the person.
const KEEP_IDENTITY =
  "Keep the exact same person, same face, same identity, same hairstyle. " +
  "Head-and-shoulders portrait, facing the camera, mouth closed, soft natural light, photorealistic.";

const LOOK_PRESETS = [
  { id: "office", label: "Business suit · office", prompt: "Change the outfit to a tailored navy business suit with a white shirt and place them in a bright modern office." },
  { id: "home", label: "Casual · living room", prompt: "Change the outfit to a cozy knit sweater and place them in a warm living room with plants." },
  { id: "outdoor", label: "Outdoor · city", prompt: "Change the outfit to a smart casual jacket and place them outdoors on a sunny city street." },
  { id: "studio", label: "Studio backdrop", prompt: "Keep the outfit and place them in front of a clean dark grey photo studio backdrop." },
];

const POLL_MS = 3000;

export function AvatarLookStudio({
  avatars,
  baseId,
  onBaseChange,
  onCreated,
}: {
  avatars: AvatarAsset[];
  baseId: string;
  onBaseChange: (id: string) => void;
  onCreated: () => Promise<void>;
}) {
  const photos = avatars.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
  const base = photos.find((a) => a.id === baseId);
  const [lookId, setLookId] = useState(LOOK_PRESETS[0].id);
  const [custom, setCustom] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = status !== null;

  async function createLook() {
    if (!base?.source_file_path) return;
    const preset = LOOK_PRESETS.find((l) => l.id === lookId);
    const change = custom.trim() || preset?.prompt || "";
    const label = custom.trim() ? "custom look" : preset?.label ?? "look";
    setError(null);
    setStatus("Creating the new look… (about 1–2 minutes)");
    try {
      let gen = await api.createGeneration({
        prompt: `${change} ${KEEP_IDENTITY}`,
        media_type: "image",
        provider: "local_comfyui",
        mode: "image_edit",
        source_image_url: base.source_file_path,
      });
      while (gen.status !== "completed" && gen.status !== "failed") {
        await new Promise((r) => setTimeout(r, POLL_MS));
        gen = await api.getGeneration(gen.id);
      }
      if (gen.status === "failed" || !gen.file_url) throw new Error(gen.error || "The look could not be created.");
      const form = new FormData();
      form.append("name", `${base.name} — ${label}`);
      form.append("source_url", gen.file_url);
      await api.createPhotoAvatar(form);
      await onCreated();
      setCustom("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The look could not be created.");
    } finally {
      setStatus(null);
    }
  }

  return (
    <section className="space-y-3 rounded-2xl border border-border bg-card p-5" data-testid="look-studio">
      <div className="flex items-center gap-2">
        <Shirt className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Create a new look</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Same person, new outfit or background. The new look is saved as another avatar you can animate.
      </p>
      {photos.length === 0 ? (
        <p className="text-sm text-muted-foreground">Add a photo avatar above first.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
          <div className="flex aspect-square items-center justify-center overflow-hidden rounded-xl border border-border bg-background/60">
            {base?.thumbnail_path && assetUrl(base.thumbnail_path) ? (
              <img src={assetUrl(base.thumbnail_path)!} alt={base.name} className="h-full w-full object-cover" />
            ) : (
              <span className="px-2 text-center text-xs text-muted-foreground">Pick a photo</span>
            )}
          </div>
          <div className="space-y-3">
            <select
              value={baseId}
              onChange={(e) => onBaseChange(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              aria-label="Photo to restyle"
            >
              <option value="">Select a photo avatar…</option>
              {photos.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <div className="flex flex-wrap gap-2">
              {LOOK_PRESETS.map((look) => (
                <button
                  key={look.id}
                  type="button"
                  onClick={() => { setLookId(look.id); setCustom(""); }}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition",
                    lookId === look.id && !custom.trim()
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border bg-background hover:bg-muted",
                  )}
                >
                  {look.label}
                </button>
              ))}
            </div>
            <input
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              maxLength={300}
              placeholder="Or describe your own: e.g. wearing a chef's apron in a bright kitchen"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={createLook}
              disabled={busy || !base}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shirt className="h-4 w-4" />}
              Create look
            </button>
            {status ? <p className="text-xs text-muted-foreground">{status}</p> : null}
            {error ? <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
          </div>
        </div>
      )}
    </section>
  );
}
