"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Mic, UserRound } from "lucide-react";

import { api } from "@/lib/api";
import { dialogueToScenes, MAX_SCENES, type Speaker } from "@/lib/podcast";
import type { AvatarAsset, VoiceOption } from "@/lib/types";

const CREDITS_PER_SCENE = 17; // voice 2 + avatar video 15
const RENDER_SECONDS_PER_SECOND = 55;
const WORDS_PER_SECOND = 2.5;
const SAMPLE =
  "Host: Welcome back to the show. Today we're talking about how to answer customer emails faster.\n" +
  "Guest: Thanks for having me. The biggest change for me was setting two fixed times a day to clear the inbox.\n" +
  "Host: That sounds simple. Does it really work?\n" +
  "Guest: It does, because you stop reacting to every message and start answering them on purpose.";

function SpeakerCard({
  title, speaker, onChange, avatars, voices,
}: {
  title: string; speaker: Speaker; onChange: (s: Speaker) => void; avatars: AvatarAsset[]; voices: VoiceOption[];
}) {
  const field = "mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <section aria-label={title} className="rounded-3xl border border-border bg-card/60 p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold"><UserRound className="h-4 w-4 text-muted-foreground" /> {title}</h2>
      <label className="mt-3 block text-xs font-medium text-muted-foreground">
        Name in the script
        <input value={speaker.name} onChange={(e) => onChange({ ...speaker, name: e.target.value.slice(0, 40) })} className={field} />
      </label>
      <label className="mt-3 block text-xs font-medium text-muted-foreground">
        Avatar look
        <select value={speaker.avatarId} onChange={(e) => onChange({ ...speaker, avatarId: e.target.value })} className={field}>
          <option value="">Choose a look…</option>
          {avatars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <label className="mt-3 block text-xs font-medium text-muted-foreground">
        <span className="flex items-center gap-1"><Mic className="h-3 w-3" /> Voice</span>
        <select value={speaker.voiceId} onChange={(e) => onChange({ ...speaker, voiceId: e.target.value })} className={field}>
          <option value="">Default voice</option>
          {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </select>
      </label>
    </section>
  );
}

export function PodcastView() {
  const router = useRouter();
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [one, setOne] = useState<Speaker>({ name: "Host", avatarId: "", voiceId: "" });
  const [two, setTwo] = useState<Speaker>({ name: "Guest", avatarId: "", voiceId: "" });
  const [text, setText] = useState(SAMPLE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setOne((s) => ({ ...s, avatarId: s.avatarId || photos[0]?.id || "" }));
      setTwo((s) => ({ ...s, avatarId: s.avatarId || photos[1]?.id || photos[0]?.id || "" }));
    }).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => {
      setVoices(r.voices);
      setTwo((s) => ({ ...s, voiceId: s.voiceId || r.voices.find((v) => v.id !== r.voices[0]?.id)?.id || "" }));
    }).catch(() => setVoices([]));
  }, []);

  const parsed = useMemo(() => dialogueToScenes(text, [one, two]), [text, one, two]);
  const words = parsed.scenes.reduce((n, s) => n + s.script.split(/\s+/).filter(Boolean).length, 0);
  const estMinutes = Math.max(1, Math.round(((words / WORDS_PER_SECOND) * RENDER_SECONDS_PER_SECOND) / 60));
  const missingAvatar = !one.avatarId || !two.avatarId;
  const sameName = one.name.trim().toLowerCase() === two.name.trim().toLowerCase();

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const movie = await api.createMovie({ title: "Video podcast", orientation: "landscape", scenes: parsed.scenes });
      router.push(`/movies/${movie.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The podcast could not be created.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Video podcast</h1>
      <p className="mx-auto mt-2 max-w-lg text-center text-sm text-muted-foreground">
        Write a conversation between two people. Each line is shown by the speaker&apos;s avatar in their own voice, cutting back and forth like a podcast edit.
      </p>

      <div className="mt-7 grid gap-4 md:grid-cols-2">
        <SpeakerCard title="Speaker 1" speaker={one} onChange={setOne} avatars={avatars} voices={voices} />
        <SpeakerCard title="Speaker 2" speaker={two} onChange={setTwo} avatars={avatars} voices={voices} />
      </div>

      <label htmlFor="dialogue" className="mt-6 block text-xs font-medium text-muted-foreground">Conversation (start each line with the speaker&apos;s name and a colon)</label>
      <textarea
        id="dialogue"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={9}
        className="mt-1 w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {parsed.ignored > 0 ? <p className="mt-1 text-xs text-amber-500">{parsed.ignored} {parsed.ignored === 1 ? "line was" : "lines were"} skipped because no speaker name came before it.</p> : null}
      {sameName ? <p className="mt-1 text-xs text-destructive">Give the two speakers different names so each line goes to the right person.</p> : null}
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3">
        <span className="text-sm">
          <strong>{parsed.scenes.length}</strong> scenes · {parsed.scenes.length * CREDITS_PER_SCENE} credits · about {estMinutes} min to render
          {parsed.scenes.length >= MAX_SCENES ? <span className="ml-2 text-amber-500">Capped at {MAX_SCENES} scenes.</span> : null}
        </span>
        <button
          type="button"
          onClick={create}
          disabled={busy || parsed.scenes.length === 0 || missingAvatar || sameName}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Create podcast draft
        </button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">The draft opens in the scene editor, where you can review it and press Generate.</p>
    </div>
  );
}
