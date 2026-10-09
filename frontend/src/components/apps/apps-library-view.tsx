"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ChevronRight, Clapperboard, FileText, Film, ImageIcon, Languages, Layers, MessagesSquare, Mic,
  MousePointerClick, Music2, PersonStanding, ScanText, Scissors, Search, Sparkles, Type, Video, Wand2, ZoomIn,
  type LucideIcon,
} from "lucide-react";

import { api } from "@/lib/api";
import { ADMIN_NAV, CREATOR_NAV } from "@/lib/navigation";
import { cn } from "@/lib/utils";

type Category = "create" | "enhance" | "edit" | "interactive";
type AppEntry = { name: string; blurb: string; icon: LucideIcon; category: Category; href?: string };

const TABS: { id: "all" | Category; label: string }[] = [
  { id: "all", label: "All apps" },
  { id: "create", label: "Create" },
  { id: "enhance", label: "Enhance" },
  { id: "edit", label: "Edit" },
  { id: "interactive", label: "Interactive" },
];

const FEATURED = [
  { name: "AI video generator", href: "/videos", image: "/sovereign-ui/apps/generator.webp", tint: "text-amber-200" },
  { name: "Talking avatar", href: "/avatars/create", image: "/sovereign-ui/apps/podcast.webp", tint: "text-sky-300" },
  { name: "Transcribe video", href: "/video-to-text", image: "/sovereign-ui/apps/cleanup.webp", tint: "text-amber-100" },
];

// Apps without an href are planned; they are listed so the roadmap is visible,
// but never rendered as links.
const APPS: AppEntry[] = [
  { name: "AI Studio", blurb: "Start with a template or build an avatar video scene by scene.", icon: Clapperboard, category: "create", href: "/movies" },
  { name: "Cinematic planner", blurb: "Plan characters, locations and shots, then assemble completed clips.", icon: Film, category: "create", href: "/cinematic-planner" },
  { name: "Cloud studio", blurb: "HeyGen profiles and ElevenLabs speech, sounds, transcription and dubbing.", icon: Sparkles, category: "create", href: "/cloud-studio" },
  { name: "Talking avatar", blurb: "Your photo speaks your script in your cloned voice.", icon: PersonStanding, category: "create", href: "/avatars/create" },
  { name: "Scene by scene", blurb: "Plan a video as a storyboard of scenes.", icon: Clapperboard, category: "create", href: "/storyboard-studio" },
  { name: "Quick Chain", blurb: "Image, motion, upscale and voice in one guided flow.", icon: Wand2, category: "create", href: "/chain" },
  { name: "AI video generator", blurb: "Turn a photo and a prompt into a short video clip.", icon: Video, category: "create", href: "/videos" },
  { name: "Image studio", blurb: "Make or edit images from a text prompt.", icon: ImageIcon, category: "create", href: "/create" },
  { name: "Director", blurb: "Pick a format (short film, ad, trailer, micro drama) and get a finished video with voice and music.", icon: Clapperboard, category: "create", href: "/director" },
  { name: "Music Lab", blurb: "Make a full song from an idea or your own lyrics, locally with YuE2.", icon: Music2, category: "create", href: "/music-lab" },
  { name: "Film studio", blurb: "Longer cinematic sequences from your clips.", icon: Film, category: "create", href: "/film-studio" },
  { name: "Video agent", blurb: "Describe a video and let local AI write and build it.", icon: Sparkles, category: "create", href: "/video-agent" },
  { name: "Video podcast", blurb: "Two avatars in conversation from one script.", icon: MessagesSquare, category: "create", href: "/podcast" },
  { name: "Slides to video", blurb: "Narrate a PDF or slide deck with your avatar.", icon: FileText, category: "create", href: "/slides" },
  { name: "Batch videos", blurb: "Make many avatar videos from a spreadsheet.", icon: Layers, category: "create", href: "/batch" },
  { name: "Upscale video", blurb: "Sharpen a finished clip to a higher resolution.", icon: ZoomIn, category: "enhance", href: "/chain" },
  { name: "Speech cleanup", blurb: "Cut long pauses and filler words automatically.", icon: Mic, category: "enhance", href: "/speech-cleanup" },
  { name: "Translate video", blurb: "Get subtitles in another language, or have your avatar say the translation.", icon: Languages, category: "enhance", href: "/translate" },
  { name: "Transcribe video", blurb: "Get a text transcript and summary of any video.", icon: Type, category: "edit", href: "/video-to-text" },
  { name: "OCR studio", blurb: "Pull text out of images and scanned pages.", icon: ScanText, category: "edit", href: "/ocr-studio" },
  { name: "Auto clips", blurb: "Find the best moments in a long video and cut shorts.", icon: Scissors, category: "edit", href: "/auto-clips" },
  { name: "Interactive video", blurb: "Videos with choices that branch to different scenes.", icon: MousePointerClick, category: "interactive", href: "/interactive" },
  { name: "Screen recorder", blurb: "Record your screen and voice, then use the clip in videos and lessons.", icon: Video, category: "interactive", href: "/record" },
];

function AppRow({ app }: { app: AppEntry }) {
  const Icon = app.icon;
  const body = (
    <>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-raised text-muted-foreground">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-semibold">
          {app.name}
          {app.href ? null : <span className="rounded-full bg-raised px-2 py-0.5 text-[10px] font-medium text-muted-foreground">Coming next</span>}
        </span>
        <span className="block truncate text-[13px] text-muted-foreground">{app.blurb}</span>
      </span>
    </>
  );
  const shell = "flex items-center gap-4 rounded-full border border-border bg-card/60 px-4 py-3";
  return app.href ? (
    <Link href={app.href} className={cn(shell, "transition-colors hover:border-primary/60 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}>
      {body}
    </Link>
  ) : (
    <div className={cn(shell, "opacity-70")} aria-disabled="true">{body}</div>
  );
}

export function AppsLibraryView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("all");
  const [query, setQuery] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    api.authMe().then((u) => setIsAdmin(u.role === "owner_admin")).catch(() => setIsAdmin(false));
  }, []);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return APPS.filter((a) => (tab === "all" || a.category === tab) && (!q || `${a.name} ${a.blurb}`.toLowerCase().includes(q)));
  }, [tab, query]);

  const studios = [...CREATOR_NAV.filter((n) => n.href !== "/"), ...(isAdmin ? ADMIN_NAV : [])];

  return (
    <div className="mx-auto max-w-[1040px]">
      <h1 className="text-4xl font-extrabold tracking-[-0.03em]">App library</h1>
      <p className="mt-1 text-sm text-muted-foreground">Explore your local tools and connected services.</p>

      <h2 className="mb-3 mt-8 text-base font-semibold">Featured apps</h2>
      <ul className="grid gap-4 sm:grid-cols-3">
        {FEATURED.map((f) => (
          <li key={f.name}>
            <Link href={f.href} className="group relative block aspect-[4/3] overflow-hidden rounded-2xl border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <img src={f.image} alt="" width={720} height={540} className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" />
              <span className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" aria-hidden="true" />
              <span className={cn("absolute bottom-10 left-5 right-5 text-3xl font-extrabold leading-[1.05] tracking-[-0.02em] drop-shadow", f.tint)}>{f.name}</span>
              <span className={cn("absolute bottom-4 left-5 inline-flex items-center gap-1 text-sm", f.tint)}>
                Create now <ChevronRight className="h-4 w-4" />
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="mt-10 flex flex-wrap items-end justify-between gap-4 border-b border-border">
        <div role="tablist" aria-label="App categories" className="flex gap-6">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "-mb-px border-b-[3px] pb-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="mb-2 flex w-full items-center gap-2 rounded-full border border-border bg-card/60 px-4 py-2 sm:w-64">
          <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search apps"
            aria-label="Search apps"
            className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
        </label>
      </div>

      {shown.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">No apps match “{query}”. Try another word.</p>
      ) : (
        <ul className="mt-5 grid gap-3 md:grid-cols-2">
          {shown.map((app) => (
            <li key={app.name}><AppRow app={app} /></li>
          ))}
        </ul>
      )}

      <h2 className="mb-3 mt-12 text-base font-semibold">All studios</h2>
      <p className="mb-4 text-sm text-muted-foreground">Everything from the old sidebar, still here.</p>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {studios.map((s) => {
          const Icon = s.icon;
          return (
            <li key={s.href}>
              <Link href={s.href} className="flex items-center gap-2.5 rounded-xl border border-border bg-card/40 px-3 py-2.5 text-sm transition-colors hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                {s.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
