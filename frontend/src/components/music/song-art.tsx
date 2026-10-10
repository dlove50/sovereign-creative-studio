import { Music2 } from "lucide-react";

import { cn } from "@/lib/utils";

/** Stable 0-359 hue from a string, so each song keeps its own cover colour. */
function hueFor(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) % 360;
  return h;
}

/** Generated cover art: a soft two-tone gradient on Sovereign's charcoal surface. */
export function SongArt({
  seed,
  className,
  playing = false,
}: {
  seed: string;
  className?: string;
  playing?: boolean;
}) {
  const hue = hueFor(seed);
  const style = {
    background: `radial-gradient(120% 120% at 20% 10%, hsl(${hue} 80% 58% / 0.9), transparent 60%),
      radial-gradient(100% 100% at 90% 90%, hsl(${(hue + 70) % 360} 70% 55% / 0.85), transparent 62%),
      hsl(var(--raised))`,
  };
  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border/60",
        className,
      )}
      style={style}
      aria-hidden="true"
    >
      <Music2 className={cn("h-1/2 w-1/2 text-white/85 drop-shadow", playing && "animate-pulse")} />
    </div>
  );
}
