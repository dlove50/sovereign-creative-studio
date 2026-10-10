"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useRef, useState } from "react";
import { ImagePlus, Loader2, Mic, Shirt, Sparkles, Trash2, UserSquare, Video } from "lucide-react";

import { defaultVoiceFor } from "@/lib/avatar-voice";
import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, AvatarJob, AvatarVoiceReadiness, VoiceAsset, VoiceOption } from "@/lib/types";
import Link from "next/link";
import { MediaActions } from "@/components/media/MediaActions";
import { MediaDetailsDrawer } from "@/components/media/MediaDetailsDrawer";
import { useMediaHandoffRouter } from "@/components/media/useMediaHandoffRouter";
import { avatarJobToMedia } from "@/lib/utils/mediaMapping";
import { cn } from "@/lib/utils";

function ReadyBadge({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-medium",
        ready
          ? "bg-emerald-500/15 text-emerald-400"
          : "bg-amber-500/15 text-amber-400",
      )}
    >
      {label}: {ready ? "Ready" : "Setup required"}
    </span>
  );
}

export function AvatarsView() {
  const [isAdmin, setIsAdmin] = useState(false);
  const [readiness, setReadiness] = useState<AvatarVoiceReadiness | null>(null);
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceAsset[]>([]);
  const [greeting, setGreeting] = useState<AvatarJob | null>(null);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [voiceName, setVoiceName] = useState("");
  const [talkingJob, setTalkingJob] = useState<AvatarJob | null>(null);
  const [pickAvatar, setPickAvatar] = useState("");
  const [pickVoice, setPickVoice] = useState("");
  const [avatarPreset, setAvatarPreset] = useState("tiny_test");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [script, setScript] = useState("");
  const [ttsVoices, setTtsVoices] = useState<VoiceOption[]>([]);
  const [ttsVoice, setTtsVoice] = useState("");
  const photoInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);

  const { onAction, detailsMedia, closeDetails, toast } = useMediaHandoffRouter("from Avatar & Voice Hub");
  const readyVoices = voices.filter((v) => v.sample_file_path);
  const avatarPresets = readiness?.avatar_presets ?? [];
  const selectedPreset = avatarPresets.find((p) => p.id === avatarPreset);
  // Only a genuinely completed avatar video maps to a MediaObject (else null).
  const avatarMedia = talkingJob ? avatarJobToMedia(talkingJob) : null;

  async function refresh() {
    const [a, v] = await Promise.all([api.listAvatars(), api.listVoices()]);
    setAvatars(a);
    setVoices(v);
  }

  useEffect(() => {
    api.getMe().then((u) => setIsAdmin(u.role === "owner_admin")).catch(() => setIsAdmin(false));
    api.avatarReadiness().then(setReadiness).catch(() => setReadiness(null));
    // Piper voices plus any VibeVoice clones (listed when VibeVoice Studio is running).
    api
      .getAudioMergeReadiness()
      .then((r) => {
        setTtsVoices(r.voices);
        setTtsVoice((cur) => cur || r.voices.find((v) => v.is_default)?.id || r.voices[0]?.id || "");
      })
      .catch(() => setTtsVoices([]));
    refresh().catch((e) => setError(e instanceof Error ? e.message : "Could not load avatars"));
  }, []);

  useEffect(() => {
    // A Home "video prompt" card passes its starter script in ?script=.
    const params = new URLSearchParams(window.location.search);
    const fromLink = params.get("script");
    if (fromLink) setScript(fromLink.slice(0, 2000));
    // "Use in a video" / "Make a video" pass the chosen look in ?avatar=.
    const chosen = params.get("avatar");
    if (chosen) setPickAvatar(chosen);
  }, []);

  useEffect(() => {
    const saved = defaultVoiceFor(avatars.find((a) => a.id === pickAvatar), avatars, ttsVoices);
    if (saved) setTtsVoice(saved);
  }, [pickAvatar, avatars, ttsVoices]);

  useEffect(() => {
    if (readiness?.greeting_text) setScript((cur) => cur || readiness.greeting_text);
  }, [readiness?.greeting_text]);

  useEffect(() => {
    if (readiness?.default_avatar_preset) setAvatarPreset(readiness.default_avatar_preset);
  }, [readiness?.default_avatar_preset]);

  async function uploadAvatar(kind: "photo" | "video", file: File) {
    setBusy(kind);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", file.name);
      if (kind === "photo") await api.createPhotoAvatar(form);
      else await api.createVideoAvatar(form);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(null);
    }
  }

  async function addVoice() {
    if (!voiceName.trim()) return;
    setBusy("voice");
    setError(null);
    try {
      await api.createVoice({ name: voiceName.trim(), voice_type: "preset" });
      setVoiceName("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add voice");
    } finally {
      setBusy(null);
    }
  }

  async function makeGreeting() {
    setBusy("greeting");
    setError(null);
    try {
      setGreeting(await api.createGreeting({ script_text: readiness?.greeting_text }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start greeting");
    } finally {
      setBusy(null);
    }
  }

  // Poll a queued/running talking-avatar job until it finishes.
  useEffect(() => {
    if (!talkingJob || (talkingJob.status !== "queued" && talkingJob.status !== "running")) return;
    const id = talkingJob.id;
    const timer = setInterval(async () => {
      try {
        const updated = await api.getAvatarJob(id);
        setTalkingJob(updated);
        if (updated.status === "completed") await refresh();
      } catch {
        /* keep last state on transient errors */
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [talkingJob]);

  async function makeTalkingAvatar() {
    if (!pickAvatar || !pickVoice) return;
    setBusy("talking");
    setError(null);
    try {
      setTalkingJob(
        await api.createTalkingAvatar({
          avatar_id: pickAvatar,
          voice_id: pickVoice,
          script_text: script.trim() || readiness?.greeting_text,
          avatar_preset: avatarPreset,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start talking avatar");
    } finally {
      setBusy(null);
    }
  }

  async function makeScriptVoice() {
    if (!script.trim()) return;
    setBusy("scriptvoice");
    setError(null);
    try {
      const voice = await api.generateVoiceGreeting({ script_text: script.trim(), tts_voice_id: ttsVoice || undefined });
      await refresh();
      setPickVoice(voice.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the voice");
    } finally {
      setBusy(null);
    }
  }


  async function makeVoiceGreeting() {
    setBusy("voicegreeting");
    setError(null);
    setVoiceNote(null);
    try {
      await api.generateVoiceGreeting({ script_text: readiness?.greeting_text });
      setVoiceNote("Voice greeting created — find it below to play or download.");
      await refresh();
    } catch (e) {
      // 409 = local voice setup required; show as a friendly note, not an error.
      const msg = e instanceof Error ? e.message : "Could not create voice greeting";
      if (/setup required|not installed|model not found/i.test(msg)) {
        setVoiceNote(`Local voice setup required — ${msg}`);
      } else {
        setError(msg);
      }
    } finally {
      setBusy(null);
    }
  }

  async function deleteVoiceGreeting(voice: VoiceAsset) {
    if (!await confirmDialog(`Delete “${voice.name}”? This removes its generated audio and cannot be undone.`)) return;
    setBusy(`delete-voice-${voice.id}`);
    setError(null);
    try {
      await api.deleteVoice(voice.id);
      if (pickVoice === voice.id) setPickVoice("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete voice greeting");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-8">
      {/* Greeting hero */}
      <section className="rounded-2xl border border-border bg-card p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Sparkles className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">
              {readiness?.greeting_text ?? "Welcome, let's create something amazing!"}
            </h2>
            <p className="text-sm text-muted-foreground">
              Make a talking avatar from a photo or video, give it a voice, and create a greeting.
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={makeGreeting}
            disabled={busy === "greeting"}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {busy === "greeting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Create greeting
          </button>
          {readiness ? (
            <>
              <ReadyBadge ready={readiness.avatar.ready} label="Avatar" />
              <ReadyBadge ready={readiness.voice.ready} label="Voice" />
            </>
          ) : null}
        </div>
        {greeting ? (
          <p className="mt-3 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            {greeting.status === "setup_required"
              ? `Avatar animation model setup required — ${greeting.error_message ?? ""}`
              : `Greeting status: ${greeting.status}`}
          </p>
        ) : null}
        {isAdmin && readiness ? (
          <div className="mt-3 space-y-1 rounded-md border border-border/70 bg-background/40 p-3 text-xs text-muted-foreground">
            <p>Avatar backend: <span className="font-mono">{readiness.avatar.backend}</span> — {readiness.avatar.detail}</p>
            <p>Voice backend: <span className="font-mono">{readiness.voice.backend}</span> — {readiness.voice.detail}</p>
            <p>Costs: avatar video {readiness.credits_per_avatar_video} credits · voice {readiness.credits_per_voice_generation} credits (charged on success only).</p>
          </div>
        ) : null}
      </section>

      {error ? (
        <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}

      {/* Create cards */}
      <section className="grid gap-4 sm:grid-cols-2">
        <CreateCard
          icon={UserSquare}
          title="Photo to Avatar"
          description="Upload a clear photo to turn into a talking avatar."
          busy={busy === "photo"}
          onPick={() => photoInput.current?.click()}
        />
        <CreateCard
          icon={Video}
          title="Video to Avatar"
          description="Upload a short video of a person to reuse as an avatar."
          busy={busy === "video"}
          onPick={() => videoInput.current?.click()}
        />
        <input
          ref={photoInput}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && uploadAvatar("photo", e.target.files[0])}
        />
        <input
          ref={videoInput}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && uploadAvatar("video", e.target.files[0])}
        />
      </section>

      {/* Avatar library */}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Your avatars</h3>
        {avatars.length === 0 ? (
          <p className="text-sm text-muted-foreground">No avatars yet — add a photo or video above.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {avatars.map((a) => (
              <div key={a.id} className="overflow-hidden rounded-xl border border-border bg-card">
                <div className="flex aspect-square items-center justify-center bg-background/60">
                  {a.thumbnail_path && assetUrl(a.thumbnail_path) ? (
                    <img src={assetUrl(a.thumbnail_path)!} alt={a.name} className="h-full w-full object-cover" />
                  ) : (
                    <Video className="h-6 w-6 text-muted-foreground" />
                  )}
                </div>
                <div className="p-2">
                  <p className="truncate text-xs font-medium">{a.name}</p>
                  <p className="text-[11px] text-muted-foreground">{a.avatar_type.replace("_", " ")}</p>
                  {a.avatar_type === "photo_avatar" ? (
                    <Link
                      href={`/avatars/looks?avatar=${a.id}`}
                      className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                    >
                      <Shirt className="h-3 w-3" /> New look
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Talking Avatar */}
      <section className="space-y-3 rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Video className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Create talking avatar</h3>
          {readiness ? <ReadyBadge ready={readiness.avatar.ready} label="Avatar engine" /> : null}
        </div>
        <p className="text-sm text-muted-foreground">
          1. Write what your avatar should say and pick a voice. 2. Choose a photo and quality. 3. Create the video —
          long voice recordings are rendered in overlapping chunks and joined. Chunk length depends on the selected preset; review transitions and lip sync before publishing.
        </p>
        <div className="space-y-2 rounded-xl border border-border/70 bg-background/40 p-3">
          <label htmlFor="avatar-script" className="text-xs font-medium text-muted-foreground">
            What should your avatar say?
          </label>
          <textarea
            id="avatar-script"
            data-testid="avatar-script"
            value={script}
            onChange={(e) => setScript(e.target.value)}
            maxLength={2000}
            rows={4}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <select
              value={ttsVoice}
              onChange={(e) => setTtsVoice(e.target.value)}
              aria-label="Voice"
              data-testid="avatar-tts-voice"
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {ttsVoices.length === 0 ? <option value="">Default voice</option> : null}
              {ttsVoices.map((v) => (
                <option key={v.id} value={v.id}>{v.label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={makeScriptVoice}
              disabled={busy === "scriptvoice" || !script.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-60"
            >
              {busy === "scriptvoice" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
              Generate voice
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {busy === "scriptvoice"
              ? "Generating speech… cloned voices take about 15 seconds per second of speech."
              : "Clone voices appear here while VibeVoice Studio is running. The new clip is selected below automatically."}
          </p>
        </div>
        {avatarPresets.length ? (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {avatarPresets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => setAvatarPreset(preset.id)}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left text-sm transition",
                  avatarPreset === preset.id
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border bg-background hover:bg-muted",
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-medium">{preset.label}</span>
                  {preset.default ? <span className="text-[10px] uppercase text-primary">Default</span> : null}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">{preset.description}</span>
                <span className="mt-2 block text-[11px] text-muted-foreground">
                  {preset.width}x{preset.height} · {preset.frames} frames · {preset.steps} steps
                </span>
                {preset.warning ? (
                  <span className="mt-1 block text-[11px] text-amber-400">{preset.warning}</span>
                ) : null}
              </button>
            ))}
          </div>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <select
            value={pickAvatar}
            onChange={(e) => setPickAvatar(e.target.value)}
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select avatar…</option>
            {avatars.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <select
            value={pickVoice}
            onChange={(e) => setPickVoice(e.target.value)}
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select voice…</option>
            {readyVoices.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={makeTalkingAvatar}
            disabled={busy === "talking" || !pickAvatar || !pickVoice}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {busy === "talking" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />}
            Create Talking Avatar
          </button>
        </div>
        {readyVoices.length === 0 ? (
          <p className="text-xs text-muted-foreground">Generate a voice from your script above first, then it appears here.</p>
        ) : null}
        {selectedPreset ? (
          <p className="text-xs text-muted-foreground">
            Selected quality: {selectedPreset.label}. Failed or OOM avatar jobs are not charged.
          </p>
        ) : null}
        {talkingJob ? (
          <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            {talkingJob.status === "setup_required" ? (
              <span>Avatar animation model setup required. Voice generation is ready. {talkingJob.error_message}</span>
            ) : talkingJob.status === "failed" ? (
              <span className="text-destructive">Generation failed: {talkingJob.error_message}</span>
            ) : talkingJob.status === "completed" && talkingJob.output_video_path ? (
              <div className="space-y-2">
                <video controls src={assetUrl(talkingJob.output_video_path) ?? undefined} className="w-full max-w-md rounded-md" />
                <p className="text-xs text-muted-foreground">
                  Preset: {talkingJob.avatar_preset ?? "unknown"}
                  {talkingJob.avatar_width && talkingJob.avatar_height
                    ? ` · ${talkingJob.avatar_width}x${talkingJob.avatar_height}`
                    : ""}
                  {talkingJob.avatar_runtime_seconds ? ` · ${talkingJob.avatar_runtime_seconds}s` : ""}
                </p>
                <a
                  href={assetUrl(talkingJob.output_video_path) ?? "#"}
                  download
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Download video
                </a>
                {avatarMedia ? (
                  <div className="border-t border-border/60 pt-2">
                    <MediaActions media={avatarMedia} onAction={onAction} compact />
                  </div>
                ) : null}
              </div>
            ) : (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Generating… ({talkingJob.status})
              </span>
            )}
          </div>
        ) : null}
        {isAdmin && readiness ? (
          <div className="space-y-0.5 rounded-md border border-border/70 bg-background/40 p-3 text-xs text-muted-foreground">
            <p>Avatar backend: <span className="font-mono">{readiness.avatar.backend}</span></p>
            <p>
              ComfyUI reachable: {String(readiness.avatar.comfy_reachable ?? "—")} · node:{" "}
              {String(readiness.avatar.node_present ?? "—")} · workflow:{" "}
              {String(readiness.avatar.workflow_present ?? "—")} · models:{" "}
              {String(readiness.avatar.models_present ?? "—")}
            </p>
            {readiness.avatar.missing && readiness.avatar.missing.length > 0 ? (
              <p>Missing: {readiness.avatar.missing.join("; ")}</p>
            ) : null}
            {selectedPreset ? (
              <p>
                Selected preset: {selectedPreset.id} · {selectedPreset.width}x{selectedPreset.height} ·{" "}
                {selectedPreset.frames} frames · {selectedPreset.steps} steps · CFG {selectedPreset.cfg}
              </p>
            ) : null}
            <p>Cost: {readiness.credits_per_avatar_video} credits on success.</p>
          </div>
        ) : null}
      </section>

      {/* Voices */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Mic className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Preset / Piper voices</h3>
          {readiness ? <ReadyBadge ready={readiness.voice.ready} label="Voice engine" /> : null}
          <button
            type="button"
            onClick={makeVoiceGreeting}
            disabled={busy === "voicegreeting"}
            className="ml-auto inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {busy === "voicegreeting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            Create a Piper greeting
          </button>
        </div>
        {voiceNote ? (
          <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">{voiceNote}</p>
        ) : null}
        <div className="flex gap-2">
          <input
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            placeholder="Voice name (e.g. Friendly)"
            className="flex h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button
            type="button"
            onClick={addVoice}
            disabled={busy === "voice" || !voiceName.trim()}
            className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-60"
          >
            <ImagePlus className="h-4 w-4" /> Add voice
          </button>
        </div>
        {voices.length === 0 ? (
          <p className="text-sm text-muted-foreground">No voices yet. Add a preset voice to get started.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {voices.map((v) => {
              const audio = v.sample_file_path ? assetUrl(v.sample_file_path) : null;
              return (
                <div key={v.id} className="space-y-2 rounded-lg border border-border bg-card px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{v.name}</p>
                      <p className="text-[11px] text-muted-foreground">{v.voice_type.replace("_", " ")}</p>
                    </div>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {v.status === "ready" ? "Ready" : "Setup required"}
                    </span>
                  </div>
                  {audio ? (
                    <div className="flex items-center gap-2">
                      <audio controls src={audio} className="h-8 w-full" />
                      <div className="flex shrink-0 flex-col items-start gap-1">
                        <button
                          type="button"
                          onClick={() => deleteVoiceGreeting(v)}
                          disabled={busy === `delete-voice-${v.id}`}
                          className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive hover:underline disabled:opacity-60"
                        >
                          {busy === `delete-voice-${v.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                          Delete
                        </button>
                        <a href={audio} download className="text-[11px] font-medium text-primary hover:underline">
                          Download
                        </a>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
        {readiness && !readiness.voice.ready ? (
          <p className="text-xs text-muted-foreground">
            Local voice generation needs a local TTS model (Piper). Preset voices can be saved now;
            spoken output arrives once a voice model is installed.
          </p>
        ) : null}
      </section>

      <p className="text-xs text-muted-foreground">
        Only create avatars from images/videos you have the rights to use. Generated avatar videos
        are AI-generated and are not real recordings.
      </p>
      <MediaDetailsDrawer media={detailsMedia} open={detailsMedia !== null} onClose={closeDetails} />
      {toast ? (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-lg">
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function CreateCard({
  icon: Icon,
  title,
  description,
  busy,
  onPick,
}: {
  icon: typeof UserSquare;
  title: string;
  description: string;
  busy: boolean;
  onPick: () => void;
}) {
  return (
    <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-5">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15 text-primary">
        <Icon className="h-6 w-6" />
      </span>
      <div>
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <button
        type="button"
        onClick={onPick}
        disabled={busy}
        className="mt-auto inline-flex items-center justify-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-60"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
        Upload &amp; create
      </button>
    </div>
  );
}
