"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Award, ChevronLeft, ChevronRight, Clapperboard, Drama, Film, GraduationCap, Home, Music2, Popcorn, Repeat, Rocket,
  Share2, ShoppingBag, Smartphone, type LucideIcon,
} from "lucide-react";

import { directorApi, type DirectorTemplate } from "@/lib/api/director";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  "short-film": Film,
  "music-video": Music2,
  "real-estate": Home,
  "product-ads": ShoppingBag,
  "ad-remake": Repeat,
  "social-content": Share2,
  "ugc-ads": Smartphone,
  "micro-drama": Drama,
  "brand-film": Award,
  explainer: GraduationCap,
  "film-trailer": Popcorn,
  "promo-video": Rocket,
};

export function templateIcon(id: string): LucideIcon {
  return ICONS[id] ?? Clapperboard;
}

export function useTemplates() {
  const [templates, setTemplates] = useState<DirectorTemplate[] | null>(null);
  const [creditsPerClip, setCreditsPerClip] = useState(20);
  useEffect(() => {
    directorApi
      .templates()
      .then((data) => {
        setTemplates(data.templates);
        setCreditsPerClip(data.credits_per_clip);
      })
      .catch(() => setTemplates([]));
  }, []);
  return { templates, creditsPerClip };
}

function Tile({ template, wide }: { template: DirectorTemplate; wide: boolean }) {
  const Icon = templateIcon(template.id);
  return (
    <Link
      href={`/director/new?template=${template.id}`}
      className={cn(
        "group relative block shrink-0 snap-start overflow-hidden rounded-2xl border border-border bg-card transition-transform duration-300 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        wide ? "w-full" : "w-[11.5rem] sm:w-[13rem]",
      )}
    >
      <div className="aspect-[4/5] overflow-hidden">
        <img src={template.image} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]" />
      </div>
      <span className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" aria-hidden="true" />
      {template.badge ? (
        <span className="absolute right-2.5 top-2.5 rounded-md bg-primary px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary-foreground">
          {template.badge}
        </span>
      ) : null}
      <span className="absolute inset-x-3 bottom-3">
        <span className="flex items-center gap-2 text-[15px] font-semibold text-white">
          <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
          {template.label}
        </span>
        <span className="mt-0.5 block text-xs leading-snug text-white/75">{template.tagline}</span>
      </span>
    </Link>
  );
}

/** The "Direct your video" row: scrollable on Home, a wrapping grid on the Director page. */
export function TemplateCarousel({ layout = "row" }: { layout?: "row" | "grid" }) {
  const { templates } = useTemplates();
  const scroller = useRef<HTMLUListElement>(null);

  const scrollBy = (direction: 1 | -1) => scroller.current?.scrollBy({ left: direction * 520, behavior: "smooth" });

  if (templates === null) {
    return <div className="h-64 animate-pulse rounded-2xl bg-card/50" aria-label="Loading templates" />;
  }
  if (templates.length === 0) {
    return <p className="text-sm text-muted-foreground">The Director templates could not be loaded. Is the backend running?</p>;
  }
  if (layout === "grid") {
    return (
      <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {templates.map((t) => (
          <li key={t.id}>
            <Tile template={t} wide />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="relative">
      <ul ref={scroller} className="flex snap-x gap-3 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {templates.map((t) => (
          <li key={t.id} className="shrink-0">
            <Tile template={t} wide={false} />
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => scrollBy(-1)}
        aria-label="Scroll templates left"
        className="absolute -left-3 top-1/2 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card/90 text-foreground shadow backdrop-blur hover:bg-raised md:flex"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => scrollBy(1)}
        aria-label="Scroll templates right"
        className="absolute -right-3 top-1/2 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card/90 text-foreground shadow backdrop-blur hover:bg-raised md:flex"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
