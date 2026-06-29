"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Eraser,
  ImageIcon,
  ImagePlus,
  LayoutTemplate,
  Palette,
  ScanFace,
  Sparkles,
  Type,
  Video,
  Wand2,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InspirationGallery } from "@/components/inspiration-gallery";

type Tile = {
  title: string;
  description: string;
  icon: typeof ImageIcon;
  href?: string;
  comingSoon?: boolean;
  accent: string;
};

// Big, obvious creation tiles. Routes reuse existing flows; unfinished ones are
// clearly marked "Coming soon" instead of exposing broken behavior.
const CREATE_TILES: Tile[] = [
  {
    title: "Text to Image",
    description: "Generate images from a text prompt.",
    icon: ImageIcon,
    href: "/create",
    accent: "from-violet-500/20 to-fuchsia-500/10",
  },
  {
    title: "Text to Video",
    description: "Create a video from a written prompt.",
    icon: Wand2,
    href: "/videos?mode=text_to_video",
    accent: "from-sky-500/20 to-cyan-500/10",
  },
  {
    title: "Image to Video",
    description: "Animate a still image into a short clip.",
    icon: Video,
    href: "/videos?mode=image_to_video",
    accent: "from-emerald-500/20 to-teal-500/10",
  },
  {
    title: "Avatar & Voice Hub",
    description: "Create a talking avatar from a video or photo.",
    icon: ScanFace,
    href: "/avatars",
    accent: "from-amber-500/20 to-orange-500/10",
  },
  {
    title: "Video to Text",
    description: "Upload a video to get a transcript or short summary.",
    icon: Type,
    href: "/video-to-text",
    accent: "from-rose-500/20 to-pink-500/10",
  },
];

const QUICK_TOOLS: Tile[] = [
  { title: "AI Design", description: "Smart layouts for posts & ads.", icon: Palette, comingSoon: true, accent: "" },
  { title: "AI Background", description: "Generate a new scene behind your subject.", icon: ImagePlus, comingSoon: true, accent: "" },
  { title: "Remove Background", description: "Cut out the subject cleanly.", icon: Eraser, comingSoon: true, accent: "" },
  { title: "Layout Design", description: "Arrange assets into a finished piece.", icon: LayoutTemplate, comingSoon: true, accent: "" },
];

function ComingSoon() {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
      Coming soon
    </span>
  );
}

function CreateTile({ tile }: { tile: Tile }) {
  const inner = (
    <div
      className={cn(
        "group relative flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-5 transition-all",
        tile.comingSoon ? "opacity-90" : "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg",
      )}
    >
      <div
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br text-foreground",
          tile.accent || "from-muted to-muted",
        )}
      >
        <tile.icon className="h-6 w-6" />
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold">{tile.title}</h3>
          {tile.comingSoon ? <ComingSoon /> : null}
        </div>
        <p className="text-sm text-muted-foreground">{tile.description}</p>
      </div>
      {!tile.comingSoon ? (
        <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-medium text-primary">
          Start <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </span>
      ) : null}
    </div>
  );

  if (tile.comingSoon || !tile.href) {
    return <div aria-disabled className="h-full cursor-default">{inner}</div>;
  }
  return (
    <Link href={tile.href} className="h-full">
      {inner}
    </Link>
  );
}

export function CreatorHomeView() {
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    api.getMe().then((u) => setName(u.name)).catch(() => setName(null));
  }, []);

  return (
    <div className="space-y-10">
      {/* Welcome */}
      <section className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
          <Sparkles className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome{name ? `, ${name}` : ""} — let&apos;s create something amazing!
          </h1>
          <p className="text-sm text-muted-foreground">
            Pick a tile below to start. No setup needed.
          </p>
        </div>
      </section>

      {/* Big creation tiles */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Create</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {CREATE_TILES.map((tile) => (
            <CreateTile key={tile.title} tile={tile} />
          ))}
        </div>
      </section>

      {/* Quick image tools */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Quick image tools</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_TOOLS.map((tool) => (
            <div
              key={tool.title}
              className="flex items-center gap-3 rounded-xl border border-border bg-card p-4"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <tool.icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium">{tool.title}</p>
                  <ComingSoon />
                </div>
                <p className="truncate text-xs text-muted-foreground">{tool.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Inspiration */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Inspiration</h2>
          <Link href="/inspiration" className="inline-flex items-center gap-1 text-sm font-medium text-primary">
            Browse all <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <InspirationGallery preview />
      </section>
    </div>
  );
}
