"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, Clapperboard, Mic, Play, Shirt, UserRound, Video } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type { AvatarAsset, AvatarJob, VoiceAsset } from "@/lib/types";
import { cn } from "@/lib/utils";

// VibeVoice Studio runs beside Sovereign; recording a new voice sample happens there.
const VIBEVOICE_URL = "http://127.0.0.1:8010";

type Step = {
  id: string;
  title: string;
  body: string;
  icon: typeof UserRound;
  done: boolean;
  action: { label: string; href: string; external?: boolean };
};

const PROMPTS = [
  { id: "ads", title: "Ads & promo", image: "/sovereign-ui/prompts/ads.webp",
    idea: "An upbeat 15-second promo for my business with a clear call to action." },
  { id: "launch", title: "Product launch", image: "/sovereign-ui/prompts/launch.webp",
    idea: "Announce a new product launch: what it is, who it helps, and how to get it." },
  { id: "tips", title: "Tips & how-to", image: "/sovereign-ui/prompts/tips.webp",
    idea: "Three quick, practical tips that save my audience time every day." },
  { id: "edu", title: "Educational video", image: "/sovereign-ui/prompts/edu.webp",
    idea: "Explain one big idea in plain language with a simple everyday example." },
];

function useSetupData() {
  const [data, setData] = useState<{ name: string; avatars: AvatarAsset[]; voices: VoiceAsset[]; jobs: AvatarJob[] } | null>(null);
  useEffect(() => {
    Promise.all([
      api.authMe().then((u) => u.name).catch(() => ""),
      api.listAvatars().catch(() => [] as AvatarAsset[]),
      api.listVoices().catch(() => [] as VoiceAsset[]),
      api.listAvatarJobs().catch(() => [] as AvatarJob[]),
    ]).then(([name, avatars, voices, jobs]) => setData({ name, avatars, voices, jobs }));
  }, []);
  return data;
}

function StepCard({ step, index, current }: { step: Step; index: number; current: boolean }) {
  const Icon = step.icon;
  const action = step.action.external ? (
    <a href={step.action.href} target="_blank" rel="noreferrer" className={actionClass(current)}>
      {step.action.label} <ChevronRight className="h-4 w-4" />
    </a>
  ) : (
    <Link href={step.action.href} className={actionClass(current)}>
      {step.action.label} <ChevronRight className="h-4 w-4" />
    </Link>
  );
  return (
    <li
      className={cn(
        "flex flex-col rounded-2xl border bg-card/80 p-4",
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
      <div className="mt-4">{action}</div>
    </li>
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
  const clone = (data?.voices ?? []).find((v) => v.provider === "vibevoice" && v.sample_file_path);
  const hasTwin = avatars.some((a) => !a.group_id);
  const hasLook = avatars.some((a) => a.group_id);
  const hasVideo = (data?.jobs ?? []).some((j) => j.status === "completed");

  const steps: Step[] = [
    { id: "twin", title: "Create your avatar", icon: UserRound, done: hasTwin,
      body: "Upload a clear photo of yourself. Outfit and background can be changed later.",
      action: { label: hasTwin ? "View my avatar" : "Upload a photo", href: "/avatars" } },
    { id: "voice", title: "Clone your voice", icon: Mic, done: Boolean(clone),
      body: "Record a short sample in VibeVoice Studio, then generate a clip in your own voice.",
      action: clone ? { label: "Record a new sample", href: VIBEVOICE_URL, external: true } : { label: "Open VibeVoice Studio", href: VIBEVOICE_URL, external: true } },
    { id: "look", title: "Create a look", icon: Shirt, done: hasLook,
      body: "New outfits and scenes from one prompt, with your face kept the same.",
      action: { label: hasLook ? "View my looks" : "Create a look", href: hasLook ? "/avatars" : "/avatars/looks" } },
    { id: "video", title: "Make your first video", icon: Video, done: hasVideo,
      body: "Type a script, pick a voice and a look, and your avatar says it.",
      action: { label: hasVideo ? "Make another video" : "Make a video", href: "/video-agent" } },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const currentIndex = steps.findIndex((s) => !s.done);

  return (
    <div className="mx-auto max-w-[1120px]">
      <section className="relative isolate pb-10 pt-6 text-center">
        <div className="welcome-glow pointer-events-none absolute inset-x-0 -top-16 -z-10 h-72" aria-hidden="true" />
        <h1 className="text-4xl font-extrabold tracking-[-0.03em] sm:text-5xl">
          Welcome{data?.name ? "," : ""}{" "}
          <span className="bg-gradient-to-r from-sky-300 to-primary bg-clip-text text-transparent">{data?.name ?? ""}</span>
        </h1>
      </section>

      <section aria-labelledby="setup-heading" className="rounded-3xl border border-border bg-card/40 p-4 sm:p-5">
        <h2 id="setup-heading" className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground/90">
          <UserRound className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Finish your setup · {doneCount}/{steps.length}
        </h2>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((step, i) => (
            <StepCard key={step.id} step={step} index={i} current={i === currentIndex} />
          ))}
        </ol>
        {clone?.sample_file_path ? (
          <div className="mt-3 flex items-center gap-3 rounded-xl bg-raised/60 px-3 py-2 text-sm">
            <Play className="h-4 w-4 text-primary" aria-hidden="true" />
            <span className="shrink-0 text-muted-foreground">Latest clip in your voice</span>
            <audio controls src={assetUrl(clone.sample_file_path) ?? undefined} className="h-8 w-full max-w-md" />
          </div>
        ) : null}
      </section>

      <section aria-labelledby="prompts-heading" className="mt-10">
        <h2 id="prompts-heading" className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground/90">
          <Clapperboard className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Video prompts
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2">
          {PROMPTS.map((p) => (
            <li key={p.id}>
              <Link
                href={`/video-agent?prompt=${encodeURIComponent(p.idea)}`}
                className="group relative block aspect-[16/7] overflow-hidden rounded-2xl border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <img src={p.image} alt="" width={960} height={420} className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
                <span className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/10 to-transparent" aria-hidden="true" />
                <span className="absolute left-5 top-4 max-w-[60%] text-3xl font-extrabold leading-[1.05] tracking-[-0.02em] text-white drop-shadow sm:text-4xl">
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
    </div>
  );
}
