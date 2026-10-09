"use client";
import { Skeleton } from "@/components/ui/skeleton";
import { confirmDialog } from "@/components/ui/confirm-host";
import { LoadError } from "@/components/ui/load-error";

import { useEffect, useMemo, useRef, useState } from "react";
import { Mic, Pause, Play, Trash2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { VoiceOption } from "@/lib/types";
import { cleanVoiceLabel, isCloneVoice, voiceGender, voiceTags } from "@/lib/voice-meta";
import { cn } from "@/lib/utils";
import { VoiceClonePanel } from "./voice-clone-panel";

type Tab = "mine" | "library";

export function VoicesView() {
  const [voices, setVoices] = useState<VoiceOption[] | null>(null);
  const [tab, setTab] = useState<Tab>("mine");
  const [query, setQuery] = useState("");
  const [gender, setGender] = useState("");
  const [cloning, setCloning] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const load = () => {
    setLoadError(null);
    return api.getAudioMergeReadiness()
      .then((r) => setVoices(r.voices))
      .catch((e) => { setLoadError(e instanceof Error ? e.message : "The voice service didn't answer."); setVoices([]); });
  };
  useEffect(() => { void load(); return () => audio.current?.pause(); }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (voices ?? []).filter((v) =>
      (tab === "mine" ? isCloneVoice(v) : !isCloneVoice(v)) &&
      (!q || cleanVoiceLabel(v).toLowerCase().includes(q)) &&
      (!gender || voiceGender(v) === gender));
  }, [voices, tab, query, gender]);

  async function play(id: string) {
    audio.current?.pause();
    if (playing === id) { setPlaying(null); return; }
    setError(null);
    try {
      const { url } = await api.voicePreview(id);
      const el = new Audio(assetUrl(url) ?? undefined);
      el.onended = () => setPlaying(null);
      audio.current = el;
      setPlaying(id);
      await el.play();
    } catch (e) {
      setPlaying(null);
      setError(e instanceof Error ? e.message : "This voice could not be played.");
    }
  }

  async function remove(v: VoiceOption) {
    if (!await confirmDialog(`Delete the cloned voice ${cleanVoiceLabel(v)}? Avatars that use it will need another voice.`)) return;
    try {
      await api.deleteClonedVoice(v.id.replace("vibevoice:", ""));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The voice could not be deleted.");
    }
  }

  const tabClass = (t: Tab) => cn("pb-2 text-base font-semibold", tab === t ? "border-b-2 border-primary text-foreground" : "text-muted-foreground hover:text-foreground");
  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="pt-4 text-4xl font-extrabold tracking-[-0.03em]">Voices</h1>
      <p className="mt-1 text-sm text-muted-foreground">Clone a voice, then give it to any avatar. Everything runs on this computer.</p>
      <div className="mt-6">
        <button type="button" onClick={() => setCloning((v) => !v)} aria-expanded={cloning} className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card/60 px-5 py-3 text-sm font-semibold hover:bg-card">
          <Mic className="h-4 w-4" /> Clone your voice
        </button>
      </div>
      {cloning ? <div className="mt-3"><VoiceClonePanel onClose={() => setCloning(false)} onCreated={() => { setCloning(false); setTab("mine"); void load(); }} /></div> : null}

      <div className="mt-6 flex gap-6 border-b border-border" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")} className={tabClass("mine")}>My voices</button>
        <button type="button" role="tab" aria-selected={tab === "library"} onClick={() => setTab("library")} className={tabClass("library")}>Library</button>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search voices…" aria-label="Search voices" className="h-10 min-w-[220px] flex-1 rounded-xl border border-input bg-background px-3 text-sm" />
        {tab === "library" ? (
          <select value={gender} onChange={(e) => setGender(e.target.value)} aria-label="Gender" className="h-10 rounded-xl border border-input bg-background px-3 text-sm">
            <option value="">All genders</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
          </select>
        ) : null}
      </div>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <ul className="mt-3 divide-y divide-border rounded-2xl border border-border" aria-label="Voices">
        {voices === null ? <li className="space-y-2 p-4"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></li> : null}
        {loadError ? <li className="p-4"><LoadError what="your voices" message={loadError} onRetry={() => void load()} /></li> : null}
        {voices !== null && !loadError && shown.length === 0 ? (
          <li className="p-8 text-center text-sm text-muted-foreground">
            {tab === "mine" ? "No cloned voices yet. Use Clone your voice above. The voice app needs to be running." : "No voices match."}
          </li>
        ) : null}
        {shown.map((v) => (
          <li key={v.id} className="flex items-center gap-3 px-3 py-3">
            <button type="button" onClick={() => play(v.id)} aria-label={`${playing === v.id ? "Stop" : "Play"} ${cleanVoiceLabel(v)}`} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-raised hover:bg-raised/70">
              {playing === v.id ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">{cleanVoiceLabel(v)}</span>
              <span className="text-xs text-muted-foreground">{voiceTags(v)}</span>
            </span>
            <span className={cn("rounded-md px-2 py-0.5 text-xs font-medium", isCloneVoice(v) ? "bg-primary/15 text-primary" : "bg-raised text-muted-foreground")}>{isCloneVoice(v) ? "Voice clone" : "Built-in"}</span>
            {isCloneVoice(v) ? (
              <button type="button" onClick={() => remove(v)} aria-label={`Delete ${cleanVoiceLabel(v)}`} className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
