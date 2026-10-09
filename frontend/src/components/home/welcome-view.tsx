"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, Clapperboard, Mic, Music2, Pause, Play, Shirt, UserRound, Video } from "lucide-react";
import { TemplateCarousel } from "@/components/director/template-carousel";
import { BlurWords } from "@/components/motion/blur-words";
import { DotGrid } from "@/components/motion/dot-grid";
import { useScrollReveal, useSpotlight, useStaggerIn } from "@/components/motion/use-motion";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, AvatarJob, VoiceOption } from "@/lib/types";
import { cleanVoiceLabel, isCloneVoice } from "@/lib/voice-meta";
import { cn } from "@/lib/utils";

type Step = {
  id: string;
  title: string;
  body: string;
  icon: typeof UserRound;
  done: boolean;
  action: { label: string; href: string };
  extra?: React.ReactNode;
};

const PROMPTS = [
  { id: "ads", title: "Ads & promo", image: "/sovereign-ui/prompts/ads-reference.png",
    idea: "An upbeat 15-second promo for my business with a clear call to action." },
  { id: "launch", title: "Product launch", image: "/sovereign-ui/prompts/launch-reference.png",
    idea: "Announce a new product launch: what it is, who it helps, and how to get it." },
  { id: "tips", title: "Tips & how-to", image: "/sovereign-ui/prompts/tips-reference.jpeg",
    idea: "Three quick, practical tips that save my audience time every day." },
  { id: "edu", title: "Educational video", image: "/sovereign-ui/prompts/edu-reference.jpg",
    idea: "Explain one big idea in plain language with a simple everyday example." },
];

function useSetupData() {
  const [data, setData] = useState<{ name: string; avatars: AvatarAsset[]; voices: VoiceOption[]; jobs: AvatarJob[] } | null>(null);
  useEffect(() => {
    Promise.all([
      api.authMe().then((u) => u.name).catch(() => ""),
      api.listAvatars().catch(() => [] as AvatarAsset[]),
      api.getAudioMergeReadiness().then((r) => r.voices).catch(() => [] as VoiceOption[]),
      api.listAvatarJobs().catch(() => [] as AvatarJob[]),
    ]).then(([name, avatars, voices, jobs]) => setData({ name, avatars, voices, jobs }));
  }, []);
  return data;
}

function StepCard({ step, index, current }: { step: Step; index: number; current: boolean }) {
  const Icon = step.icon;
  const action = (
    <Link href={step.action.href} className={actionClass(current)}>
      {step.action.label} <ChevronRight className="h-4 w-4" />
    </Link>
  );
  return (
    <li
      data-spotlight
      className={cn(
        "spotlight flex flex-col rounded-2xl border bg-card/80 p-4",
        current ? "border-primary shadow-[0_0_0_1px_hsl(var(--primary)),0_0_32px_hsl(var(--primary)/0.18)]" : "border-border",
      )}
    >
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "flex h-5 w-5 items-center justify-center rounded-full",
            step.done ? "bg-primary text-primary-foreground" : "border-2 border-primary",
          )}
          aria-hidden="true"
        >
          {step.done ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
        </span>
        <span className="text-[11px] font-medium text-muted-foreground">{step.done ? "Complete" : `Step ${index + 1}`}</span>
      </div>
      <h3 className="mt-3 flex items-center gap-2 text-[15px] font-semibold">
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        {step.title}
      </h3>
      <p className="mt-1.5 flex-1 text-[13px] leading-relaxed text-muted-foreground">{step.body}</p>
      {step.extra ? <div className="mt-3">{step.extra}</div> : null}
      <div className="mt-4">{action}</div>
    </li>
  );
}

/** A small "play this voice" chip, like the one on HeyGen's setup card. */
function VoiceChip({ voice }: { voice: VoiceOption }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => () => audio.current?.pause(), []);
  async function toggle() {
    if (playing) { audio.current?.pause(); setPlaying(false); return; }
    try {
      const { url } = await api.voicePreview(voice.id);
      const el = new Audio(assetUrl(url) ?? undefined);
      el.onended = () => setPlaying(false);
      audio.current = el;
      setPlaying(true);
      await el.play();
    } catch {
      setPlaying(false);
    }
  }
  return (
    <button type="button" onClick={toggle} aria-label={`${playing ? "Stop" : "Play"} ${cleanVoiceLabel(voice)}`} className="flex w-full items-center gap-2 rounded-full bg-raised px-3 py-1.5 text-left text-xs font-medium hover:bg-raised/70">
      {playing ? <Pause className="h-3.5 w-3.5 text-primary" /> : <Play className="h-3.5 w-3.5 text-primary" />}
      <span className="truncate">{cleanVoiceLabel(voice)}</span>
    </button>
  );
}

function actionClass(current: boolean) {
  return cn(
    "inline-flex w-full items-center justify-center gap-1 rounded-xl px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    current ? "bg-primary text-primary-foreground hover:bg-primary/90" : "bg-raised text-foreground hover:bg-raised/70",
  );
}

export function WelcomeView() {
  const data = useSetupData();
  const avatars = data?.avatars ?? [];
  // Prefer the voice saved on one of your avatars; otherwise the first cloned voice.
  const savedVoiceId = avatars.find((a) => !a.group_id && a.default_voice_id)?.default_voice_id;
  const clones = (data?.voices ?? []).filter(isCloneVoice);
  const clone = clones.find((v) => v.id === savedVoiceId) ?? clones[0];
  const hasTwin = avatars.some((a) => !a.group_id);
  const hasLook = avatars.some((a) => a.group_id);
  const hasVideo = (data?.jobs ?? []).some((j) => j.status === "completed");

  const steps: Step[] = [
    { id: "twin", title: "Create your avatar", icon: UserRound, done: hasTwin,
      body: "Upload a video of yourself talking, or a clear photo. Outfit and background can be changed later.",
      action: { label: hasTwin ? "View my avatars" : "Create my avatar", href: hasTwin ? "/avatars" : "/avatars/new" } },
    { id: "voice", title: "Polish your voice", icon: Mic, done: Boolean(clone),
      body: "Hear the clone made from your recording, or record a cleaner sample and clone it again.",
      extra: clone ? <VoiceChip voice={clone} /> : undefined,
      action: { label: clone ? "Re-record voice" : "Clone my voice", href: "/voices" } },
    { id: "look", title: "Create a look", icon: Shirt, done: hasLook,
      body: "New outfits and scenes from one prompt, and your face stays locked.",
      action: { label: hasLook ? "View my looks" : "Create a look", href: hasLook ? "/avatars" : "/avatars/looks" } },
    { id: "video", title: "Make your first video", icon: Video, done: hasVideo,
      body: "Start from a script, a prompt, or scene by scene in the video editor.",
      action: { label: hasVideo ? "Make another video" : "Make a video", href: "/video-agent" } },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const currentIndex = steps.findIndex((s) => !s.done);

  const page = useRef<HTMLDivElement>(null);
  const stepList = useRef<HTMLOListElement>(null);
  useStaggerIn(stepList, data ? steps.length : 0);
  useScrollReveal(page);
  useSpotlight(page);

  return (
    <div ref={page} className="mx-auto max-w-[1000px]">
      <section className="relative isolate pb-10 pt-6 text-center">
        <div className="welcome-glow pointer-events-none absolute inset-x-0 -top-16 -z-10 h-72" aria-hidden="true" />
        <div className="pointer-events-none absolute inset-x-0 -top-6 bottom-0 -z-10 opacity-80 [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_72%)]" aria-hidden="true">
          <DotGrid />
        </div>
        <h1 className="text-4xl font-extrabold tracking-[-0.03em] sm:text-5xl">
          <BlurWords text="Welcome" />
          {data?.name ? (
            <>
              ,{" "}
              <BlurWords text={data.name} delay={0.25} className="bg-gradient-to-r from-sky-300 to-primary bg-clip-text text-transparent" />
            </>
          ) : null}
        </h1>
      </section>

      <section aria-labelledby="setup-heading" className="rounded-3xl border border-border bg-card/40 p-4 sm:p-5">
        <h2 id="setup-heading" className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground/90">
          <UserRound className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Finish your setup · {doneCount}/{steps.length}
        </h2>
        <ol ref={stepList} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, i) => (
            <StepCard key={step.id} step={step} index={i} current={i === currentIndex} />
          ))}
        </ol>
      </section>

      <section data-reveal aria-labelledby="director-heading" className="mt-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="director-heading" className="flex items-center gap-2 text-sm font-medium text-foreground/90">
            <Clapperboard className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            Direct your video
          </h2>
          <Link href="/director" className="text-xs text-muted-foreground hover:text-foreground">See all</Link>
        </div>
        <TemplateCarousel />
      </section>

      <section data-reveal aria-labelledby="prompts-heading" className="mt-10">
        <h2 id="prompts-heading" className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground/90">
          <Clapperboard className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Video prompts
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2">
          {PROMPTS.map((p) => (
            <li key={p.id}>
              <Link
                href={`/video-agent?prompt=${encodeURIComponent(p.idea)}`}
                className="group relative block aspect-[5/2] overflow-hidden rounded-2xl border border-border bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <img src={p.image} alt="" className="block h-full w-full object-cover" style={{ objectPosition: p.id === "ads" ? "center 45%" : "center top" }} />
                <span className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/10 to-transparent" aria-hidden="true" />
                <span className="absolute left-5 top-4 max-w-[60%] text-2xl font-extrabold leading-[1.05] tracking-[-0.02em] text-white drop-shadow sm:text-3xl">
                  {p.title}
                </span>
                <span className="absolute bottom-4 left-5 inline-flex items-center gap-1 rounded-full border border-white/30 bg-white/15 px-4 py-1.5 text-sm font-medium text-white backdrop-blur">
                  Create now <ChevronRight className="h-4 w-4" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section data-reveal aria-labelledby="music-heading" className="mt-10">
        <h2 id="music-heading" className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground/90">
          <Music2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Music
        </h2>
        <Link
          href="/music-lab"
          className="group relative block aspect-[5/2] overflow-hidden rounded-2xl border border-border bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:aspect-[5/1]"
        >
          <img src="/home/music-lab.png" alt="" className="block h-full w-full object-cover" />
          <span className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/10 to-transparent" aria-hidden="true" />
          <span className="absolute left-5 top-4 max-w-[60%] text-2xl font-extrabold leading-[1.05] tracking-[-0.02em] text-white drop-shadow sm:text-3xl">
            Music Lab
          </span>
          <span className="absolute bottom-4 left-5 inline-flex items-center gap-1 rounded-full border border-white/30 bg-white/15 px-4 py-1.5 text-sm font-medium text-white backdrop-blur">
            Create a song <ChevronRight className="h-4 w-4" />
          </span>
        </Link>
      </section>
    </div>
  );
}
