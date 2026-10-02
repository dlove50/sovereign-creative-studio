"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUp, Check, History, Layers, Loader2, Search, UserRound, X } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import {
  LOOK_CATEGORIES, LOOK_TEMPLATES, MAX_CUSTOM_PACK, MIN_CUSTOM_PACK, isPack,
  type LookCategory, type LookTemplate, type LookVariant,
} from "@/lib/look-templates";
import { useLookQueue } from "@/lib/look-queue";
import { cn } from "@/lib/utils";

const CREDITS_PER_LOOK = 5;
type Filter = "All" | "Look Packs" | LookCategory;

function PackModal({
  template, onClose, onCreate,
}: {
  template: LookTemplate;
  onClose: () => void;
  onCreate: (variants: LookVariant[]) => Promise<void>;
}) {
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(template.variants.map((_, i) => i)));
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const picked = template.variants.filter((_, i) => chosen.has(i));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label={template.name} onClick={onClose}>
      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card md:grid-cols-[1fr_340px]" onClick={(e) => e.stopPropagation()}>
        <img src={template.cover} alt="" className="h-full max-h-[70vh] w-full object-cover" />
        <div className="flex flex-col p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-extrabold tracking-[-0.02em]">{template.name}</h2>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Layers className="h-3.5 w-3.5" /> {isPack(template) ? `Look Pack · ${template.variants.length} looks` : "1 look"}
              </p>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded-full p-1 text-muted-foreground hover:bg-raised hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
          <ul className="mt-4 space-y-2">
            {template.variants.map((v, i) => (
              <li key={v.label}>
                <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-border px-3 py-2.5 text-sm hover:bg-raised">
                  <input
                    type="checkbox"
                    checked={chosen.has(i)}
                    onChange={() => setChosen((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; })}
                    className="h-4 w-4 accent-[hsl(var(--primary))]"
                  />
                  {v.label}
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-auto flex items-center justify-between gap-3 pt-6">
            <span className="text-xs text-muted-foreground">{picked.length * CREDITS_PER_LOOK} credits · about {Math.max(1, picked.length * 1.5)} min</span>
            <button
              type="button"
              disabled={busy || picked.length === 0}
              onClick={async () => { setBusy(true); try { await onCreate(picked); } finally { setBusy(false); } }}
              className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Create {picked.length === 1 ? "look" : `${picked.length} looks`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LookStudioView() {
  const router = useRouter();
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [filter, setFilter] = useState<Filter>("All");
  const [query, setQuery] = useState("");
  const [customPack, setCustomPack] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [modal, setModal] = useState<LookTemplate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const refresh = useCallback(async () => setAvatars(await api.listAvatars()), []);
  const queue = useLookQueue(refresh);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setAvatarId(params.get("avatar") ?? "");
    if (params.get("custom")) promptRef.current?.focus();
    refresh().catch(() => setAvatars([]));
  }, [refresh]);

  const photos = avatars.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
  const avatar = photos.find((a) => a.id === avatarId) ?? null;
  const thumb = avatar?.thumbnail_path ? assetUrl(avatar.thumbnail_path) : null;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return LOOK_TEMPLATES.filter((t) =>
      (filter === "All" || (filter === "Look Packs" ? isPack(t) : t.category === filter)) &&
      (!q || `${t.name} ${t.category} ${t.variants.map((v) => v.label).join(" ")}`.toLowerCase().includes(q)),
    );
  }, [filter, query]);

  async function create(variants: LookVariant[]) {
    if (!avatar) { setError("Pick the avatar to restyle first."); return; }
    setError(null);
    setBusy(true);
    try {
      await queue.start(avatar, variants);
      router.push(`/avatars/${avatar.group_id || avatar.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The looks could not be started.");
    } finally {
      setBusy(false);
    }
  }

  const customVariants = LOOK_TEMPLATES.filter((t) => picked.includes(t.id)).map((t) => t.variants[0]);
  const chips: Filter[] = ["All", "Look Packs", ...LOOK_CATEGORIES];

  return (
    <div className="mx-auto max-w-[1120px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">What new look are you imagining?</h1>

      <section className="mt-7 rounded-3xl border border-border bg-card/70 p-4">
        <div className="flex gap-4">
          <div className="flex h-36 w-28 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-raised">
            {thumb ? <img src={thumb} alt={avatar?.name ?? ""} className="h-full w-full object-cover" /> : <UserRound className="h-6 w-6 text-muted-foreground" />}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <label htmlFor="look-prompt" className="text-xs font-medium text-muted-foreground">Describe how to change this look</label>
            <textarea
              id="look-prompt"
              ref={promptRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              maxLength={400}
              placeholder="e.g. wearing a chef's apron in a bright restaurant kitchen"
              className="mt-1.5 w-full resize-none bg-transparent text-[15px] placeholder:text-muted-foreground/70 focus:outline-none"
            />
            <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
              <select
                value={avatarId}
                onChange={(e) => setAvatarId(e.target.value)}
                aria-label="Avatar to restyle"
                className="h-9 max-w-[260px] rounded-full border border-border bg-background px-3 text-sm"
              >
                <option value="">Choose an avatar…</option>
                {photos.map((a) => (
                  <option key={a.id} value={a.id}>{a.look_label ? `${a.name}` : a.name}</option>
                ))}
              </select>
              <button
                type="button"
                aria-label="Create this look"
                disabled={busy || !prompt.trim() || !avatar}
                onClick={() => create([{ label: prompt.trim().slice(0, 60), prompt: prompt.trim() }])}
                className="ml-auto flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground disabled:bg-raised disabled:text-muted-foreground"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>
      </section>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-base font-semibold">Choose templates for your new looks</h2>
        {avatar ? (
          <Link href={`/avatars/${avatar.group_id || avatar.id}`} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs hover:bg-raised">
            <History className="h-3.5 w-3.5" /> Recent creations{queue.pending.length ? ` (${queue.pending.length} in progress)` : ""}
          </Link>
        ) : null}
      </div>
      <label className="mt-3 flex items-center gap-2 rounded-full border border-border bg-card/60 px-4 py-2">
        <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search templates" aria-label="Search templates" className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none" />
      </label>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter templates">
        {chips.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={filter === c}
            onClick={() => setFilter(c)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              filter === c ? "border-primary bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {c === "Look Packs" ? <Layers className="h-3 w-3" /> : null}
            {c}
          </button>
        ))}
      </div>

      {customPack ? (
        <div className="sticky top-2 z-20 mt-4 flex items-center justify-between rounded-2xl border border-primary/60 bg-card px-4 py-3 shadow-lg shadow-black/30">
          <span className="text-sm">Custom look pack: <strong>{picked.length}</strong> of {MIN_CUSTOM_PACK}–{MAX_CUSTOM_PACK} picked</span>
          <span className="flex gap-2">
            <button type="button" onClick={() => { setCustomPack(false); setPicked([]); }} className="rounded-full px-3 py-1.5 text-sm text-muted-foreground hover:bg-raised">Cancel</button>
            <button
              type="button"
              disabled={busy || picked.length < MIN_CUSTOM_PACK}
              onClick={() => create(customVariants)}
              className="rounded-full bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
            >
              Create {picked.length} looks
            </button>
          </span>
        </div>
      ) : null}

      <ul className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-3">
        {filter === "All" && !query ? (
          <li>
            <button
              type="button"
              onClick={() => setCustomPack((v) => !v)}
              aria-pressed={customPack}
              className={cn(
                "flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-2xl border bg-card/50 text-center hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                customPack ? "border-primary" : "border-border",
              )}
            >
              <span className="flex -space-x-3">
                {LOOK_TEMPLATES.slice(0, 3).map((t) => (
                  <img key={t.id} src={t.cover} alt="" className="h-12 w-12 rounded-xl border-2 border-card object-cover" />
                ))}
              </span>
              <span className="text-sm font-semibold">Custom look pack</span>
              <span className="text-xs text-muted-foreground">Choose {MIN_CUSTOM_PACK} to {MAX_CUSTOM_PACK} templates</span>
            </button>
          </li>
        ) : null}
        {shown.map((t) => {
          const selected = picked.includes(t.id);
          return (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => {
                  if (!customPack) { setModal(t); return; }
                  setPicked((p) => (selected ? p.filter((x) => x !== t.id) : p.length < MAX_CUSTOM_PACK ? [...p, t.id] : p));
                }}
                className={cn(
                  "group relative block aspect-[4/3] w-full overflow-hidden rounded-2xl border text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selected ? "border-primary ring-2 ring-primary" : "border-border",
                )}
              >
                <img src={t.cover} alt="" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
                <span className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-3 pt-10">
                  <span className="text-sm font-semibold text-white">{t.name}</span>
                  {isPack(t) ? <span className="rounded-full bg-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-950">Look Pack</span> : null}
                </span>
                {selected ? <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground"><Check className="h-4 w-4" /></span> : null}
              </button>
            </li>
          );
        })}
      </ul>
      {shown.length === 0 ? <p className="py-10 text-center text-sm text-muted-foreground">No templates match. Try another word or filter.</p> : null}

      {modal ? <PackModal template={modal} onClose={() => setModal(null)} onCreate={async (v) => { await create(v); setModal(null); }} /> : null}
    </div>
  );
}
