"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { LayoutGrid, List, Search, UserPlus } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AvatarMenu, FavoriteButton } from "./avatar-actions";
import { PublicAvatars } from "./public-avatars";
import { AvatarPreview } from "./avatar-preview";
import { CategoryAvatars } from "./category-avatars";
import { LOOK_CATEGORIES } from "@/lib/look-templates";

export type AvatarGroup = { base: AvatarAsset; looks: AvatarAsset[] };

export function groupAvatars(avatars: AvatarAsset[]): AvatarGroup[] {
  const bases = avatars.filter((a) => !a.group_id);
  return bases.map((base) => ({ base, looks: avatars.filter((a) => a.group_id === base.id) }));
}

function Thumb({ avatar, className }: { avatar?: AvatarAsset; className?: string }) {
  const src = avatar?.thumbnail_path ? assetUrl(avatar.thumbnail_path) : null;
  return <AvatarPreview image={src} video={avatar?.avatar_type === "video_avatar" ? assetUrl(avatar.source_file_path) : null} label={avatar?.look_label || avatar?.name || "Additional look"} className={className} />;
}

function GroupCard({ group, list, onChanged }: { group: AvatarGroup; list: boolean; onChanged: () => void }) {
  const [first, second] = group.looks;
  if (list) {
    return (
      <Link href={`/avatars/${group.base.id}`} className="flex items-center gap-4 rounded-2xl border border-border bg-card/60 p-3 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Thumb avatar={group.base} className="h-16 w-16 shrink-0 rounded-xl" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold text-foreground">{group.base.name}</span>
          <span className="text-sm text-muted-foreground">{group.looks.length + 1} looks</span>
        </span>
      </Link>
    );
  }
  return (
    <div className="group">
      <Link href={`/avatars/${group.base.id}`} className="block focus-visible:outline-none">
        <div className="grid aspect-[16/10] grid-cols-[2fr_1fr] gap-1 overflow-hidden rounded-2xl border border-border transition-colors group-hover:border-primary/60 focus-visible:ring-2 focus-visible:ring-ring">
          <Thumb avatar={group.base} className="h-full" />
          <div className="grid grid-rows-2 gap-1">
            <Thumb avatar={first} className="h-full" />
            <Thumb avatar={second} className="h-full" />
          </div>
        </div>
      </Link>
      <div className="mt-2.5 flex items-center gap-1">
        <Link href={`/avatars/${group.base.id}`} className="min-w-0 flex-1 truncate font-semibold text-foreground focus-visible:outline-none focus-visible:underline">{group.base.name}</Link>
        <span className="flex items-center opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 [&:has([aria-pressed=true])]:opacity-100">
          <AvatarMenu avatar={group.base} lookCount={group.looks.length + 1} onRenamed={onChanged} onDeleted={onChanged} />
          <FavoriteButton avatar={group.base} onChanged={onChanged} />
        </span>
      </div>
    </div>
  );
}

function NewAvatarButton() {
  return (
    <Link
      href="/avatars/new"
      className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <UserPlus className="h-4 w-4" />
      New avatar
    </Link>
  );
}

export function AvatarGalleryView() {
  const [avatars, setAvatars] = useState<AvatarAsset[] | null>(null);
  const [tab, setTab] = useState<"mine" | "public">("mine");
  const [query, setQuery] = useState("");
  const [list, setList] = useState(false);
  const [category, setCategory] = useState("All");

  const refresh = useCallback(async () => setAvatars(await api.listAvatars()), []);
  useEffect(() => {
    refresh().catch(() => setAvatars([]));
  }, [refresh]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return groupAvatars(avatars ?? []).filter((g) => (!q || g.base.name.toLowerCase().includes(q)) && (category !== "Look Packs" || g.looks.length >= 2));
  }, [avatars, query, category]);

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
        <div className="mb-2"><NewAvatarButton /></div>
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
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Avatar styles">
            {["All", "Look Packs", ...LOOK_CATEGORIES].map(c => <button key={c} type="button" aria-pressed={category === c} onClick={() => setCategory(c)} className={cn("rounded-full border px-3 py-1.5 text-sm focus-visible:ring-2 focus-visible:ring-ring", category === c ? "border-primary bg-primary/15 text-foreground" : "border-border bg-card text-foreground hover:bg-raised")}>{c}</button>)}
          </div>
          {category !== "All" && category !== "Look Packs" ? <CategoryAvatars category={category} query={query} /> : avatars === null ? (
            <p className="py-16 text-center text-sm text-muted-foreground">Loading your avatars…</p>
          ) : groups.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-base font-semibold">{query ? `No avatars match “${query}”.` : "No avatars yet."}</p>
              <p className="mt-1 text-sm text-muted-foreground">Use New avatar to upload a photo, or pick one from Public avatars.</p>
            </div>
          ) : (
            <ul className={cn("mt-6 grid gap-x-5 gap-y-7", list ? "grid-cols-1 md:grid-cols-2" : "sm:grid-cols-2")}>
              {groups.map((g) => (
                <li key={g.base.id}><GroupCard group={g} list={list} onChanged={() => void refresh()} /></li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="mt-6">
          <p className="mb-4 text-sm text-muted-foreground">Browse a presenter’s looks, then add the collection to My avatars.</p>
          <PublicAvatars onAdopted={refresh} />
        </div>
      )}
    </div>
  );
}
