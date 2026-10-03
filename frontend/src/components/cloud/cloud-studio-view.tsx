"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Cloud, Download, Loader2, RefreshCw, Settings2 } from "lucide-react";
import { cloudApi, type CatalogItem, type CloudJob, type CloudOperation, type CloudStatus } from "@/lib/api/cloud";
import { cn } from "@/lib/utils";

const MODES: { id: CloudOperation; label: string; detail: string }[] = [
  { id: "avatar-video", label: "Avatar video", detail: "Use a HeyGen avatar look with its own voice, or select another HeyGen voice." },
  { id: "tts", label: "Text to speech", detail: "Turn your script into an MP3 with a voice available to your ElevenLabs account." },
  { id: "sound-effects", label: "Sound effects", detail: "Describe a sound or ambience. Save the generated effect to your local collection." },
  { id: "voice-changer", label: "Voice changer", detail: "Upload a recording and change its voice while preserving the performance." },
  { id: "transcribe", label: "Speech to text", detail: "Transcribe audio or video, with speaker information and word timing saved as JSON." },
  { id: "dubbing", label: "Dubbing", detail: "Translate audio or video into another language using ElevenLabs automatic dubbing." },
  { id: "isolate", label: "Audio isolation", detail: "Remove background noise from a voice recording." },
];
const UPLOADS = new Set<CloudOperation>(["voice-changer", "transcribe", "dubbing", "isolate"]);
const field = "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
const button = "inline-flex items-center justify-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50";
const message = (e: unknown) => e instanceof Error ? e.message : "Something went wrong. Try again.";

function OutputPreview({ job }: { job: CloudJob }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = job.files.find(f => /\.(mp3|mp4|wav)$/.test(f));
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  if (!name) return null;
  async function preview() {
    if (!name) return;
    setBusy(true); setError("");
    try { setUrl(URL.createObjectURL(await cloudApi.file(job, name))); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  return <div className="space-y-2">{url ? name.endsWith(".mp4")
    ? <video controls src={url} className="max-h-96 w-full rounded-xl bg-black" aria-label={`${job.title} preview`} />
    : <audio controls src={url} className="w-full" aria-label={`${job.title} preview`} />
    : <button type="button" className={button} disabled={busy} onClick={preview}>{busy ? "Loading preview…" : "Preview output"}</button>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}</div>;
}

export function CloudStudioView() {
  const [status, setStatus] = useState<CloudStatus | null>(null);
  const [jobs, setJobs] = useState<CloudJob[]>([]);
  const [mode, setMode] = useState<CloudOperation>("avatar-video");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [voices, setVoices] = useState<CatalogItem[]>([]);
  const [avatars, setAvatars] = useState<CatalogItem[]>([]);
  const [voiceToken, setVoiceToken] = useState<string | null>(null);
  const [avatarToken, setAvatarToken] = useState<string | null>(null);
  const [ownership, setOwnership] = useState("public");
  const [voiceId, setVoiceId] = useState("");
  const [avatarId, setAvatarId] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File>();
  const [duration, setDuration] = useState(5);
  const [loop, setLoop] = useState(false);
  const [language, setLanguage] = useState("es");
  const [ratio, setRatio] = useState("16:9");
  const [engine, setEngine] = useState("avatar_iv");
  const [accepted, setAccepted] = useState(false);
  const [refreshing, setRefreshing] = useState<string[]>([]);
  const catalogVersion = useRef(0);
  const submitting = useRef(false);
  const provider = mode === "avatar-video" ? "heygen" : "elevenlabs";
  const providerName = provider === "heygen" ? "HeyGen" : "ElevenLabs";
  const connected = status?.providers.find(p => p.id === provider);
  const ready = !!connected?.enabled && !!connected?.configured;
  const voiceNeeded = ["tts", "voice-changer", "avatar-video"].includes(mode);
  const selectedVoice = voices.find(v => v.id === voiceId);
  const selectedAvatar = avatars.find(a => a.id === avatarId);

  useEffect(() => {
    let active = true;
    Promise.all([cloudApi.status(), cloudApi.jobs()]).then(([s, j]) => { if (active) { setStatus(s); setJobs(j); } })
      .catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    catalogVersion.current += 1;
    setVoices([]); setAvatars([]); setVoiceToken(null); setAvatarToken(null);
    setVoiceId(""); setAvatarId(""); setAccepted(false); setCatalogBusy(false);
  }, [provider, ownership]);

  useEffect(() => {
    if (!jobs.some(j => ["queued", "submitting"].includes(j.status))) return;
    const timer = setInterval(() => cloudApi.jobs().then(setJobs).catch(e => setError(message(e))), 4000);
    return () => clearInterval(timer);
  }, [jobs]);

  const remoteJobs = jobs.filter(j => j.status === "processing").map(j => j.id).join(",");
  useEffect(() => {
    if (!remoteJobs) return;
    let active = true;
    let checking = false;
    const timer = setInterval(async () => {
      if (checking) return;
      checking = true;
      for (const id of remoteJobs.split(",")) {
        try { const updated = await cloudApi.refresh(id); if (active) setJobs(current => current.map(j => j.id === id ? updated : j)); }
        catch (e) { if (active) setError(message(e)); }
      }
      checking = false;
    }, 60_000);
    return () => { active = false; clearInterval(timer); };
  }, [remoteJobs]);

  async function loadCatalog(kind: "voices" | "avatars", more = false) {
    const version = catalogVersion.current;
    setCatalogBusy(true); setError("");
    try {
      const page = await cloudApi.catalog(provider, kind, more ? (kind === "voices" ? voiceToken : avatarToken) ?? "" : "", ownership);
      if (version !== catalogVersion.current) return;
      const update = (previous: CatalogItem[]) => [...new Map([...(more ? previous : []), ...page.items].map(item => [item.id, item])).values()];
      if (kind === "voices") { setVoices(update); setVoiceToken(page.next_token); }
      else { setAvatars(update); setAvatarToken(page.next_token); }
      if (!page.items.length) setNotice("No profiles returned for this account and filter. You can also enter a profile ID.");
    } catch (e) { if (version === catalogVersion.current) setError(message(e)); }
    finally { if (version === catalogVersion.current) setCatalogBusy(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    if (UPLOADS.has(mode) && !file) { setError("Choose an audio or video file first."); return; }
    if (file && UPLOADS.has(mode) && file.size > 100 * 1024 * 1024) { setError("Choose a file smaller than 100 MB."); return; }
    submitting.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const job = await cloudApi.submit({ request_id: crypto.randomUUID(), operation: mode, accept_charges: accepted,
        title, text, voice_id: voiceId, avatar_id: avatarId, aspect_ratio: ratio, engine,
        target_lang: language, duration_seconds: duration, loop }, UPLOADS.has(mode) ? file : undefined);
      setJobs(current => [job, ...current.filter(j => j.id !== job.id)]);
      setAccepted(false); setNotice("Job saved. Its progress and downloads appear below.");
    } catch (e) {
      setError(message(e));
      // A lost response does not mean submission failed. Do not retry a paid POST.
      try { setJobs(await cloudApi.jobs()); } catch { /* Keep the original error visible. */ }
    } finally { submitting.current = false; setBusy(false); }
  }

  async function refreshJob(job: CloudJob) {
    setRefreshing(current => [...current, job.id]);
    setError("");
    try { const updated = await cloudApi.refresh(job.id); setJobs(current => current.map(j => j.id === job.id ? updated : j)); }
    catch (e) { setError(message(e)); }
    finally { setRefreshing(current => current.filter(id => id !== job.id)); }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-12">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="mb-2 flex items-center gap-2 text-sm text-primary"><Cloud className="h-4 w-4" /> Connected creation</p>
          <h1 className="text-3xl font-semibold tracking-tight">Cloud studio</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Your HeyGen profiles and ElevenLabs tools, with finished media saved in Sovereign. Owner access required.</p></div>
        <Link href="/admin/integrations" className={button}><Settings2 className="h-4 w-4" /> Provider settings</Link>
      </header>
      <div className="flex flex-wrap gap-2" aria-label="Cloud tools">
        {MODES.map(m => <button key={m.id} type="button" disabled={busy} aria-pressed={mode === m.id}
          onClick={() => { setMode(m.id); setAccepted(false); setError(""); setNotice(""); }}
          className={cn(button, mode === m.id && "border-primary bg-primary/10 text-primary")}>{m.label}</button>)}
      </div>
      {error && <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm">{error}</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <form onSubmit={submit} className="space-y-5 rounded-2xl border border-border bg-card p-5 sm:p-7">
          <div><h2 className="text-xl font-semibold">{MODES.find(m => m.id === mode)?.label}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{MODES.find(m => m.id === mode)?.detail}</p></div>
          {!ready && <p className="rounded-xl bg-raised p-4 text-sm">{status ? `Add an API key and enable ${providerName} in Provider settings to use this tool.` : "Loading provider settings…"}</p>}
          <label className="block space-y-2 text-sm font-medium">Project title <span className="font-normal text-muted-foreground">(optional)</span>
            <input className={field} value={title} onChange={e => setTitle(e.target.value)} maxLength={120} placeholder="Give this output a name" /></label>
          {mode === "avatar-video" && <div className="space-y-3">
            <label className="block space-y-2 text-sm font-medium">HeyGen library
              <select className={field} value={ownership} onChange={e => setOwnership(e.target.value)}><option value="public">Public profiles</option><option value="private">My profiles</option></select></label>
            <button type="button" className={button} disabled={!ready || catalogBusy} onClick={() => loadCatalog("avatars")}>
              {catalogBusy && <Loader2 className="h-4 w-4 animate-spin" />} Browse avatar looks</button>
            {avatars.length > 0 && <div className="grid max-h-80 grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-3">
              {avatars.map(a => <button key={a.id} type="button" aria-pressed={avatarId === a.id}
                className={cn("overflow-hidden rounded-xl border text-left focus-visible:ring-2 focus-visible:ring-primary", avatarId === a.id ? "border-primary bg-primary/10" : "border-border")}
                onClick={() => { setAvatarId(a.id); setVoiceId(a.default_voice_id ?? ""); if (a.engines.length) setEngine(a.engines.includes("avatar_iv") ? "avatar_iv" : a.engines[0]); }}>
                {/* Provider-hosted catalog preview, never used as a local clone. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {a.image_url && <img src={a.image_url} alt="" loading="lazy" className="h-32 w-full object-cover" />}
                <span className="block p-2 text-xs font-medium">{a.name}</span></button>)}
            </div>}
            {avatarToken && <button type="button" className={button} disabled={catalogBusy} onClick={() => loadCatalog("avatars", true)}>More avatar looks</button>}
            <label className="block space-y-2 text-sm font-medium">Avatar look ID<input required className={field} value={avatarId} onChange={e => setAvatarId(e.target.value)} placeholder="Choose a profile above or paste its look ID" pattern="[A-Za-z0-9_-]+" /></label>
            <div className="grid grid-cols-2 gap-3"><label className="space-y-2 text-sm font-medium">Format<select className={field} value={ratio} onChange={e => setRatio(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select></label>
              <label className="space-y-2 text-sm font-medium">Avatar engine<select className={field} value={engine} onChange={e => setEngine(e.target.value)}>
                {(selectedAvatar?.engines.length ? selectedAvatar.engines : ["avatar_iv", "avatar_v", "avatar_iii"]).map(value => <option key={value} value={value}>{value.replace("avatar_", "Avatar ").toUpperCase()}</option>)}</select></label></div>
          </div>}
          {voiceNeeded && <div className="space-y-3">
            <button type="button" className={button} disabled={!ready || catalogBusy} onClick={() => loadCatalog("voices")}>Browse {providerName} voices</button>
            {voices.length > 0 && <label className="block space-y-2 text-sm font-medium">Available voices<select className={field} value={voices.some(v => v.id === voiceId) ? voiceId : ""} onChange={e => setVoiceId(e.target.value)}><option value="">Choose a voice</option>{voices.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>}
            {voiceToken && <button type="button" className={button} disabled={catalogBusy} onClick={() => loadCatalog("voices", true)}>More voices</button>}
            <label className="block space-y-2 text-sm font-medium">Voice ID {mode === "avatar-video" && <span className="font-normal text-muted-foreground">(blank uses avatar default)</span>}
              <input required={mode !== "avatar-video"} className={field} value={voiceId} onChange={e => setVoiceId(e.target.value)} pattern="[A-Za-z0-9_-]*" placeholder="Choose a voice or paste its ID" /></label>
            {selectedVoice?.audio_url && <audio key={selectedVoice.id} controls preload="none" src={selectedVoice.audio_url} className="w-full" aria-label={`${selectedVoice.name} preview`} />}
          </div>}
          {UPLOADS.has(mode) ? <label className="block space-y-2 text-sm font-medium">Source recording
            <input key={mode} type="file" required className={field} accept={mode === "dubbing" || mode === "transcribe" ? "audio/*,video/*" : "audio/*"} onChange={e => setFile(e.target.files?.[0])} />
            <span className="block text-xs font-normal text-muted-foreground">Up to 100 MB. This file will be uploaded to ElevenLabs for processing.</span></label>
            : <label className="block space-y-2 text-sm font-medium">{mode === "sound-effects" ? "Describe the sound" : "Script"}
              <textarea required className={cn(field, "min-h-36 resize-y")} value={text} onChange={e => setText(e.target.value)} maxLength={5000}
                placeholder={mode === "sound-effects" ? "Rain on a workshop roof, soft wind and a distant rumble…" : "Write what the voice should say…"} /></label>}
          {mode === "sound-effects" && <div className="flex flex-wrap items-end gap-5"><label className="space-y-2 text-sm font-medium">Duration (seconds)<input type="number" min={0.5} max={30} step={0.5} className={field} value={duration} onChange={e => setDuration(Number(e.target.value))} /></label>
            <label className="flex items-center gap-2 py-3 text-sm"><input type="checkbox" checked={loop} onChange={e => setLoop(e.target.checked)} /> Seamless loop</label></div>}
          {mode === "dubbing" && <label className="block space-y-2 text-sm font-medium">Target language code
            <input required className={field} pattern="[a-z]{2,3}" maxLength={3} value={language} onChange={e => setLanguage(e.target.value.toLowerCase())} />
            <span className="block text-xs font-normal text-muted-foreground">For example: es (Spanish), fr (French), en (English), de (German). Uses automatic dubbing with watermark enabled.</span></label>}
          <label className="flex items-start gap-3 text-sm"><input required type="checkbox" className="mt-1" checked={accepted} onChange={e => setAccepted(e.target.checked)} />
            <span>Send this request to {providerName}. It uses my provider credits or paid allowance.</span></label>
          <button disabled={!ready || busy || !accepted} className={cn(button, "border-primary bg-primary text-primary-foreground hover:bg-primary/90")}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}{busy ? "Submitting…" : `Create with ${providerName}`}</button>
        </form>
        <aside className="space-y-6 text-sm">
          <div><h2 className="font-semibold">Connected providers</h2><div className="mt-3 space-y-3">{status?.providers.map(p => <div key={p.id} className="flex justify-between gap-3 border-b border-border pb-3"><span>{p.name}</span><span className="text-muted-foreground">{p.enabled && p.configured ? "Enabled" : "Needs setup"}</span></div>)}</div></div>
          <div><h2 className="font-semibold">Saved on this computer</h2><p className="mt-2 text-muted-foreground">Completed outputs are downloaded into the folder below. Use the downloads in job history to copy them elsewhere.</p><code className="mt-3 block break-all rounded-xl bg-raised p-3 text-xs">{status?.output_directory ?? "Loading…"}</code></div>
          <p className="text-muted-foreground">Profiles run through their original provider. Voice and avatar models remain in the cloud. Available profiles and features depend on your account; a website subscription may not include API credits.</p>
        </aside>
      </div>
      <section className="space-y-4" aria-label="Cloud job history"><div className="flex items-center justify-between gap-3"><h2 className="text-xl font-semibold">Your cloud outputs</h2>
        <button className={button} type="button" onClick={() => cloudApi.jobs().then(setJobs).catch(e => setError(message(e)))}><RefreshCw className="h-4 w-4" /> Reload history</button></div>
        {!jobs.length && <p className="rounded-2xl border border-dashed border-border p-8 text-sm text-muted-foreground">Your first output will appear here. No cloud generation runs until you submit a request.</p>}
        {jobs.map(job => <article key={job.id} className="space-y-3 rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-medium">{job.title}</h3><p className="mt-1 text-xs text-muted-foreground">{job.provider} · {job.operation} · {new Date(job.created_at).toLocaleString()}</p></div>
            <span className="rounded-full bg-raised px-3 py-1 text-xs">{job.status === "submitting" ? "Working" : job.status}</span></div>
          {job.error && <p className="text-sm text-destructive">{job.error}</p>}
          {job.remote_id && <p className="break-all text-xs text-muted-foreground">Provider job: {job.remote_id}</p>}
          {job.status === "processing" && <div className="space-y-2"><p className="text-xs text-muted-foreground">Progress checks run every minute while this page is open. You can return later to save the result.</p><button type="button" className={button} disabled={refreshing.includes(job.id)} onClick={() => refreshJob(job)}>{refreshing.includes(job.id) ? "Checking & saving…" : "Check progress & save result"}</button></div>}
          <OutputPreview job={job} />
          <div className="flex flex-wrap gap-2">{job.files.map(name => <button type="button" key={name} className={button} onClick={() => cloudApi.download(job, name).catch(e => setError(message(e)))}><Download className="h-4 w-4" /> {name}</button>)}</div>
        </article>)}
      </section>
    </div>
  );
}
