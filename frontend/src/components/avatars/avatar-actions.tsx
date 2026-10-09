"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, Copy, Heart, MoreHorizontal, Pause, Pencil, Play, Replace, Mic, Trash2, Video, X } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, VoiceOption } from "@/lib/types";
import { cleanVoiceLabel } from "@/lib/voice-meta";
import { cn } from "@/lib/utils";
import { VoiceStep } from "./new/voice-step";

/** Closes a popover when the user clicks elsewhere or presses Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, close]);
  return ref;
}

export function FavoriteButton({ avatar, onChanged, className }: { avatar: AvatarAsset; onChanged: (a: AvatarAsset) => void; className?: string }) {
  const [busy, setBusy] = useState(false);
  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    try { onChanged(await api.updateAvatar(avatar.id, { is_favorite: !avatar.is_favorite })); } finally { setBusy(false); }
  }
  return (
    <button type="button" onClick={toggle} disabled={busy} aria-pressed={!!avatar.is_favorite} aria-label={avatar.is_favorite ? "Remove from favorites" : "Add to favorites"}
      className={cn("flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-foreground", className)}>
      <Heart className={cn("h-4 w-4", avatar.is_favorite && "fill-rose-500 text-rose-500")} />
    </button>
  );
}

export function AvatarMenu({ avatar, lookCount, onRenamed, onDeleted, className }: {
  avatar: AvatarAsset; lookCount: number; onRenamed: (a: AvatarAsset) => void; onDeleted: () => void; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));

  async function rename() {
    setOpen(false);
    const name = window.prompt("Rename avatar", avatar.name)?.trim();
    if (name && name !== avatar.name) onRenamed(await api.updateAvatar(avatar.id, { name }));
  }
  async function remove() {
    setOpen(false);
    if (!await confirmDialog(`Delete “${avatar.name}” and its ${lookCount} ${lookCount === 1 ? "look" : "looks"}? This can't be undone.`)) return;
    await api.deleteAvatar(avatar.id);
    onDeleted();
  }
  async function copyId() {
    try { await navigator.clipboard.writeText(avatar.id); setCopied(true); setTimeout(() => { setCopied(false); setOpen(false); }, 900); } catch { setOpen(false); }
  }
  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-raised";
  return (
    <div ref={ref} className={cn("relative", className)}>
      <button type="button" aria-label="More options" aria-expanded={open} onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v); }}
        className="flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-foreground">
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-56 rounded-xl border border-border bg-card p-1.5 shadow-2xl shadow-black/40" onClick={(e) => e.stopPropagation()}>
          <button role="menuitem" type="button" onClick={rename} className={item}><Pencil className="h-4 w-4 text-muted-foreground" /> Edit name</button>
          <Link role="menuitem" href={`/avatars/create?avatar=${avatar.id}`} className={item}><Video className="h-4 w-4 text-muted-foreground" /> Make a video</Link>
          <button role="menuitem" type="button" onClick={copyId} className={item}>{copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4 text-muted-foreground" />} {copied ? "Copied" : "Copy avatar ID"}</button>
          <button role="menuitem" type="button" onClick={remove} className={cn(item, "text-destructive")}><Trash2 className="h-4 w-4" /> Delete</button>
        </div>
      ) : null}
    </div>
  );
}

export function VoicePill({ avatar, onChanged }: { avatar: AvatarAsset; onChanged: (a: AvatarAsset) => void }) {
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [menu, setMenu] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const ref = useDismiss(menu, () => setMenu(false));

  useEffect(() => { api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([])); return () => audio.current?.pause(); }, []);
  const current = voices.find((v) => v.id === avatar.default_voice_id);
  const label = current ? cleanVoiceLabel(current) : avatar.default_voice_id ? avatar.default_voice_id.replace("vibevoice:", "") : "Choose a voice";

  async function play() {
    if (!avatar.default_voice_id) { setSwitching(true); return; }
    if (playing) { audio.current?.pause(); setPlaying(false); return; }
    setError(null);
    try {
      const { url } = await api.voicePreview(avatar.default_voice_id);
      const el = new Audio(assetUrl(url) ?? undefined);
      el.onended = () => setPlaying(false);
      audio.current = el;
      setPlaying(true);
      await el.play();
    } catch (e) {
      setPlaying(false);
      setError(e instanceof Error ? e.message : "This voice could not be played.");
    }
  }

  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-raised";
  return (
    <div ref={ref} className="relative">
      <div className="flex items-center rounded-full border border-border bg-card/60">
        <button type="button" onClick={play} aria-label={playing ? "Stop voice sample" : "Play voice sample"} className="flex h-9 w-9 items-center justify-center rounded-l-full hover:bg-raised">
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
        <button type="button" onClick={() => setMenu((v) => !v)} aria-expanded={menu} className="flex h-9 items-center gap-2 rounded-r-full pl-1 pr-3 text-sm font-medium hover:bg-raised">
          <span className="max-w-[160px] truncate">{label}</span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
      {error ? <p role="alert" className="absolute right-0 top-11 z-20 w-64 rounded-lg bg-destructive/15 px-3 py-2 text-xs text-destructive">{error}</p> : null}
      {menu ? (
        <div role="menu" className="absolute right-0 z-30 mt-1 w-52 rounded-xl border border-border bg-card p-1.5 shadow-2xl shadow-black/40">
          <Link role="menuitem" href="/voices" className={item}><Mic className="h-4 w-4 text-muted-foreground" /> Improve voice</Link>
          <button role="menuitem" type="button" onClick={() => { setMenu(false); setSwitching(true); }} className={item}><Replace className="h-4 w-4 text-muted-foreground" /> Switch voice</button>
        </div>
      ) : null}
      {switching ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Choose a voice">
          <div className="relative max-h-[90vh] w-full max-w-[640px] overflow-y-auto rounded-3xl border border-border bg-card p-6 sm:p-8">
            <button type="button" onClick={() => setSwitching(false)} aria-label="Close" className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full hover:bg-raised"><X className="h-5 w-5" /></button>
            <VoiceStep avatar={avatar} onDone={(a) => { setSwitching(false); onChanged(a); }} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
