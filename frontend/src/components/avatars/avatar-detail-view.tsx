"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Camera, Loader2, PenLine, Plus, Repeat2, Sparkles, Trash2, UserRound, Video, X } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { useLookQueue } from "@/lib/look-queue";

// One-click edits from the "Edit look" panel; each makes a new look.
const QUICK_EDITS = {
  appearance: { label: "Enhanced", prompt: "Improve the photo quality: even, flattering studio lighting, sharp focus, natural skin texture, tidy hair. Keep the outfit and background." },
  angles: { label: "Three-quarter view", prompt: "Show the same person turned slightly to a three-quarter angle toward the camera, same outfit and background." },
};

function LookModal({
  look, baseId, onClose, onQuickEdit, onDelete,
}: {
  look: AvatarAsset;
  baseId: string;
  onClose: () => void;
  onQuickEdit: (kind: keyof typeof QUICK_EDITS) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const src = look.thumbnail_path ? assetUrl(look.thumbnail_path) : null;
  const caption = look.look_label || look.name;

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function run(kind: keyof typeof QUICK_EDITS) {
    setBusy(kind);
    try { await onQuickEdit(kind); onClose(); } finally { setBusy(null); }
  }

  const row = "flex w-full items-center gap-3 rounded-xl border border-border px-3 py-2.5 text-left hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label={caption} onClick={onClose}>
      <div className="grid max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card md:grid-cols-[1fr_300px]" onClick={(e) => e.stopPropagation()}>
        <div className="flex min-h-0 flex-col">
          <p className="border-b border-border px-5 py-4 font-semibold">{caption}</p>
          <div className="flex min-h-[320px] flex-1 items-center justify-center bg-background/60">
            {src ? <img src={src} alt={caption} className="max-h-[70vh] object-contain" /> : <Video className="h-8 w-8 text-muted-foreground" />}
          </div>
        </div>
        <div className="flex flex-col border-l border-border p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-semibold">Edit look</p>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-1 text-muted-foreground hover:bg-raised hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
          <div className="space-y-2">
            <button type="button" className={row} onClick={() => run("appearance")} disabled={busy !== null || !look.source_file_path}>
              {busy === "appearance" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4 text-muted-foreground" />}
              <span><span className="block text-sm font-medium">Appearance</span><span className="block text-xs text-muted-foreground">Cleaner light and sharper detail</span></span>
            </button>
            <button type="button" className={row} onClick={() => run("angles")} disabled={busy !== null || !look.source_file_path}>
              {busy === "angles" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4 text-muted-foreground" />}
              <span><span className="block text-sm font-medium">Camera angle</span><span className="block text-xs text-muted-foreground">A three-quarter side view</span></span>
            </button>
            <Link href={`/avatars/looks?avatar=${look.id}&custom=1`} className={row}>
              <PenLine className="h-4 w-4 text-muted-foreground" />
              <span><span className="block text-sm font-medium">Custom edit</span><span className="block text-xs text-muted-foreground">Describe the change yourself</span></span>
            </Link>
            <Link href={`/avatars/looks?avatar=${look.id}`} className={row}>
              <Repeat2 className="h-4 w-4 text-muted-foreground" />
              <span><span className="block text-sm font-medium">Remix into a scene</span><span className="block text-xs text-muted-foreground">Pick from scene templates</span></span>
            </Link>
          </div>
          <div className="mt-auto space-y-2 pt-6">
            <Link href={`/avatars/create?avatar=${look.id}`} className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
              <Video className="h-4 w-4" /> Use in a video
            </Link>
            {look.id !== baseId ? (
              <button
                type="button"
                onClick={async () => { if (window.confirm(`Delete the look “${caption}”? This can't be undone.`)) { setBusy("delete"); await onDelete(); } }}
                className="flex w-full items-center justify-center gap-2 rounded-full px-4 py-2 text-sm text-destructive hover:bg-raised"
              >
                <Trash2 className="h-4 w-4" /> Delete look
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AvatarDetailView({ avatarId }: { avatarId: string }) {
  const router = useRouter();
  const [avatars, setAvatars] = useState<AvatarAsset[] | null>(null);
  const [open, setOpen] = useState<AvatarAsset | null>(null);

  const refresh = useCallback(async () => setAvatars(await api.listAvatars()), []);
  const queue = useLookQueue(refresh);
  useEffect(() => { refresh().catch(() => setAvatars([])); }, [refresh]);

  const clicked = avatars?.find((a) => a.id === avatarId);
  const base = clicked?.group_id ? avatars?.find((a) => a.id === clicked.group_id) : clicked;
  if (avatars === null) return <p className="py-16 text-center text-sm text-muted-foreground">Loading…</p>;
  if (!base) {
    return (
      <div className="py-16 text-center">
        <p className="font-semibold">This avatar no longer exists.</p>
        <Link href="/avatars" className="mt-2 inline-block text-sm text-primary hover:underline">Back to avatars</Link>
      </div>
    );
  }
  const looks = [base, ...avatars.filter((a) => a.group_id === base.id)];
  const pendingHere = queue.pending.filter((p) => p.groupId === base.id);
  const photo = base.thumbnail_path ? assetUrl(base.thumbnail_path) : null;

  return (
    <div className="mx-auto max-w-[1120px]">
      <header className="flex flex-wrap items-center gap-4 border-b border-border pb-5">
        <Link href="/avatars" aria-label="Back to avatars" className="flex h-9 w-9 items-center justify-center rounded-full border border-border hover:bg-raised"><ArrowLeft className="h-4 w-4" /></Link>
        <span className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full bg-raised">
          {photo ? <img src={photo} alt="" className="h-full w-full object-cover" /> : <UserRound className="h-5 w-5 text-muted-foreground" />}
        </span>
        <h1 className="min-w-0 flex-1 truncate text-2xl font-extrabold tracking-[-0.02em]">{base.name}</h1>
        <Link href={`/avatars/create?avatar=${base.id}`} className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
          <Video className="h-4 w-4" /> Make a video
        </Link>
        <button
          type="button"
          onClick={async () => {
            if (!window.confirm(`Delete “${base.name}” and all ${looks.length} looks? This can't be undone.`)) return;
            await api.deleteAvatar(base.id);
            router.push("/avatars");
          }}
          aria-label="Delete avatar"
          className="flex h-9 w-9 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-raised hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </header>

      <p className="mb-3 mt-5 text-sm text-muted-foreground">{looks.length} {looks.length === 1 ? "look" : "looks"}</p>
      {queue.error ? (
        <p className="mb-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">
          {queue.error} <button type="button" className="ml-2 underline" onClick={queue.clearError}>Dismiss</button>
        </p>
      ) : null}
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <li>
          <Link href={`/avatars/looks?avatar=${base.id}`} className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-2xl border border-border bg-card/60 text-sm font-semibold hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground"><Plus className="h-5 w-5" /></span>
            Add looks
          </Link>
        </li>
        {pendingHere.map((p) => (
          <li key={p.generationId} className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-primary/50 bg-card/40 p-3 text-center">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="text-xs font-medium">{p.label}</span>
            <span className="text-[11px] text-muted-foreground">Creating… about 1–2 min</span>
          </li>
        ))}
        {looks.map((look) => {
          const src = look.thumbnail_path ? assetUrl(look.thumbnail_path) : null;
          const caption = look.id === base.id ? "Original photo" : look.look_label || look.name;
          return (
            <li key={look.id}>
              <button type="button" onClick={() => setOpen(look)} className="group relative block aspect-[4/3] w-full overflow-hidden rounded-2xl border border-border text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {src ? <img src={src} alt="" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" /> : <span className="flex h-full items-center justify-center bg-raised"><Video className="h-6 w-6 text-muted-foreground" /></span>}
                <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2.5 pt-8 text-xs font-medium text-white">{caption}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {open ? (
        <LookModal
          look={open}
          baseId={base.id}
          onClose={() => setOpen(null)}
          onQuickEdit={async (kind) => { await queue.start(open, [QUICK_EDITS[kind]]); }}
          onDelete={async () => { await api.deleteAvatar(open.id); setOpen(null); await refresh(); }}
        />
      ) : null}
    </div>
  );
}
