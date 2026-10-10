"use client";

import { useState } from "react";
import { ImageIcon, Pause, Play, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

type Kind = "video" | "image";
type Card = {
  id: string;
  title: string;
  tag: string;
  kind: Kind;
  gradient: string;
  meta?: string;
};

// Thumbnails are pre-rendered locally (Z-Image Turbo) into public/inspiration/<id>.png.
const thumbSrc = (id: string) => `/inspiration/${id}.png`;

// Seeded local inspiration content (static for now — no external calls).
const TRENDING: Card[] = [
  { id: "t1", title: "Glow serum unboxing", tag: "TikTok", kind: "video", gradient: "from-fuchsia-500/40 to-violet-600/30", meta: "0:15" },
  { id: "t2", title: "Sneaker drop teaser", tag: "TikTok", kind: "video", gradient: "from-sky-500/40 to-indigo-600/30", meta: "0:09" },
  { id: "t3", title: "Café morning aesthetic", tag: "TikTok", kind: "video", gradient: "from-amber-500/40 to-orange-600/30", meta: "0:12" },
  { id: "t4", title: "Skincare routine reel", tag: "TikTok", kind: "video", gradient: "from-emerald-500/40 to-teal-600/30", meta: "0:18" },
  { id: "t5", title: "Candle ambience loop", tag: "TikTok", kind: "video", gradient: "from-rose-500/40 to-pink-600/30", meta: "0:08" },
  { id: "t6", title: "Watch close-up spin", tag: "TikTok", kind: "video", gradient: "from-slate-500/40 to-zinc-600/30", meta: "0:10" },
];

const VIDEO_TEMPLATES: Card[] = [
  { id: "v1", title: "Product reveal — slow zoom", tag: "Template", kind: "video", gradient: "from-violet-500/40 to-purple-700/30", meta: "5s" },
  { id: "v2", title: "Three-shot promo", tag: "Template", kind: "video", gradient: "from-cyan-500/40 to-blue-700/30", meta: "10s" },
  { id: "v3", title: "Runway walk loop", tag: "Template", kind: "video", gradient: "from-pink-500/40 to-rose-700/30", meta: "6s" },
  { id: "v4", title: "Cinematic push-in", tag: "Template", kind: "video", gradient: "from-teal-500/40 to-emerald-700/30", meta: "8s" },
];

const IMAGE_TEMPLATES: Card[] = [
  { id: "i1", title: "Luxury studio hero", tag: "Template", kind: "image", gradient: "from-amber-400/40 to-yellow-600/30" },
  { id: "i2", title: "Marble flat-lay", tag: "Template", kind: "image", gradient: "from-stone-400/40 to-neutral-600/30" },
  { id: "i3", title: "Neon night scene", tag: "Template", kind: "image", gradient: "from-fuchsia-500/40 to-indigo-700/30" },
  { id: "i4", title: "Soft daylight portrait", tag: "Template", kind: "image", gradient: "from-sky-400/40 to-cyan-600/30" },
];

const TABS = [
  { id: "trending", label: "Starter ideas", cards: TRENDING },
  { id: "video", label: "Video Templates", cards: VIDEO_TEMPLATES },
  { id: "image", label: "Image Templates", cards: IMAGE_TEMPLATES },
] as const;

function ThumbCard({ card }: { card: Card }) {
  const [playing, setPlaying] = useState(false);
  const [hasClip, setHasClip] = useState(true);
  const interactive = card.kind === "video" && hasClip;
  return (
    <div className="group overflow-hidden rounded-xl border border-border bg-card transition-transform hover:-translate-y-0.5">
      <div className={cn("relative flex aspect-[3/4] items-center justify-center bg-gradient-to-br", card.gradient)}>
        {playing && interactive ? (
          <video
            src={`/inspiration/${card.id}.mp4`}
            autoPlay
            loop
            muted
            playsInline
            className="absolute inset-0 h-full w-full object-cover"
            onError={() => {
              // No motion clip for this card: stay on the still thumbnail.
              setHasClip(false);
              setPlaying(false);
            }}
          />
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={thumbSrc(card.id)}
            alt=""
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
            onError={(e) => {
              // Missing thumbnail: fall back to the gradient background.
              e.currentTarget.style.display = "none";
            }}
          />
        )}
        {interactive ? (
          <button
            type="button"
            aria-label={playing ? "Pause preview" : "Play preview"}
            onClick={() => setPlaying((p) => !p)}
            className={cn(
              "relative flex h-10 w-10 items-center justify-center rounded-full bg-background/70 text-foreground transition-opacity hover:bg-background/90",
              playing && "opacity-0 group-hover:opacity-100",
            )}
          >
            {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
          </button>
        ) : (
          <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-background/70 text-foreground">
            {card.kind === "video" ? <Play className="h-5 w-5" /> : <ImageIcon className="h-5 w-5" />}
          </span>
        )}
        <span className="absolute left-2 top-2 rounded-full bg-background/70 px-2 py-0.5 text-[11px] font-medium">
          {card.tag}
        </span>
        {card.meta ? (
          <span className="absolute bottom-2 right-2 rounded-full bg-background/70 px-2 py-0.5 text-[11px]">
            {card.meta}
          </span>
        ) : null}
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-medium">{card.title}</p>
      </div>
    </div>
  );
}

export function InspirationGallery({ preview = false }: { preview?: boolean }) {
  const [active, setActive] = useState<(typeof TABS)[number]["id"]>("trending");

  if (preview) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {TRENDING.map((card) => (
          <ThumbCard key={card.id} card={card} />
        ))}
      </div>
    );
  }

  const current = TABS.find((t) => t.id === active) ?? TABS[0];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActive(tab.id)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors",
              active === tab.id
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:bg-muted",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {current.cards.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border text-center text-sm text-muted-foreground">
          <Sparkles className="h-7 w-7" />
          <p className="font-medium text-foreground">Nothing here yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {current.cards.map((card) => (
            <ThumbCard key={card.id} card={card} />
          ))}
        </div>
      )}
    </div>
  );
}
