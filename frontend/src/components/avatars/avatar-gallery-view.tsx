"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ImagePlus, LayoutGrid, List, Loader2, Search, Sparkles, UserPlus, UserRound, Video } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { LOOK_TEMPLATES } from "@/lib/look-templates";
import { cn } from "@/lib/utils";

export type AvatarGroup = { base: AvatarAsset; looks: AvatarAsset[] };

export function groupAvatars(avatars: AvatarAsset[]): AvatarGroup[] {
  const bases = avatars.filter((a) => !a.group_id);
  return bases.map((base) => ({ base, looks: avatars.filter((a) => a.group_id === base.id) }));
}

function Thumb({ avatar, className }: { avatar?: AvatarAsset; className?: string }) {
  const src = avatar?.thumbnail_path ? assetUrl(avatar.thumbnail_path) : null;
  return (
    <div className={cn("flex items-center justify-center overflow-hidden bg-raised", className)}>
      {src ? (
        <img src={src} alt="" className="h-full w-full object-cover" />
      ) : avatar?.avatar_type === "video_avatar" ? (
        <Video className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      ) : (
        <UserRound className="h-5 w-5 text-muted-foreground/60" aria-hidden="true" />
      )}
    </div>
  );
}

function GroupCard({ group, list }: { group: AvatarGroup; list: boolean }) {
  const [first, second] = group.looks;
  if (list) {
    return (
      <Link href={`/avatars/${group.base.id}`} className="flex items-center gap-4 rounded-2xl border border-border bg-card/60 p-3 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Thumb avatar={group.base} className="h-16 w-16 shrink-0 rounded-xl" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold">{group.base.name}</span>
          <span className="text-sm text-muted-foreground">{group.looks.length + 1} looks</span>
        </span>
      </Link>
    );
  }
  return (
    <Link href={`/avatars/${group.base.id}`} className="group block focus-visible:outline-none">
      <div className="grid aspect-[16/10] grid-cols-[2fr_1fr] gap-1 overflow-hidden rounded-2xl border border-border transition-colors group-hover:border-primary/60 group-focus-visible:ring-2 group-focus-visible:ring-ring">
        <Thumb avatar={group.base} className="h-full" />
        <div className="grid grid-rows-2 gap-1">
          <Thumb avatar={first} className="h-full" />
          <Thumb avatar={second} className="h-full" />
        </div>
      </div>
      <p className="mt-2.5 truncate font-semibold">{group.base.name}</p>
    </Link>
  );
}

function NewAvatarMenu({ onCreated }: { onCreated: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [designing, setDesigning] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const router = useRouter();

  async function upload(kind: "photo" | "video", file: File) {
    setBusy(kind);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", file.name.replace(/\.[^.]+$/, ""));
      const created = kind === "photo" ? await api.createPhotoAvatar(form) : await api.createVideoAvatar(form);
      await onCreated();
      router.push(`/avatars/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(null);
      setOpen(false);
    }
  }

  async function design() {
    if (!prompt.trim()) return;
    setBusy("design");
    setError(null);
    try {
      let gen = await api.createGeneration({
        prompt: `Waist-up portrait photo of ${prompt.trim()}, facing the camera, mouth closed, soft natural light, photorealistic`,
        media_type: "image",
        provider: "local_comfyui",
        mode: "text_to_image",
        quality_preset: "krea2_turbo_fp8",
      });
      while (gen.status !== "completed" && gen.status !== "failed") {
        await new Promise((r) => setTimeout(r, 3000));
        gen = await api.getGeneration(gen.id);
      }
      if (gen.status === "failed" || !gen.file_url) throw new Error(gen.error || "The avatar could not be designed.");
      const form = new FormData();
      form.append("name", prompt.trim().slice(0, 60));
      form.append("source_url", gen.file_url);
      const created = await api.createPhotoAvatar(form);
      await onCreated();
      router.push(`/avatars/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The avatar could not be designed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
        New avatar
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-72 rounded-2xl border border-border bg-card p-2 shadow-2xl shadow-black/40">
          <button type="button" onClick={() => photoInput.current?.click()} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-raised">
            <ImagePlus className="h-4 w-4 text-muted-foreground" /> Upload a photo
          </button>
          <button type="button" onClick={() => videoInput.current?.click()} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-raised">
            <Video className="h-4 w-4 text-muted-foreground" /> Upload a video of yourself
          </button>
          <button type="button" onClick={() => setDesigning((v) => !v)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-raised">
            <Sparkles className="h-4 w-4 text-muted-foreground" /> Design with AI
          </button>
          {designing ? (
            <div className="space-y-2 px-2 pb-2 pt-1">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                maxLength={300}
                placeholder="e.g. a friendly woman in her 40s with short grey hair and a denim jacket"
                className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <button
                type="button"
                onClick={design}
                disabled={busy === "design" || !prompt.trim()}
                className="w-full rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
              >
                {busy === "design" ? "Designing… (about 10 seconds)" : "Design avatar"}
              </button>
            </div>
          ) : null}
          {error ? <p className="px-3 pb-2 text-xs text-destructive">{error}</p> : null}
        </div>
      ) : null}
      <input ref={photoInput} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && upload("photo", e.target.files[0])} />
      <input ref={videoInput} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden" onChange={(e) => e.target.files?.[0] && upload("video", e.target.files[0])} />
    </div>
  );
}

function PublicAvatars({ onAdopted }: { onAdopted: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const router = useRouter();
  async function adopt(id: string, name: string, cover: string) {
    setBusy(id);
    try {
      const blob = await fetch(cover).then((r) => r.blob());
      const form = new FormData();
      form.append("file", new File([blob], `${id}.webp`, { type: "image/webp" }));
      form.append("name", name);
      const created = await api.createPhotoAvatar(form);
      await onAdopted();
      router.push(`/avatars/${created.id}`);
    } finally {
      setBusy(null);
    }
  }
  return (
    <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {LOOK_TEMPLATES.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            onClick={() => adopt(t.id, `${t.name} presenter`, t.cover)}
            disabled={busy !== null}
            className="group relative block w-full overflow-hidden rounded-2xl border border-border text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <img src={t.cover} alt="" className="aspect-[3/4] w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
            <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-3 text-sm font-semibold text-white">
              {busy === t.id ? "Adding…" : `${t.name} presenter`}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function AvatarGalleryView() {
  const [avatars, setAvatars] = useState<AvatarAsset[] | null>(null);
  const [tab, setTab] = useState<"mine" | "public">("mine");
  const [query, setQuery] = useState("");
  const [list, setList] = useState(false);

  const refresh = useCallback(async () => setAvatars(await api.listAvatars()), []);
  useEffect(() => {
    refresh().catch(() => setAvatars([]));
  }, [refresh]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return groupAvatars(avatars ?? []).filter((g) => !q || g.base.name.toLowerCase().includes(q));
  }, [avatars, query]);

  return (
    <div className="mx-auto max-w-[1120px]">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border">
        <div role="tablist" aria-label="Avatar collections" className="flex gap-6">
          {(["mine", "public"] as const).map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={cn(
                "-mb-px border-b-[3px] pb-2.5 text-[15px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                tab === id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {id === "mine" ? "My avatars" : "Public avatars"}
            </button>
          ))}
        </div>
        <div className="mb-2"><NewAvatarMenu onCreated={refresh} /></div>
      </div>

      {tab === "mine" ? (
        <>
          <div className="mt-5 flex items-center gap-3">
            <label className="flex flex-1 items-center gap-2 rounded-full border border-border bg-card/60 px-4 py-2">
              <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search avatars" className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none" />
            </label>
            <div className="flex rounded-full border border-border bg-card/60 p-1" role="group" aria-label="Layout">
              <button type="button" onClick={() => setList(false)} aria-pressed={!list} className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-xs", !list ? "bg-raised text-foreground" : "text-muted-foreground")}>
                <LayoutGrid className="h-3.5 w-3.5" /> Grid
              </button>
              <button type="button" onClick={() => setList(true)} aria-pressed={list} className={cn("flex items-center gap-1.5 rounded-full px-3 py-1 text-xs", list ? "bg-raised text-foreground" : "text-muted-foreground")}>
                <List className="h-3.5 w-3.5" /> List
              </button>
            </div>
          </div>
          {avatars === null ? (
            <p className="py-16 text-center text-sm text-muted-foreground">Loading your avatars…</p>
          ) : groups.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-base font-semibold">{query ? `No avatars match “${query}”.` : "No avatars yet."}</p>
              <p className="mt-1 text-sm text-muted-foreground">Use New avatar to upload a photo, or pick one from Public avatars.</p>
            </div>
          ) : (
            <ul className={cn("mt-6 grid gap-x-5 gap-y-7", list ? "grid-cols-1 md:grid-cols-2" : "sm:grid-cols-2")}>
              {groups.map((g) => (
                <li key={g.base.id}><GroupCard group={g} list={list} /></li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="mt-6">
          <p className="mb-4 text-sm text-muted-foreground">AI-generated presenters you can use as your own. Picking one adds a copy to My avatars.</p>
          <PublicAvatars onAdopted={refresh} />
        </div>
      )}
    </div>
  );
}
