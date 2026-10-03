"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Loader2, Mic, Pause, Play } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, VoiceOption } from "@/lib/types";
import { cleanVoiceLabel as cleanLabel, isCloneVoice as isClone, voiceTags } from "@/lib/voice-meta";
import { VoiceClonePanel } from "@/components/voices/voice-clone-panel";
import { cn } from "@/lib/utils";

type Tab = "mine" | "builtin";

export function VoiceStep({ avatar, onBack, onDone }: { avatar: AvatarAsset; onBack?: () => void; onDone: (avatar: AvatarAsset) => void }) {
  const [voices, setVoices] = useState<VoiceOption[] | null>(null);
  const [tab, setTab] = useState<Tab>("mine");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(avatar.default_voice_id ?? null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [cloning, setCloning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  const load = () => api.getAudioMergeReadiness().then((r) => r.voices).catch(() => []).then(setVoices);
  useEffect(() => { void load(); return () => audio.current?.pause(); }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (voices ?? []).filter((v) => (tab === "mine" ? isClone(v) : !isClone(v)) && (!q || v.label.toLowerCase().includes(q)));
  }, [voices, tab, query]);

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

  async function select() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      onDone(await api.updateAvatar(avatar.id, { default_voice_id: selected }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the voice.");
      setSaving(false);
    }
  }

  const tabClass = (t: Tab) => cn("pb-2 text-base font-semibold", tab === t ? "border-b-2 border-primary text-foreground" : "text-muted-foreground hover:text-foreground");
  return (
    <div>
      <div className="flex items-center gap-3">
        {onBack ? <button type="button" onClick={onBack} aria-label="Back" className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-raised"><ArrowLeft className="h-5 w-5" /></button> : null}
        <h2 className="text-2xl font-extrabold tracking-tight">Choose a voice for {avatar.name}</h2>
      </div>
      <div className="mt-5">
        <button type="button" onClick={() => setCloning((v) => !v)} className="inline-flex items-center gap-2 rounded-2xl border border-border bg-card/60 px-5 py-3 text-sm font-semibold hover:bg-card">
          <Mic className="h-4 w-4" /> Clone your voice
        </button>
      </div>
      {cloning ? <div className="mt-3"><VoiceClonePanel onClose={() => setCloning(false)} onCreated={(id) => { setCloning(false); setSelected(id); setTab("mine"); void load(); }} /></div> : null}
      <div className="mt-5 flex gap-6 border-b border-border" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")} className={tabClass("mine")}>My voices</button>
        <button type="button" role="tab" aria-selected={tab === "builtin"} onClick={() => setTab("builtin")} className={tabClass("builtin")}>Built-in voices</button>
      </div>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search voices…" aria-label="Search voices" className="mt-4 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm" />
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <ul className="mt-3 max-h-[340px] divide-y divide-border overflow-y-auto rounded-2xl border border-border" aria-label="Voices">
        {voices === null ? <li className="p-6 text-center text-sm text-muted-foreground">Loading voices…</li> : null}
        {voices !== null && shown.length === 0 ? (
          <li className="p-6 text-center text-sm text-muted-foreground">
            {tab === "mine" ? "No cloned voices yet. Use Clone your voice above, and start the voice app if it is not running." : "No voices match."}
          </li>
        ) : null}
        {shown.map((v) => (
          <li key={v.id}>
            <div className={cn("flex items-center gap-3 px-3 py-3", selected === v.id && "bg-primary/10")}>
              <button type="button" onClick={() => play(v.id)} aria-label={`${playing === v.id ? "Stop" : "Play"} ${cleanLabel(v)}`} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-raised hover:bg-raised/70">
                {playing === v.id ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </button>
              <button type="button" onClick={() => setSelected(v.id)} aria-pressed={selected === v.id} className="min-w-0 flex-1 text-left focus-visible:outline-none">
                <span className="block truncate text-sm font-semibold">{cleanLabel(v)}</span>
                <span className="text-xs text-muted-foreground">{voiceTags(v)}</span>
              </button>
              {selected === v.id ? <span className="rounded-full bg-primary px-2.5 py-0.5 text-xs font-semibold text-primary-foreground">Selected</span> : null}
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-5 flex justify-between">
        <button type="button" onClick={() => onDone(avatar)} className="rounded-full bg-raised px-6 py-3 text-sm font-semibold hover:bg-raised/70">Skip for now</button>
        <button type="button" disabled={!selected || saving} onClick={select} className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Select voice
        </button>
      </div>
    </div>
  );
}
