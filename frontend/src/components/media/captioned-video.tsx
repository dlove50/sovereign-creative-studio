"use client";

import { useEffect, useRef, useState } from "react";
import { Captions, Download, Loader2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * A finished video with Download and "Add captions". Captions are burned into a copy
 * (local Whisper + FFmpeg, a few seconds to a minute), and the original stays available.
 * With `auto` the captions are added as soon as the video shows up.
 */
export function CaptionedVideo({ src, auto = false, className, children }: { src: string; auto?: boolean; className?: string; children?: React.ReactNode }) {
  const [captioned, setCaptioned] = useState<{ video_url: string; srt_url: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triedAuto = useRef<string | null>(null);

  async function add() {
    setBusy(true);
    setError(null);
    try {
      setCaptioned(await api.addCaptions(src));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Captions could not be added.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { setCaptioned(null); setError(null); }, [src]);
  useEffect(() => {
    if (auto && triedAuto.current !== src) { triedAuto.current = src; void add(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, src]);

  const shown = captioned?.video_url ?? src;
  const button = "inline-flex items-center justify-center gap-2 rounded-full border border-border px-5 py-2 text-sm hover:bg-raised disabled:opacity-60";
  return (
    <div className="flex flex-wrap items-end gap-4">
      <video key={shown} controls src={assetUrl(shown) ?? undefined} className={cn("rounded-2xl border border-border bg-black", className)} />
      <span className="flex flex-col gap-2">
        <a href={assetUrl(shown) ?? "#"} download className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground">
          <Download className="h-4 w-4" /> Download video
        </a>
        {captioned ? (
          <a href={assetUrl(captioned.srt_url) ?? "#"} download className={button}><Captions className="h-4 w-4" /> Download captions (.srt)</a>
        ) : (
          <button type="button" onClick={add} disabled={busy} className={button}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Captions className="h-4 w-4" />} {busy ? "Adding captions…" : "Add captions"}
          </button>
        )}
        {children}
        {error ? <span role="alert" className="max-w-[220px] text-xs text-destructive">{error}</span> : null}
      </span>
    </div>
  );
}
