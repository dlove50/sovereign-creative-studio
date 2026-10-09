"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Captions, Check, ChevronRight, Clock, Loader2, Monitor, Mic, Palette, Paperclip, PenLine, Sparkles, UserRound, X } from "lucide-react";

import { defaultVoiceFor } from "@/lib/avatar-voice";
import { CaptionedVideo } from "@/components/media/captioned-video";
import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, AvatarJob, BrandKit, VoiceOption } from "@/lib/types";
import { cn } from "@/lib/utils";

const LENGTHS = [15, 30, 60] as const;
const RENDER_SECONDS_PER_SECOND = 55; // measured on the RTX 5070 Ti at 480x832
const POLL_MS = 4000;

type Mode = "autopilot" | "review";
type Stage = "idle" | "writing" | "review" | "voice" | "video" | "done" | "failed";
type Idea = { title: string; image: string; prompt: string; seconds: number };

const P = "/sovereign-ui/prompts/";
const L = "/sovereign-ui/looks/";
const TABS: { id: string; label: string; heading: string; ideas: Idea[] }[] = [
  { id: "for-you", label: "For you", heading: "Popular ideas", ideas: [
    { title: "Tips & how-to", image: `${P}tips.webp`, seconds: 30, prompt: "Three quick, practical tips for people who want to get more done in less time." },
    { title: "Product launch", image: `${P}launch.webp`, seconds: 30, prompt: "Announce a new product launch with excitement: what it is, who it helps, and how to get it." },
    { title: "Ads & promo", image: `${P}ads.webp`, seconds: 15, prompt: "An upbeat 15-second promo for a small local business with a clear call to action." },
    { title: "Educational video", image: `${P}edu.webp`, seconds: 60, prompt: "Explain one big idea in plain language with a simple everyday example." },
  ] },
  { id: "brand", label: "Personal brand", heading: "Build your personal brand", ideas: [
    { title: "Expert explainer", image: `${L}professor.webp`, seconds: 60, prompt: "Explain a common misconception in my field and what people should know instead." },
    { title: "Meet me", image: `${L}creator-studio.webp`, seconds: 30, prompt: "A friendly introduction: who I am, what I do, and why people follow my work." },
    { title: "News brief", image: `${L}presenter.webp`, seconds: 30, prompt: "A short, neutral news-style update about a recent change in my industry." },
    { title: "Sales outreach", image: `${L}corporate.webp`, seconds: 30, prompt: "A personal video message to a potential client explaining how I can help them." },
  ] },
  { id: "learning", label: "Courses & learning", heading: "Make learning videos that stick", ideas: [
    { title: "Course lesson", image: `${L}professor.webp`, seconds: 60, prompt: "Lesson one of a beginner course: what we'll cover and the first key concept." },
    { title: "Micro-lesson", image: `${P}edu.webp`, seconds: 30, prompt: "A one-minute micro-lesson that teaches a single useful skill step by step." },
    { title: "Skills refresher", image: `${L}slate.webp`, seconds: 30, prompt: "A quick refresher of three things people forget about a common skill." },
  ] },
  { id: "training", label: "Corporate training", heading: "Turn know-how into training", ideas: [
    { title: "Team onboarding", image: `${L}corporate.webp`, seconds: 60, prompt: "Welcome new team members: how the first week works and who to ask for help." },
    { title: "Policy explainer", image: `${L}law.webp`, seconds: 30, prompt: "Explain a workplace policy clearly and why it matters, without legal jargon." },
    { title: "Internal update", image: `${L}minimal.webp`, seconds: 30, prompt: "A short internal update on this month's progress and next month's priorities." },
  ] },
  { id: "creators", label: "Creator channels", heading: "Make videos for your channel", ideas: [
    { title: "Channel intro", image: `${L}creator-studio.webp`, seconds: 15, prompt: "A punchy channel intro telling viewers what the channel is about and why to subscribe." },
    { title: "Weekly tips", image: `${P}tips.webp`, seconds: 30, prompt: "This week's top three tips for my audience, upbeat and quick." },
    { title: "Product review", image: `${P}launch.webp`, seconds: 60, prompt: "An honest review of a product: what I liked, what I didn't, and who should buy it." },
  ] },
  { id: "real-estate", label: "Real estate", heading: "Sell homes with video", ideas: [
    { title: "Market update", image: `${L}real-estate.webp`, seconds: 30, prompt: "A local housing market update for buyers and sellers this month." },
    { title: "Listing spotlight", image: `${L}coastal.webp`, seconds: 30, prompt: "Spotlight a new home listing: the best three features and how to book a viewing." },
    { title: "Meet the agent", image: `${L}real-estate.webp`, seconds: 30, prompt: "Introduce myself as a real estate agent and how I help clients buy or sell." },
  ] },
];

function Chip({ icon: Icon, label, children }: { icon: typeof UserRound; label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 items-center gap-2 rounded-xl border border-border bg-raised/60 px-2.5 py-1.5">
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="flex min-w-0 flex-col">
        <span className="text-[10px] text-muted-foreground">{label}</span>
        {children}
      </span>
    </label>
  );
}

type Brand = { id: string; name: string; kit: BrandKit };

/** Short instruction block that makes the script follow a brand system. */
export function brandContext(brand: Brand | undefined): string {
  if (!brand) return "";
  const { kit } = brand;
  const parts = [
    kit.brand_name || brand.name ? `Brand: ${kit.brand_name || brand.name}.` : "",
    kit.brand_voice ? `Voice and tone: ${kit.brand_voice}.` : "",
    kit.target_audience ? `Audience: ${kit.target_audience}.` : "",
    kit.product_positioning ? `What it offers: ${kit.product_positioning}.` : "",
    kit.negative_keywords ? `Avoid: ${kit.negative_keywords}.` : "",
  ].filter(Boolean);
  return parts.length ? `Write in line with this brand. ${parts.join(" ")}` : "";
}

const selectClass = "max-w-[180px] truncate bg-transparent text-xs font-medium focus:outline-none";

export function VideoAgentView() {
  const [avatars, setAvatars] = useState<AvatarAsset[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [avatarId, setAvatarId] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [seconds, setSeconds] = useState<number>(30);
  const [instructions, setInstructions] = useState("");
  const [shape, setShape] = useState<"auto" | "portrait" | "landscape">("auto");
  const [captionsOn, setCaptionsOn] = useState(true);
  const [knowledge, setKnowledge] = useState<{ name: string; text: string }[]>([]);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const knowledgeInput = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<Mode>("review");
  const [brands, setBrands] = useState<Brand[]>([]);
  const [brandId, setBrandId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [tab, setTab] = useState(TABS[0].id);
  const [stage, setStage] = useState<Stage>("idle");
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [job, setJob] = useState<AvatarJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fromLink = new URLSearchParams(window.location.search).get("prompt");
    if (fromLink) setPrompt(fromLink.slice(0, 2000));
    api.listAvatars().then((all) => {
      const photos = all.filter((a) => a.avatar_type === "photo_avatar" && a.source_file_path);
      setAvatars(photos);
      setAvatarId((cur) => cur || photos[0]?.id || "");
    }).catch(() => setAvatars([]));
    api.listProjects().then(async (projects) => {
      const kits = await Promise.all(projects.map((p) => api.getBrandKit(p.id).catch(() => null)));
      setBrands(projects.flatMap((p, i) => {
        const kit = kits[i];
        return kit && Object.values(kit).some((v) => v && String(v).trim()) ? [{ id: p.id, name: p.name, kit }] : [];
      }));
    }).catch(() => setBrands([]));
    api.getAudioMergeReadiness().then((r) => {
      setVoices(r.voices);
      const clone = r.voices.find((v) => v.id.startsWith("vibevoice:") && !/_(man|woman)/.test(v.id));
      setVoiceId((cur) => cur || clone?.id || r.voices.find((v) => v.is_default)?.id || r.voices[0]?.id || "");
    }).catch(() => setVoices([]));
  }, []);

  // Picking an avatar switches to the voice saved on it (the user can still change it afterwards).
  useEffect(() => {
    const saved = defaultVoiceFor(avatars.find((a) => a.id === avatarId), avatars, voices);
    if (saved) setVoiceId(saved);
  }, [avatarId, avatars, voices]);

  // Follow the talking-avatar render until it finishes.
  useEffect(() => {
    if (stage !== "video" || !job) return;
    const timer = setInterval(async () => {
      try {
        const next = await api.getAvatarJob(job.id);
        setJob(next);
        if (next.status === "completed") setStage("done");
        if (next.status === "failed" || next.status === "setup_required") {
          setError(next.error_message || "The video could not be rendered.");
          setStage("failed");
        }
      } catch { /* keep polling through brief hiccups */ }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [stage, job?.id]);

  const avatar = avatars.find((a) => a.id === avatarId);
  const words = script.split(/\s+/).filter(Boolean).length;
  const estMinutes = Math.max(1, Math.round(((words / 2.5) * RENDER_SECONDS_PER_SECOND) / 60));
  const busy = stage === "writing" || stage === "voice" || stage === "video";
  const tabData = useMemo(() => TABS.find((t) => t.id === tab)!, [tab]);

  async function makeVideo(text: string) {
    if (!avatarId) { setError("Add an avatar first, then try again."); setStage("failed"); return; }
    setError(null);
    try {
      setStage("voice");
      const voice = await api.generateVoiceGreeting({ script_text: text, tts_voice_id: voiceId || undefined });
      setStage("video");
      setJob(await api.createTalkingAvatar({ avatar_id: avatarId, voice_id: voice.id, script_text: text, ...(shape === "auto" ? {} : { avatar_preset: `${shape}_480p` }) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The video could not be started.");
      setStage("failed");
    }
  }

  async function addKnowledge(file: File) {
    setKnowledgeError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const out = await api.extractKnowledge(form);
      setKnowledge((all) => [...all, { name: out.name, text: out.text }].slice(0, 3));
    } catch (e) {
      setKnowledgeError(e instanceof Error ? e.message : "That file could not be read.");
    }
  }

  async function submit() {
    if (!prompt.trim() || busy) return;
    setError(null);
    setJob(null);
    setStage("writing");
    try {
      const parts = [
        prompt.trim(),
        brandContext(brands.find((b) => b.id === brandId)),
        instructions.trim() ? `Extra instructions: ${instructions.trim()}` : "",
        ...knowledge.map((k) => `Use only facts from this material (${k.name}): ${k.text}`),
      ].filter(Boolean);
      const out = await api.writeAgentScript({ prompt: parts.join(" ").slice(0, 8000), seconds });
      setTitle(out.title);
      setScript(out.script);
      if (mode === "autopilot") await makeVideo(out.script);
      else setStage("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The script could not be written.");
      setStage("failed");
    }
  }

  const steps: { id: Stage; label: string }[] = [
    { id: "writing", label: "Writing the script" },
    { id: "voice", label: "Recording the voice" },
    { id: "video", label: "Animating your avatar" },
    { id: "done", label: "Video ready" },
  ];
  const order: Stage[] = ["writing", "review", "voice", "video", "done"];
  const reached = (s: Stage) => order.indexOf(stage) >= order.indexOf(s);

  return (
    <div className="mx-auto max-w-[1040px]">
      <h1 className="pt-6 text-center text-4xl font-extrabold tracking-[-0.03em]">What do you want to create?</h1>
      <p className="mt-3 text-center"><Link href="/cinematic-planner" className="text-primary underline underline-offset-4">Plan a cinematic story with characters and multiple shots</Link></p>

      <section className="mt-7 rounded-3xl border border-primary/40 bg-card/70 p-4 shadow-[0_0_40px_hsl(var(--primary)/0.12)]">
        <div className="flex flex-wrap gap-2">
          <Chip icon={UserRound} label="Avatar">
            <select value={avatarId} onChange={(e) => setAvatarId(e.target.value)} className={selectClass} aria-label="Avatar">
              {avatars.length === 0 ? <option value="">No avatars yet</option> : null}
              {avatars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </Chip>
          <Chip icon={Mic} label="Voice">
            <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)} className={selectClass} aria-label="Voice">
              {voices.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </Chip>
          <Chip icon={Palette} label="Brand">
            <select value={brandId} onChange={(e) => setBrandId(e.target.value)} className={selectClass} aria-label="Brand">
              <option value="">None</option>
              {brands.map((b) => <option key={b.id} value={b.id}>{b.kit.brand_name || b.name}</option>)}
            </select>
          </Chip>
          <Chip icon={Monitor} label="Shape">
            <select value={shape} onChange={(e) => setShape(e.target.value as typeof shape)} className={selectClass} aria-label="Shape">
              <option value="auto">Auto</option>
              <option value="portrait">Portrait 9:16</option>
              <option value="landscape">Landscape 16:9</option>
            </select>
          </Chip>
          <Chip icon={Captions} label="Captions">
            <select value={captionsOn ? "on" : "off"} onChange={(e) => setCaptionsOn(e.target.value === "on")} className={selectClass} aria-label="Captions">
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
          </Chip>
          <Chip icon={Clock} label="Length">
            <select value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} className={selectClass} aria-label="Length">
              {LENGTHS.map((s) => <option key={s} value={s}>{s} seconds</option>)}
            </select>
          </Chip>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input value={instructions} onChange={(e) => setInstructions(e.target.value.slice(0, 500))} aria-label="Instructions" placeholder="Instructions (optional): tone, must-include points, things to avoid" className="h-9 min-w-[240px] flex-1 rounded-full border border-border bg-background px-4 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          <button type="button" onClick={() => knowledgeInput.current?.click()} disabled={knowledge.length >= 3} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-border px-3 text-xs hover:bg-raised disabled:opacity-50">
            <Paperclip className="h-3.5 w-3.5" /> Add knowledge
          </button>
          <input ref={knowledgeInput} type="file" accept=".pdf,.pptx,.txt,.md" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void addKnowledge(f); }} />
          {knowledge.map((k) => (
            <span key={k.name} className="inline-flex items-center gap-1.5 rounded-full bg-raised px-3 py-1 text-xs">
              {k.name.slice(0, 24)}
              <button type="button" aria-label={`Remove ${k.name}`} onClick={() => setKnowledge((all) => all.filter((x) => x.name !== k.name))} className="text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
        {knowledgeError ? <p className="mt-2 text-xs text-destructive">{knowledgeError}</p> : null}
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }}
          rows={3}
          maxLength={2000}
          aria-label="Describe your video"
          placeholder="Describe the video you want: the topic, who it's for, and the feeling. I'll write the script."
          className="mt-3 w-full resize-none bg-transparent text-[15px] placeholder:text-muted-foreground/70 focus:outline-none"
        />
        <div className="flex items-center justify-end gap-2">
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} aria-label="Mode" className="h-9 rounded-full border border-border bg-background px-3 text-xs">
            <option value="review">Review script first</option>
            <option value="autopilot">Auto-pilot</option>
          </select>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !prompt.trim()}
            className="inline-flex h-9 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {stage === "writing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Submit
          </button>
        </div>
      </section>

      {stage !== "idle" ? (
        <section className="mt-5 rounded-3xl border border-border bg-card/60 p-5" aria-live="polite">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-lg font-bold">{title || "Your video"}</h2>
            {!busy ? (
              <button type="button" onClick={() => { setStage("idle"); setJob(null); setError(null); }} aria-label="Close" className="rounded-full p-1 text-muted-foreground hover:bg-raised"><X className="h-4 w-4" /></button>
            ) : null}
          </div>
          <ol className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
            {steps.map((s) => {
              const active = stage === s.id;
              const done = reached(s.id) && !active && stage !== "failed";
              return (
                <li key={s.id} className={cn("flex items-center gap-2 text-sm", active || done ? "text-foreground" : "text-muted-foreground")}>
                  <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border", done ? "border-primary bg-primary text-primary-foreground" : active ? "border-primary" : "border-border")}>
                    {done ? <Check className="h-3 w-3" strokeWidth={3} /> : active ? <Loader2 className="h-3 w-3 animate-spin text-primary" /> : null}
                  </span>
                  {s.label}
                </li>
              );
            })}
          </ol>

          {stage === "writing" ? <p className="mt-4 text-sm text-muted-foreground">Local Qwen is writing your script. This takes about a minute.</p> : null}

          {script && (stage === "review" || stage === "voice" || stage === "video" || stage === "done" || stage === "failed") ? (
            <div className="mt-4">
              <label htmlFor="agent-script" className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <PenLine className="h-3.5 w-3.5" /> Script · {words} words · about {Math.round(words / 2.5)} seconds
              </label>
              <textarea
                id="agent-script"
                value={script}
                onChange={(e) => setScript(e.target.value)}
                readOnly={stage !== "review"}
                rows={5}
                maxLength={2000}
                className="mt-1.5 w-full rounded-2xl border border-border bg-background/60 px-4 py-3 text-[15px] leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              {stage === "review" ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <span className="text-xs text-muted-foreground">Rendering takes about {estMinutes} min on your GPU.</span>
                  <span className="flex gap-2">
                    <button type="button" onClick={submit} className="rounded-full border border-border px-4 py-2 text-sm hover:bg-raised">Rewrite</button>
                    <button type="button" onClick={() => makeVideo(script)} disabled={!script.trim()} className="inline-flex items-center gap-1 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
                      Make video <ChevronRight className="h-4 w-4" />
                    </button>
                  </span>
                </div>
              ) : null}
            </div>
          ) : null}

          {stage === "voice" ? <p className="mt-3 text-sm text-muted-foreground">Recording the voice. Cloned voices take about 15 seconds per second of speech.</p> : null}
          {stage === "video" ? (
            <p className="mt-3 text-sm text-muted-foreground">
              Animating {avatar?.name ?? "your avatar"} in 3-second pieces, about {estMinutes} min. You can leave this page; the finished video appears in Recents.
            </p>
          ) : null}
          {stage === "done" && job?.output_video_path ? (
            <div className="mt-4">
              <CaptionedVideo src={job.output_video_path} auto={captionsOn} className="max-h-[480px]">
                <Link href="/avatars/create" className="rounded-full border border-border px-5 py-2 text-center text-sm hover:bg-raised">Fine-tune in Make a video</Link>
              </CaptionedVideo>
            </div>
          ) : null}
          {stage === "failed" && error ? <p className="mt-4 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
        </section>
      ) : null}

      <div className="mt-10 flex justify-center">
        <div role="tablist" aria-label="Video ideas" className="flex max-w-full gap-1 overflow-x-auto rounded-full border border-border bg-card/60 p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn("shrink-0 rounded-full px-4 py-1.5 text-sm transition-colors", tab === t.id ? "bg-raised font-semibold text-foreground ring-1 ring-primary/60" : "text-muted-foreground hover:text-foreground")}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <h2 className="mb-4 mt-7 flex items-center gap-2 text-lg font-bold"><Sparkles className="h-4 w-4 text-primary" /> {tabData.heading}</h2>
      <ul className="grid grid-cols-2 gap-4 md:grid-cols-3">
        {tabData.ideas.map((idea) => (
          <li key={idea.title}>
            <button
              type="button"
              onClick={() => { setPrompt(idea.prompt); setSeconds(idea.seconds); window.scrollTo({ top: 0, behavior: "smooth" }); }}
              className="group relative block aspect-[16/10] w-full overflow-hidden rounded-2xl border border-border text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <img src={idea.image} alt="" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
              <span className="absolute inset-0 bg-gradient-to-b from-black/55 via-transparent to-black/40" aria-hidden="true" />
              <span className="absolute left-4 top-3 max-w-[70%] text-2xl font-extrabold leading-[1.05] tracking-[-0.02em] text-white drop-shadow">{idea.title}</span>
              <span className="absolute bottom-3 left-4 inline-flex items-center gap-1 text-sm text-white/90">Create yours <ChevronRight className="h-4 w-4" /></span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
