"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AvatarPreview } from "./avatar-preview";

type CategoryAvatar = { id: string; name: string; category: string; description: string; cover: string | null; preview?: string; status: string; looks: { label: string; cover: string; preview?: string }[] };

export function CategoryAvatars({ category, query }: { category: string; query: string }) {
  const [avatars, setAvatars] = useState<CategoryAvatar[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const router = useRouter();
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const res = await fetch("/sovereign-ui/category-avatars/catalog.json", { cache: "no-store" });
        if (!res.ok) throw new Error("The category library is being prepared.");
        const data = await res.json();
        if (active) { setAvatars(data.avatars); setError(null); }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Library unavailable."); }
    };
    void refresh(); const timer = setInterval(refresh, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const ready = avatars.filter(a => a.category === category && a.cover);
  const shown = ready.filter(a => `${a.name} ${a.description}`.toLowerCase().includes(query.toLowerCase()));
  async function adopt(a: CategoryAvatar) {
    if (!a.cover) return;
    setBusy(a.id);
    try {
      const res = await fetch(a.cover); if (!res.ok) throw new Error("Image unavailable. Try again after the library refreshes.");
      const form = new FormData(); form.append("file", new File([await res.blob()], `${a.id}.webp`, { type: "image/webp" })); form.append("name", `${a.name} — ${a.description}`);
      const avatar = await api.createPhotoAvatar(form); router.push(`/avatars/${avatar.id}`);
    } catch(e) { setError(e instanceof Error ? e.message : "Could not add avatar."); setBusy(null); }
  }
  return <section className="mt-5" aria-label={`${category} avatar library`}>
    <p className="text-sm text-muted-foreground">{ready.length} of 20 {category.toLowerCase()} styles ready. New renders appear automatically.</p>
    {error ? <p role="status" className="mt-3 text-sm text-muted-foreground">{error}</p> : null}
    {!shown.length ? <p className="py-12 text-center text-sm text-muted-foreground">{ready.length ? "No styles match your search." : `The ${category.toLowerCase()} collection is queued for rendering.`}</p> : null}
    <ul className="mt-5 grid gap-x-5 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">{shown.map(a => <li key={a.id}>
      <button onClick={() => void adopt(a)} disabled={busy !== null} className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-2xl" aria-label={`Use ${a.name}`}>
        <AvatarPreview image={a.cover} video={a.preview} label={a.description} className="aspect-[4/5] rounded-2xl" />
        <span className="mt-2 block font-semibold text-foreground">{busy === a.id ? "Adding…" : a.name}</span>
        <span className="mt-1 block text-sm text-muted-foreground">{a.description}</span>
      </button>
    </li>)}</ul>
  </section>;
}
