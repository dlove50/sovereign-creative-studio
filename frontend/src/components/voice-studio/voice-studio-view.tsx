"use client";

import { PromptAssist } from "@/components/prompt-assist/prompt-assist";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioLines, Dices, Download, Loader2, Pause, Play, Power, Square, Trash2, Upload, Users } from "lucide-react";

import { confirmDialog } from "@/components/ui/confirm-host";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  voiceStudioApi, type VoiceClip, type VoiceEngine, type VoiceExample, type VoiceJob, type VoiceList, type VoiceModel,
} from "@/lib/api/voice-studio";
import { cn } from "@/lib/utils";

type Tab = "conversation" | "realtime" | "library";

const fmt = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
/** "en-Alice_woman" becomes "Alice, woman (English)". */
const LANGUAGES: Record<string, string> = { en: "English", zh: "Chinese", in: "Indian English" };
function voiceLabel(name: string) {
  const m = name.match(/^([a-z]{2})-([A-Za-z]+)_(man|woman)(?:_bgm)?$/);
  if (!m) return name;
  return `${m[2]}, ${m[3]} (${LANGUAGES[m[1]] ?? m[1]})${name.endsWith("_bgm") ? ", with music" : ""}`;
}
const errorText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

/** Play, pause, stop and download for one finished clip. */
function ClipPlayer({ url, name, autoPlay = false }: { url: string; name: string; autoPlay?: boolean }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const el = new Audio(url);
    audio.current = el;
    el.onloadedmetadata = () => setDuration(el.duration || 0);
    el.ontimeupdate = () => setPosition(el.currentTime);
    el.onended = () => { setPlaying(false); setPosition(0); };
    if (autoPlay) void el.play().then(() => setPlaying(true)).catch(() => undefined);
    return () => { el.pause(); audio.current = null; };
  }, [url, autoPlay]);

  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) void el.play().then(() => setPlaying(true)).catch(() => undefined);
    else { el.pause(); setPlaying(false); }
  };
  const stop = () => {
    const el = audio.current;
    if (!el) return;
    el.pause();
    el.currentTime = 0;
    setPlaying(false);
    setPosition(0);
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-background/40 p-3" role="group" aria-label="Playback controls">
      <Button size="icon" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button size="icon" variant="ghost" onClick={stop} aria-label="Stop"><Square className="h-4 w-4" /></Button>
      <input
        type="range" min={0} max={duration || 1} step={0.1} value={position} aria-label="Position"
        onChange={(e) => { const el = audio.current; if (el) { el.currentTime = Number(e.target.value); setPosition(Number(e.target.value)); } }}
        className="min-w-[120px] flex-1 accent-primary"
      />
      <span className="tabular w-24 text-right text-xs text-muted-foreground">{fmt(position)} / {fmt(duration)}</span>
      <a href={url} download={name} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-muted">
        <Download className="h-4 w-4" aria-hidden="true" /> Download
      </a>
    </div>
  );
}

/** Plays the engine's live chunks gaplessly while a clip is still being made. */
function useLiveAudio() {
  const ctx = useRef<AudioContext | null>(null);
  const nextAt = useRef(0);
  const sources = useRef<AudioBufferSourceNode[]>([]);
  const [heard, setHeard] = useState(0);

  const push = useCallback((base64: string, sampleRate: number) => {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const ints = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
    if (!ints.length) return;
    if (!ctx.current) ctx.current = new AudioContext({ sampleRate });
    const c = ctx.current;
    const buffer = c.createBuffer(1, ints.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < ints.length; i++) channel[i] = ints[i] / 32768;
    const source = c.createBufferSource();
    source.buffer = buffer;
    source.connect(c.destination);
    const start = Math.max(c.currentTime + 0.05, nextAt.current);
    source.start(start);
    nextAt.current = start + buffer.duration;
    sources.current.push(source);
    setHeard((h) => h + buffer.duration);
  }, []);

  const stop = useCallback(() => {
    sources.current.forEach((s) => { try { s.stop(); } catch { /* already finished */ } });
    sources.current = [];
    nextAt.current = 0;
    void ctx.current?.close();
    ctx.current = null;
    setHeard(0);
  }, []);

  useEffect(() => stop, [stop]);
  return { push, stop, heard };
}

export function VoiceStudioView() {
  const [tab, setTab] = useState<Tab>("conversation");
  const [engine, setEngine] = useState<VoiceEngine | null>(null);
  const [models, setModels] = useState<VoiceModel[]>([]);
  const [voices, setVoices] = useState<VoiceList>({ voices: [], realtime: [] });
  const [examples, setExamples] = useState<VoiceExample[]>([]);
  const [clips, setClips] = useState<VoiceClip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);

  // conversation form
  const [script, setScript] = useState("");
  const [count, setCount] = useState(2);
  const [speakers, setSpeakers] = useState<string[]>(["en-Alice_woman", "en-Carter_man", "en-Frank_man", "en-Maya_woman"]);
  const [cfg, setCfg] = useState(1.3);
  const [steps, setSteps] = useState(5);
  const [seed, setSeed] = useState(42);
  const [noClone, setNoClone] = useState(false);
  // realtime form
  const [rtText, setRtText] = useState("");
  const [rtVoice, setRtVoice] = useState("en-Emma_woman");
  const [rtCfg, setRtCfg] = useState(1.5);
  const [rtSteps, setRtSteps] = useState(5);

  const [job, setJob] = useState<VoiceJob | null>(null);
  const [result, setResult] = useState<VoiceClip | null>(null);
  const jobId = useRef<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const live = useLiveAudio();
  const [previewing, setPreviewing] = useState<string | null>(null);
  const previewAudio = useRef<HTMLAudioElement | null>(null);

  const refreshStatus = useCallback(async () => {
    try { setEngine(await voiceStudioApi.status()); } catch { setEngine(null); }
  }, []);
  const refreshClips = useCallback(() => { voiceStudioApi.clips().then(setClips).catch(() => setClips([])); }, []);

  const loadEngineData = useCallback(async () => {
    try {
      const [m, v, e] = await Promise.all([voiceStudioApi.models(), voiceStudioApi.voices(), voiceStudioApi.examples()]);
      setModels(m.models);
      setVoices(v);
      setExamples(e.examples);
    } catch { /* the engine is asleep: lists fill in once it is ready */ }
  }, []);

  useEffect(() => {
    void refreshStatus();
    refreshClips();
    const id = window.setInterval(() => void refreshStatus(), 3000);
    return () => window.clearInterval(id);
  }, [refreshStatus, refreshClips]);

  useEffect(() => { if (engine?.ready) void loadEngineData(); }, [engine?.ready, engine?.model, loadEngineData]);

  // When Voice Studio opens, wake the engine once (nothing else to do first).
  const woke = useRef(false);
  useEffect(() => {
    if (!engine || woke.current || engine.online || !engine.installed) return;
    woke.current = true;
    void voiceStudioApi.start().then(() => refreshStatus()).catch((e) => setError(errorText(e, "Could not start the voice engine.")));
  }, [engine, refreshStatus]);

  const isFull = engine?.kind === "full";
  const isRealtime = engine?.kind === "realtime";
  const busy = !!job && job.status === "running";
  const voiceNames = useMemo(() => voices.voices.map((v) => v.name), [voices]);

  async function pickModel(label: string) {
    setError(null);
    setSwitching(true);
    try {
      if (!engine?.online) await voiceStudioApi.start(label);
      else await voiceStudioApi.switchModel(label);
      await refreshStatus();
    } catch (e) { setError(errorText(e, "Could not switch the model.")); }
    finally { setSwitching(false); }
  }

  async function follow(id: string) {
    jobId.current = id;
    let after = 0;
    for (;;) {
      if (jobId.current !== id) return;
      try {
        const [state, chunks] = await Promise.all([voiceStudioApi.job(id), voiceStudioApi.chunks(id, after)]);
        after = chunks.next;
        chunks.chunks.forEach((c) => live.push(c, chunks.sample_rate));
        setJob(state);
        if (state.status !== "running") {
          if (state.status === "done" && state.clip) {
            setResult({ ...state.clip, audio_url: `/api/voice-studio/clips/${state.clip.id}/audio` });
            refreshClips();
          }
          if (state.status === "error") setError(state.error ?? "The voice could not be made.");
          return;
        }
      } catch (e) {
        setError(errorText(e, "Lost contact with the voice engine."));
        setJob(null);
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function generate() {
    setError(null);
    setResult(null);
    live.stop();
    try {
      const out = await voiceStudioApi.generate({
        script, num_speakers: count, speakers: speakers.slice(0, count), cfg_scale: cfg,
        inference_steps: steps, seed, disable_voice_cloning: noClone,
      });
      setJob({ id: out.id, kind: "podcast", status: "running", log: "", error: null, chunk_count: 0, streamed_seconds: 0, elapsed: 0, has_audio: false });
      void follow(out.id);
    } catch (e) { setError(errorText(e, "Could not start.")); }
  }

  async function speak() {
    setError(null);
    setResult(null);
    live.stop();
    try {
      const out = await voiceStudioApi.realtime({ text: rtText, voice: rtVoice, cfg_scale: rtCfg, steps: rtSteps });
      setJob({ id: out.id, kind: "realtime", status: "running", log: "", error: null, chunk_count: 0, streamed_seconds: 0, elapsed: 0, has_audio: false });
      void follow(out.id);
    } catch (e) { setError(errorText(e, "Could not start.")); }
  }

  async function stopJob() {
    if (!job) return;
    try { await voiceStudioApi.stopJob(job.id); } catch { /* it may already be finished */ }
    live.stop();
  }

  function previewVoice(name: string) {
    previewAudio.current?.pause();
    if (previewing === name) { setPreviewing(null); return; }
    const el = new Audio(voiceStudioApi.voiceAudioUrl(name));
    previewAudio.current = el;
    el.onended = () => setPreviewing(null);
    setPreviewing(name);
    void el.play().catch(() => setPreviewing(null));
  }

  async function addVoices(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    try {
      for (const file of Array.from(files)) await voiceStudioApi.addVoice(file);
      await loadEngineData();
    } catch (e) { setError(errorText(e, "That recording could not be added.")); }
  }

  function insertSpeaker(n: number) {
    setScript((s) => `${s}${s && !s.endsWith("\n") ? "\n" : ""}Speaker ${n}: `);
  }

  function loadExample(index: number) {
    const pick = examples[index];
    if (!pick) return;
    setCount(Math.min(4, Math.max(1, pick.num_speakers)));
    setScript(pick.script);
  }

  function randomExample() {
    if (!examples.length) return;
    const pick = examples[Math.floor(Math.random() * examples.length)];
    setCount(Math.min(4, Math.max(1, pick.num_speakers)));
    setScript(pick.script);
  }

  async function removeClip(clip: VoiceClip) {
    if (!(await confirmDialog("Delete this voice clip? It moves to the trash."))) return;
    try { await voiceStudioApi.deleteClip(clip.id); refreshClips(); }
    catch (e) { setError(errorText(e, "It could not be deleted.")); }
  }

  const engineBadge = !engine
    ? "Checking…"
    : !engine.installed ? "Not installed"
    : engine.loading ? "Loading model…"
    : engine.ready ? "Ready" : engine.online ? "Starting…" : "Asleep";

  return (
    <div className="mx-auto max-w-[1100px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-extrabold tracking-[-0.03em]">Voice Studio</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Turn a script into speech with up to four cloned voices, or speak instantly with a preset. Everything runs on this computer.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={engine?.ready ? "default" : "muted"}>{engineBadge}</Badge>
          {engine?.online ? (
            <Button size="sm" variant="outline" onClick={() => void voiceStudioApi.stop().then(refreshStatus)} title="Stops VibeVoice and gives the graphics card back to images and music">
              <Power className="h-4 w-4" aria-hidden="true" /> Stop engine
            </Button>
          ) : engine?.installed ? (
            <Button size="sm" onClick={() => void voiceStudioApi.start().then(refreshStatus)}><Power className="h-4 w-4" aria-hidden="true" /> Start engine</Button>
          ) : null}
        </div>
      </header>

      {engine && engine.installed && !engine.ready ? (
        <p role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          {engine.loading
            ? `Loading ${engine.loading}. This takes a minute or two, and it needs most of the graphics card, so images and songs wait their turn.`
            : "The voice engine is starting. It frees the graphics card for itself first, then loads its model."}
        </p>
      ) : null}
      {engine && !engine.installed ? (
        <EmptyState icon={AudioLines} title="VibeVoice is not installed here" body="Sovereign looks for it in F:\AI\VibeVoice." />
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Label htmlFor="vs-model" className="text-sm">Model</Label>
        <select
          id="vs-model" value={engine?.model ?? ""} disabled={switching || busy || !models.length}
          onChange={(e) => void pickModel(e.target.value)}
          className="h-10 min-w-[280px] rounded-md border border-input bg-background/40 px-3 text-sm"
        >
          {!engine?.model ? <option value="">{engine?.ready ? "—" : "Start the engine to choose"}</option> : null}
          {models.map((m) => <option key={m.label} value={m.label}>{m.label}</option>)}
        </select>
        {switching ? <Loader2 className="h-4 w-4 animate-spin text-primary" aria-label="Switching model" /> : null}
        <span className="text-xs text-muted-foreground">Only one model fits on the 8 GB card at a time.</span>
      </div>

      <div className="inline-flex rounded-lg border border-border bg-background/40 p-0.5" role="tablist" aria-label="Voice Studio sections">
        {([["conversation", "Conversation"], ["realtime", "Realtime"], ["library", `Library${clips.length ? ` (${clips.length})` : ""}`]] as const).map(([id, label]) => (
          <button
            key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={cn("h-9 rounded-md px-4 text-sm font-medium transition-colors", tab === id ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground")}
          >
            {label}
          </button>
        ))}
      </div>

      {error ? <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</p> : null}

      {tab === "conversation" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(280px,360px)_1fr]">
          <section className="space-y-5 rounded-2xl border border-border bg-card/60 p-4" aria-label="Speakers and settings">
            <div>
              <h2 className="text-sm font-semibold">Podcast settings</h2>
              <Label className="mt-3 flex items-center gap-2"><Users className="h-4 w-4" aria-hidden="true" /> Number of speakers</Label>
              <div className="mt-2 flex gap-2">
                {[1, 2, 3, 4].map((n) => (
                  <button key={n} type="button" aria-pressed={count === n} onClick={() => setCount(n)}
                    className={cn("h-9 w-9 rounded-full border text-sm", count === n ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground")}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
            {Array.from({ length: count }, (_, i) => (
              <div key={i} className="space-y-1.5">
                <Label htmlFor={`vs-speaker-${i}`}>Speaker {i + 1}</Label>
                <div className="flex gap-2">
                  <select
                    id={`vs-speaker-${i}`} value={speakers[i] ?? ""}
                    onChange={(e) => setSpeakers((s) => s.map((v, j) => (j === i ? e.target.value : v)))}
                    className="h-10 min-w-0 flex-1 rounded-md border border-input bg-background/40 px-2 text-sm"
                  >
                    <optgroup label="Your recordings">
                      {voices.voices.filter((v) => !v.preset).map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
                    </optgroup>
                    <optgroup label="Built-in voices">
                      {voices.voices.filter((v) => v.preset).map((v) => <option key={v.name} value={v.name}>{voiceLabel(v.name)}</option>)}
                    </optgroup>
                    {!voiceNames.includes(speakers[i]) ? <option value={speakers[i]}>{speakers[i]}</option> : null}
                  </select>
                  <Button size="icon" variant="outline" aria-label={`Preview ${speakers[i]}`} onClick={() => previewVoice(speakers[i])}>
                    {previewing === speakers[i] ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            ))}
            <div>
              <input ref={uploadRef} type="file" multiple accept="audio/*,.m4a,.aac" className="hidden" onChange={(e) => { void addVoices(e.target.files); e.target.value = ""; }} />
              <Button variant="outline" size="sm" onClick={() => uploadRef.current?.click()} disabled={!engine?.online}>
                <Upload className="h-4 w-4" aria-hidden="true" /> Add a recorded voice
              </Button>
              <p className="mt-1.5 text-xs text-muted-foreground">Clean WAV, MP3, FLAC, OGG, M4A or AAC. About 10 to 30 seconds of one person talking works best.</p>
            </div>
            <details className="rounded-lg border border-border p-3">
              <summary className="cursor-pointer text-sm font-medium">Advanced settings</summary>
              <div className="mt-3 space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="vs-cfg">CFG scale: {cfg.toFixed(2)}</Label>
                  <input id="vs-cfg" type="range" min={1} max={12} step={0.05} value={cfg} onChange={(e) => setCfg(Number(e.target.value))} className="w-full accent-primary" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="vs-steps">Inference steps: {steps}</Label>
                  <input id="vs-steps" type="range" min={1} max={50} step={1} value={steps} onChange={(e) => setSteps(Number(e.target.value))} className="w-full accent-primary" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="vs-seed">Seed (−1 for random)</Label>
                  <Input id="vs-seed" type="number" value={seed} onChange={(e) => setSeed(Math.max(-1, Math.round(Number(e.target.value))))} />
                </div>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={noClone} onChange={(e) => setNoClone(e.target.checked)} className="mt-1" />
                  <span>Disable voice cloning<span className="block text-xs text-muted-foreground">The model ignores the speaker recordings.</span></span>
                </label>
              </div>
            </details>
          </section>

          <section className="space-y-4" aria-label="Script and result">
            <div className="space-y-2">
              <Label htmlFor="vs-example">Example scripts</Label>
              <select
                id="vs-example" value="" onChange={(e) => loadExample(Number(e.target.value))} disabled={!examples.length}
                className="h-10 w-full rounded-md border border-input bg-background/40 px-2 text-sm"
              >
                <option value="">{examples.length ? "Pick an example podcast to load it…" : "Examples appear when the engine is ready"}</option>
                {examples.map((ex, i) => (
                  <option key={i} value={i}>{`${ex.name ?? `Example ${i + 1}`} · ${ex.num_speakers} speaker${ex.num_speakers === 1 ? "" : "s"}`}</option>
                ))}
              </select>
              <Label htmlFor="vs-script">Script</Label>
              <Textarea
                id="vs-script" value={script} onChange={(e) => setScript(e.target.value)} rows={12} maxLength={60000}
                placeholder={"Speaker 1: Welcome to the show!\nSpeaker 2: Thanks for having me.\n\nOr paste plain text and the lines are shared out among the speakers."}
              />
                <PromptAssist value={script} onChange={(t) => setScript(t.slice(0, 60000))} kind="podcast" context="Voice Studio conversation script" />
              <div className="flex flex-wrap items-center gap-2">
                {Array.from({ length: count }, (_, i) => (
                  <Button key={i} size="sm" variant="outline" type="button" onClick={() => insertSpeaker(i + 1)}>+ Speaker {i + 1}</Button>
                ))}
                <Button size="sm" variant="ghost" type="button" onClick={randomExample} disabled={!examples.length}>
                  <Dices className="h-4 w-4" aria-hidden="true" /> Random example
                </Button>
              </div>
            </div>

            {engine?.ready && !isFull ? (
              <p className="text-sm text-amber-200">Cloning voices needs the 7B or 1.5B model. Pick one above, or use the Realtime tab.</p>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={() => void generate()} disabled={!engine?.ready || !isFull || busy || !script.trim() || switching}>
                {busy && job?.kind === "podcast" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <AudioLines className="h-4 w-4" aria-hidden="true" />}
                {busy && job?.kind === "podcast" ? `Generating… ${fmt(job.elapsed)}` : "Generate voices"}
              </Button>
              {busy ? <Button size="lg" variant="destructive" onClick={() => void stopJob()}><Square className="h-4 w-4" aria-hidden="true" /> Stop</Button> : null}
            </div>

            {busy && job?.kind === "podcast" ? (
              <div role="status" className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
                <strong>LIVE STREAMING</strong>
                <span>Audio plays as it is generated{live.heard ? ` (${live.heard.toFixed(1)}s heard so far)` : ""}. It can pause briefly between chunks.</span>
              </div>
            ) : null}

            {job && job.kind === "podcast" ? (
              <div className="space-y-2 rounded-xl border border-border bg-card/50 p-3 text-sm">
                <p className="text-muted-foreground">
                  {job.status === "running" ? `Working… ${job.streamed_seconds ? `${job.streamed_seconds}s of audio so far. ` : ""}Audio starts playing as it arrives.` : job.status === "done" ? "Done. Saved to your library." : job.status === "stopped" ? "Stopped." : "Failed."}
                </p>
                {job.log ? <pre data-lenis-prevent className="max-h-40 overflow-y-auto whitespace-pre-wrap font-sans text-xs text-muted-foreground">{job.log}</pre> : null}
              </div>
            ) : null}
            {result && result.kind === "podcast" ? <ClipPlayer url={result.audio_url} name={`voice-studio-${result.id}.wav`} /> : null}
          </section>
        </div>
      ) : null}

      {tab === "realtime" ? (
        <section className="space-y-4 rounded-2xl border border-border bg-card/60 p-4" aria-label="Realtime voice">
          <p className="text-sm text-muted-foreground">One speaker, instant, with the preset voices. No cloning. This needs the Realtime 0.5B model.</p>
          {engine?.ready && !isRealtime ? (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              The loaded model is not the Realtime one.
              {models.find((m) => m.kind === "realtime") ? (
                <Button size="sm" onClick={() => void pickModel(models.find((m) => m.kind === "realtime")!.label)} disabled={switching || busy}>Switch to Realtime 0.5B</Button>
              ) : null}
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="rt-voice">Preset voice</Label>
              <select id="rt-voice" value={rtVoice} onChange={(e) => setRtVoice(e.target.value)} className="h-10 w-full rounded-md border border-input bg-background/40 px-2 text-sm">
                {voices.realtime.length ? voices.realtime.map((v) => <option key={v} value={v}>{v}</option>) : <option value={rtVoice}>{rtVoice}</option>}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rt-cfg">CFG scale: {rtCfg.toFixed(2)}</Label>
              <input id="rt-cfg" type="range" min={1} max={2} step={0.05} value={rtCfg} onChange={(e) => setRtCfg(Number(e.target.value))} className="w-full accent-primary" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rt-steps">Diffusion steps: {rtSteps}</Label>
              <input id="rt-steps" type="range" min={1} max={20} step={1} value={rtSteps} onChange={(e) => setRtSteps(Number(e.target.value))} className="w-full accent-primary" />
            </div>
          </div>
          <Textarea value={rtText} onChange={(e) => setRtText(e.target.value)} rows={5} maxLength={20000} aria-label="Text to speak" placeholder="Type what the voice should say…" />
          <PromptAssist value={rtText} onChange={(t) => setRtText(t.slice(0, 20000))} kind="narration" context="Voice Studio single-voice narration" />
          <Button size="lg" onClick={() => void speak()} disabled={!engine?.ready || !isRealtime || busy || !rtText.trim()}>
            {busy && job?.kind === "realtime" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <AudioLines className="h-4 w-4" aria-hidden="true" />}
            Speak
          </Button>
          {result && result.kind === "realtime" ? <ClipPlayer url={result.audio_url} name={`voice-studio-${result.id}.wav`} autoPlay /> : null}
        </section>
      ) : null}

      {tab !== "library" ? (
        <section className="space-y-3 rounded-2xl border border-border bg-card/40 p-4 text-sm" aria-label="Tips and limitations">
          <h2 className="text-sm font-semibold">Usage tips</h2>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Press <strong>Generate voices</strong> to start. Audio plays live as it is made, and the complete file appears with a download button when it finishes.</li>
            <li><strong>Stop</strong> interrupts a generation at any time.</li>
            <li>Not happy with it? Generate again, or change the CFG scale or seed in Advanced settings.</li>
            <li>The 7B model clones your recorded voices best. The Realtime 0.5B model is fastest but uses preset voices only.</li>
          </ul>
          <h2 className="pt-2 text-sm font-semibold">Risks and limitations</h2>
          <p className="text-muted-foreground">
            VibeVoice can produce outputs that are unexpected, biased or inaccurate, and it inherits any biases of its base model. High-quality synthetic
            speech can be misused for impersonation, fraud or disinformation. Use generated audio lawfully, check that transcripts are accurate, only clone
            voices you have the right to use, and say that audio is AI-generated when you share it.
          </p>
        </section>
      ) : null}

      {tab === "library" ? (
        clips.length === 0 ? (
          <EmptyState icon={AudioLines} title="No voice clips yet" body="Everything you generate is saved here, ready to replay or download." />
        ) : (
          <ul className="space-y-3">
            {clips.map((clip) => (
              <li key={clip.id} className="space-y-2 rounded-xl border border-border bg-card/60 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold">
                    {clip.kind === "realtime" ? `Realtime · ${clip.voice ?? "preset"}` : `${clip.speakers?.length ?? 1} speaker${(clip.speakers?.length ?? 1) === 1 ? "" : "s"}${clip.speakers?.length ? ` · ${clip.speakers.join(", ")}` : ""}`}
                  </p>
                  <span className="text-xs text-muted-foreground">
                    {fmt(clip.duration_seconds)} · {new Date(clip.created_at).toLocaleString()}{clip.render_seconds ? ` · made in ${fmt(clip.render_seconds)}` : ""}
                  </span>
                </div>
                {clip.script ? <p className="line-clamp-2 text-sm text-muted-foreground">{clip.script}</p> : null}
                <ClipPlayer url={clip.audio_url} name={`voice-studio-${clip.id}.wav`} />
                <div className="flex justify-end">
                  <Button size="sm" variant="ghost" onClick={() => void removeClip(clip)} aria-label="Delete clip"><Trash2 className="h-4 w-4" aria-hidden="true" /> Delete</Button>
                </div>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
