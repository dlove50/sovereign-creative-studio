"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FileAudio, Loader2, Upload, Video } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, VoiceOption } from "@/lib/types";

type Result = Awaited<ReturnType<typeof api.translateVideo>>;
const ACCEPT = "video/mp4,video/quicktime,video/webm,video/x-matroska,audio/mpeg,audio/wav,audio/mp4,.mkv,.m4v,.m4a";

// Piper voice ids start with a language code (es_ES-..., fr_FR-...). Used to pick a voice that speaks the translation.
const LANGUAGE_CODES: Record<string, string> = {
  English: "en", Spanish: "es", French: "fr", German: "de", Italian: "it", Portuguese: "pt", Dutch: "nl", Polish: "pl",
  Russian: "ru", Ukrainian: "uk", Turkish: "tr", Arabic: "ar", Chinese: "zh", Czech: "cs", Danish: "da", Finnish: "fi",
  Greek: "el", Hungarian: "hu", Norwegian: "no", Romanian: "ro", Swedish: "sv", Vietnamese: "vi", Catalan: "ca",
};

function voiceForLanguage(language: string, voices: VoiceOption[]): VoiceOption | undefined {
  const code = LANGUAGE_CODES[language];
  return code ? voices.find((v) => v.ready && v.language.toLowerCase().startsWith(`${code}_`)) : undefined;
}

function clock(seconds: number) {
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export function TranslateView() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [languages, setLanguages] = useState<string[]>([]);
  const [language, setLanguage] = useState("Spanish");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [voiceChosen, setVoiceChosen] = useState(false); // once the person picks a voice, stop choosing for them
  const [making, setMaking] = useState(false);
  const spokenLanguage = result?.language ?? language;
  const matchingVoice = voiceForLanguage(spokenLanguage, voices);

  useEffect(() => {
    if (!voiceChosen) setVoiceId(matchingVoice?.id ?? "");
  }, [matchingVoice?.id, voiceChosen]);

  useEffect(() => {
    api.translateLanguages().then(setLanguages).catch(() => setLanguages([]));
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setAvatarId((cur) => cur || photos[0]?.id || "");
    }).catch(() => setAvatars([]));
    api.getAudioMergeReadiness().then((r) => setVoices(r.voices)).catch(() => setVoices([]));
  }, []);

  async function run() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      setResult(await api.translateVideo(form));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The file could not be translated.");
    } finally {
      setBusy(false);
    }
  }

  async function makeAvatarVideo() {
    if (!result || !avatarId) return;
    setMaking(true);
    setError(null);
    try {
      const made = await api.translationToMovie({
        title: `${file?.name.replace(/\.[^.]+$/, "") ?? "Video"} (${result.language})`,
        lines: result.segments.map((s) => s.text),
        avatar_id: avatarId,
        tts_voice_id: voiceId || null,
        orientation: "landscape",
      });
      router.push(`/movies/${made.movie_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the avatar video.");
      setMaking(false);
    }
  }

  const field = "mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <div className="mx-auto max-w-[820px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Translate video</h1>
      <p className="mx-auto mt-2 max-w-lg text-center text-sm text-muted-foreground">
        Upload a video or recording and get subtitles in another language. You can also have your avatar say the translation.
        Spoken translation needs a voice in that language. Spanish and French voices are installed; for other
        languages, use a cloned voice and check how it sounds before relying on it.
      </p>

      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-8 flex w-full flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-border bg-card/40 py-10 hover:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {file ? <FileAudio className="h-7 w-7 text-primary" /> : <Upload className="h-7 w-7 text-muted-foreground" />}
        <span className="text-sm font-semibold">{file ? file.name : "Choose a video or audio file"}</span>
        <span className="text-xs text-muted-foreground">{file ? `${(file.size / 1e6).toFixed(1)} MB · click to change` : "MP4, MOV, WEBM, MKV, MP3, WAV or M4A"}</span>
      </button>
      <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="min-w-[220px] flex-1 text-xs font-medium text-muted-foreground">
          Translate into
          <select value={language} onChange={(e) => setLanguage(e.target.value)} className={field}>
            {(languages.length ? languages : [language]).map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <button type="button" disabled={busy || !file} onClick={run} className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-6 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {busy ? "Translating… this can take a few minutes" : "Translate"}
        </button>
      </div>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      {result ? (
        <section className="mt-7 space-y-4" aria-label="Translation result">
          {result.has_video ? <video src={assetUrl(result.video_url) ?? undefined} controls className="max-h-[360px] w-full rounded-2xl bg-black" /> : null}
          <div className="flex flex-wrap gap-2">
            <a href={assetUrl(result.srt_url) ?? undefined} download className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised">
              <Download className="h-4 w-4" /> Subtitles (.srt)
            </a>
            <a href={assetUrl(result.vtt_url) ?? undefined} download className="inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised">
              <Download className="h-4 w-4" /> Subtitles (.vtt)
            </a>
          </div>
          <ol className="max-h-[320px] space-y-2 overflow-y-auto rounded-2xl border border-border bg-card/50 p-3 text-sm">
            {result.segments.map((s, i) => (
              <li key={i} className="grid grid-cols-[48px_1fr] gap-3">
                <span className="text-xs text-muted-foreground">{clock(s.start)}</span>
                <span>{s.text}<span className="block text-xs text-muted-foreground">{s.original}</span></span>
              </li>
            ))}
          </ol>
          <div className="rounded-3xl border border-border bg-card/60 p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold"><Video className="h-4 w-4" /> Have an avatar say it</h2>
            <p className="mt-1 text-xs text-muted-foreground">Creates a draft you can review in the scene editor. Nothing renders until you press Generate.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <label className="text-xs font-medium text-muted-foreground">
                Presenter
                <select value={avatarId} onChange={(e) => setAvatarId(e.target.value)} className={field}>
                  {avatars.length === 0 ? <option value="">No avatars yet</option> : null}
                  {avatars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </label>
              <label className="text-xs font-medium text-muted-foreground">
                Voice
                <select value={voiceId} onChange={(e) => { setVoiceChosen(true); setVoiceId(e.target.value); }} className={field}>
                  <option value="">Default voice</option>
                  {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
                <span className="mt-1 block text-xs font-normal" aria-live="polite">
                  {voiceChosen
                    ? (voiceId && matchingVoice?.id !== voiceId ? `Check that this voice speaks ${spokenLanguage}.` : "")
                    : matchingVoice ? `Matched to ${spokenLanguage}: ${matchingVoice.label}.`
                      : `No built-in ${spokenLanguage} voice. The default voice is English; choose a cloned voice for ${spokenLanguage}.`}
                </span>
              </label>
              <button type="button" disabled={making || !avatarId} onClick={makeAvatarVideo} className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                {making ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Create draft
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
