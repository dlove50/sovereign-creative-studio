"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart, Loader2, Search } from "lucide-react";

import { api } from "@/lib/api";
import manifest from "@/lib/public-avatars.generated.json";
import { cn } from "@/lib/utils";
import { AvatarPreview } from "./avatar-preview";

type PublicLook = { label: string; cover: string };
type PublicAvatar = { id: string; name: string; category: string; cover: string | null; looks: PublicLook[] };

const CATEGORIES = ["Professional", "Lifestyle", "UGC", "Community"] as const;
type Filter = "All" | (typeof CATEGORIES)[number] | "Favorites";
const FAVORITES_KEY = "scs_public_avatar_favorites";

const AVATARS: PublicAvatar[] = (Object.values(manifest) as PublicAvatar[]).filter((a) => a.cover);

function readFavorites(): string[] {
  try { return JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]") as string[]; } catch { return []; }
}

/** Fetch a bundled picture and upload it as an avatar (or a look inside an avatar). */
async function upload(cover: string, name: string, extra?: { groupId: string; label: string }) {
  const blob = await fetch(cover).then((r) => r.blob());
  const form = new FormData();
  form.append("file", new File([blob], `${name}.webp`, { type: "image/webp" }));
  form.append("name", extra ? `${name} - ${extra.label}` : name);
  if (extra) { form.append("group_id", extra.groupId); form.append("look_label", extra.label); }
  return api.createPhotoAvatar(form);
}

export function PublicAvatars({ onAdopted }: { onAdopted: () => Promise<void> }) {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("All");
  const [query, setQuery] = useState("");
  const [favorites, setFavorites] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [avatars, setAvatars] = useState(AVATARS);
  const [previewClips, setPreviewClips] = useState<Record<string, string>>({});
  const [alternateClips, setAlternateClips] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    const refresh = () => fetch("/sovereign-ui/public-avatars/catalog.json", { cache: "no-store" })
      .then(r => { if (!r.ok) throw new Error("Catalog unavailable"); return r.json(); })
      .then(data => setAvatars((Object.values(data) as PublicAvatar[]).filter(a => a.cover)))
      .catch(() => undefined);
    void refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const refresh = () => fetch("/sovereign-ui/public-avatars/previews/catalog.json", { cache: "no-store" })
      .then(r => r.ok ? r.json() : {}).then(setPreviewClips).catch(() => undefined);
    void refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => setFavorites(readFavorites()), []);

  useEffect(() => {
    const refresh = () => fetch("/sovereign-ui/public-avatars/previews/alternate-catalog.json", { cache: "no-store" })
      .then(r => r.ok ? r.json() : {}).then(setAlternateClips).catch(() => undefined);
    void refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return avatars.filter((a) =>
      (filter === "All" || (filter === "Favorites" ? favorites.includes(a.id) : a.category === filter)) &&
      (!q || `${a.name} ${a.category} ${a.looks.map((l) => l.label).join(" ")}`.toLowerCase().includes(q)));
  }, [filter, query, favorites, avatars]);

  function toggleFavorite(id: string) {
    setFavorites((cur) => {
      const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
      try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(next)); } catch { /* storage blocked: favorite lasts until reload */ }
      return next;
    });
  }

  async function adopt(a: PublicAvatar) {
    if (!a.cover) return;
    setBusy(a.id);
    setError(null);
    try {
      const base = await upload(a.cover, a.name);
      for (const look of a.looks) await upload(look.cover, a.name, { groupId: base.id, label: look.label });
      await onAdopted();
      router.push(`/avatars/${base.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The avatar could not be added.");
      setBusy(null);
    }
  }

  const chip = (c: Filter) => cn("rounded-full border px-4 py-1.5 text-sm font-semibold transition-colors", filter === c ? "border-primary bg-primary/15 text-foreground" : "border-border bg-card text-foreground hover:bg-raised");
  const selected = avatars.find(a => a.id === selectedId);
  if (selected) {
    const looks = [{ label: "Original", cover: selected.cover! }, ...selected.looks];
    return <div>
      <button type="button" onClick={() => setSelectedId(null)} className="mb-5 rounded-lg border border-border px-4 py-2 focus-visible:ring-2 focus-visible:ring-ring">Back to public avatars</button>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div><h2 className="text-2xl font-semibold">{selected.name}</h2><p className="text-sm text-muted-foreground">{looks.length} available looks</p></div>
        <button type="button" disabled={busy !== null} onClick={() => adopt(selected)} className="rounded-full bg-primary px-5 py-2 font-semibold text-primary-foreground disabled:opacity-50">{busy ? "Adding looks…" : "Add all looks to My avatars"}</button>
      </div>
      {error && <p role="alert" className="mb-4 text-destructive">{error}</p>}
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {looks.map(look => <li key={look.label}><AvatarPreview image={look.cover} video={look.cover === selected.cover ? previewClips[selected.id] : alternateClips[look.cover]} label={`${selected.name}: ${look.label}`} className="aspect-[4/5] w-full rounded-2xl" /><p className="mt-2 font-medium">{look.label}</p></li>)}
      </ul>
    </div>;
  }
  if (avatars.length === 0) {
    return <p className="py-14 text-center text-sm text-muted-foreground">The public avatar library has not been generated yet. Run tools/generate_public_avatar_library.py.</p>;
  }
  return (
    <div>
      <label className="flex items-center gap-2 rounded-full border border-border bg-card/60 px-4 py-2">
        <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" aria-label="Search public avatars" className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none" />
      </label>
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Category">
        {(["All", ...CATEGORIES, "Favorites"] as Filter[]).map((c) => <button key={c} type="button" aria-pressed={filter === c} onClick={() => setFilter(c)} className={chip(c)}>{c}</button>)}
      </div>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {shown.length === 0 ? <p className="py-14 text-center text-sm text-muted-foreground">{filter === "Favorites" ? "Tap the heart on an avatar to keep it here." : "No avatars match."}</p> : null}
      <ul className="mt-5 grid gap-x-5 gap-y-8 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((a) => (
          <li key={a.id} className="group">
            <button type="button" onClick={() => setSelectedId(a.id)} aria-label={`View ${a.name} looks`} className="block w-full text-left focus-visible:outline-none">
              <span className="grid aspect-[16/10] grid-cols-[2fr_1fr] gap-1 overflow-hidden rounded-2xl border border-border transition-colors group-hover:border-primary/60 group-focus-within:ring-2 group-focus-within:ring-ring">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <AvatarPreview image={a.cover} video={previewClips[a.id]} label={a.name} className="h-full w-full" />
                <span className="grid min-h-0 grid-rows-2 gap-1">
                  {[0, 1].map((i) => a.looks[i]
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <AvatarPreview key={i} image={a.looks[i].cover} video={alternateClips[a.looks[i].cover]} label={`${a.name}: ${a.looks[i].label}`} className="h-full min-h-0 w-full" />
                    : <span key={i} className="bg-raised" />)}
                </span>
              </span>
            </button>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-semibold text-foreground">{busy === a.id ? "Adding…" : a.name}</span>
              <span className="text-xs text-muted-foreground">{a.category}</span>
              {busy === a.id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              <button type="button" onClick={() => toggleFavorite(a.id)} aria-pressed={favorites.includes(a.id)} aria-label={favorites.includes(a.id) ? `Remove ${a.name} from favorites` : `Add ${a.name} to favorites`} className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-raised">
                <Heart className={cn("h-4 w-4", favorites.includes(a.id) ? "fill-rose-500 text-rose-500" : "text-muted-foreground")} />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
