"use client";

import { useRef, useState } from "react";
import { UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMotionPreference } from "@/components/motion/motion-provider";

/** Play actual preview footage only; still images never masquerade as animation. */
export function AvatarPreview({ image, video, label, className }: { image?: string | null; video?: string | null; label: string; className?: string }) {
  const { motionEnabled } = useMotionPreference();
  const clip = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  function play() {
    if (!video || !motionEnabled) return;
    void clip.current?.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }
  function stop() {
    clip.current?.pause();
    if (clip.current) clip.current.currentTime = 0;
    setPlaying(false);
  }
  return <span onMouseEnter={play} onMouseLeave={stop} onFocus={play} onBlur={stop}
    tabIndex={video ? 0 : undefined} aria-label={video ? `Preview ${label}` : undefined}
    className={cn("relative flex min-h-0 items-center justify-center overflow-hidden bg-raised", className)}>
    {image && !failed ? <img src={image} alt={label} onError={() => setFailed(true)} className="h-full w-full object-cover" />
      : <span className="flex flex-col items-center gap-2 p-3 text-center text-xs text-muted-foreground"><UserRound className="h-6 w-6" aria-hidden="true" />{failed ? "Image unavailable" : "Add a look"}</span>}
    {video ? <video ref={clip} src={video} muted loop playsInline preload="none" onError={() => setPlaying(false)} aria-hidden="true"
      className={cn("absolute inset-0 h-full w-full object-cover", !playing && "invisible")} /> : null}
  </span>;
}
