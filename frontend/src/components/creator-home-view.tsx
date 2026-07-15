"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ImageIcon,
  Pause,
  Play,
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
  href: string;
  accent: string;
  /** Pre-rendered media in public/home/<media>.png (+ optional .mp4 clip). */
  media?: string;
};

// Big, obvious creation tiles. Routes reuse the stable V1 creation flows.
const CREATE_TILES: Tile[] = [
  {
    title: "Text to Image",
    description: "Generate images from a text prompt.",
    icon: ImageIcon,
    href: "/create",
    accent: "from-violet-500/20 to-fuchsia-500/10",
    media: "text-to-image",
  },
  {
    title: "Text to Video",
    description: "Create a video from a written prompt.",
    icon: Wand2,
    href: "/videos?mode=text_to_video",
    accent: "from-sky-500/20 to-cyan-500/10",
    media: "text-to-video",
  },
  {
    title: "Image to Video",
    description: "Animate a still image into a short clip.",
    icon: Video,
    href: "/videos?mode=image_to_video",
    accent: "from-emerald-500/20 to-teal-500/10",
    media: "image-to-video",
  },
  {
    title: "Avatar & Voice Hub",
    description: "Create a talking avatar from a video or photo.",
    icon: ScanFace,
    href: "/avatars",
    accent: "from-amber-500/20 to-orange-500/10",
    media: "avatar-voice-hub",
  },
  {
    title: "Video to Text",
    description: "Upload a video to get a transcript or short summary.",
    icon: Type,
    href: "/video-to-text",
    accent: "from-rose-500/20 to-pink-500/10",
    media: "video-to-text",
  },
];

function TileMedia({ tile }: { tile: Tile }) {
  const [playing, setPlaying] = useState(false);
  const [hasImage, setHasImage] = useState(true);
  const [hasClip, setHasClip] = useState(true);
  if (!tile.media || !hasImage) return null;
  return (
    <div className={cn("relative -mx-5 -mt-5 mb-1 aspect-video overflow-hidden rounded-t-2xl bg-gradient-to-br", tile.accent)}>
      {playing && hasClip ? (
        <video
          src={`/home/${tile.media}.mp4`}
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => {
            setHasClip(false);
            setPlaying(false);
          }}
        />
      ) : (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={`/home/${tile.media}.png`}
          alt=""
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setHasImage(false)}
        />
      )}
      {hasClip ? (
        <button
          type="button"
          aria-label={playing ? "Pause preview" : "Play preview"}
          onClick={() => setPlaying((p) => !p)}
          className={cn(
            "absolute bottom-2 right-2 z-20 flex h-8 w-8 items-center justify-center rounded-full bg-background/70 text-foreground transition-colors hover:bg-background/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            playing && "opacity-0 group-hover:opacity-100",
          )}
        >
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>
      ) : null}
    </div>
  );
}

function CreateTile({ tile }: { tile: Tile }) {
  return (
    <article className="group relative flex h-full flex-col gap-3 overflow-hidden rounded-2xl border border-border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-within:border-primary focus-within:ring-2 focus-within:ring-ring">
      <Link
        href={tile.href}
        aria-label={`Start ${tile.title}`}
        className="absolute inset-0 z-10 rounded-2xl focus:outline-none"
      />
      <TileMedia tile={tile} />
      <div
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br text-foreground",
          tile.accent,
        )}
      >
          <tile.icon className="h-6 w-6" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-semibold">{tile.title}</h3>
        <p className="text-sm text-muted-foreground">{tile.description}</p>
      </div>
      <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-medium text-primary">
        Start <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
      </span>
    </article>
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
            Follow the guided workflow or jump directly into a creative tool.
          </p>
        </div>
      </section>

      <Link
        href="/chain"
        className="group flex flex-col justify-between gap-5 rounded-2xl border border-primary/30 bg-gradient-to-r from-primary/15 via-card to-card p-6 transition-all hover:border-primary/60 hover:shadow-lg sm:flex-row sm:items-center"
      >
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Wand2 className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">Recommended workflow</p>
            <h2 className="mt-1 text-xl font-semibold">Start with Quick Chain</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Move from an idea to image, video, voice, transcript, and download in one guided flow.
            </p>
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-primary">
          Start creating <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
        </span>
      </Link>

      {/* Big creation tiles */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Or choose a tool</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {CREATE_TILES.map((tile) => (
            <CreateTile key={tile.title} tile={tile} />
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
