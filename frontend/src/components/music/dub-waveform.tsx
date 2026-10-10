"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import type { DubCue } from "@/lib/api/music";

export const CUE_COLORS = ["#22b8f0", "#f59e0b", "#34d399", "#f472b6", "#a78bfa", "#fb7185", "#facc15", "#2dd4bf"];

type Props = {
  peaks: string;
  duration: number;
  position: number;
  bpm: number;
  beatOffset: number;
  cues: DubCue[];
  loop: { start: number; end: number; active: boolean } | null;
  trim: { start: number; end: number };
  drops: { at: number; end: number }[];
  /** Visible window in seconds; the waveform follows the playhead when zoomed in. */
  zoomSeconds: number;
  onSeek: (seconds: number) => void;
};

function decodePeaks(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Serato-style waveform: beat grid, hot cue flags, loop, trim region and drop-outs over the song's real peaks. */
export function DubWaveform(props: Props) {
  const { peaks, duration, position, bpm, beatOffset, cues, loop, trim, drops, zoomSeconds, onSeek } = props;
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const data = useMemo(() => decodePeaks(peaks), [peaks]);
  const windowSeconds = Math.min(zoomSeconds || duration, duration);
  const viewStart = windowSeconds >= duration ? 0 : Math.max(0, Math.min(position - windowSeconds / 2, duration - windowSeconds));

  const draw = useCallback(() => {
    const el = canvas.current;
    if (!el) return;
    const dpr = window.devicePixelRatio || 1;
    const w = el.clientWidth;
    const h = el.clientHeight;
    if (el.width !== Math.round(w * dpr) || el.height !== Math.round(h * dpr)) {
      el.width = Math.round(w * dpr);
      el.height = Math.round(h * dpr);
    }
    const g = el.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const x = (t: number) => ((t - viewStart) / windowSeconds) * w;
    const mid = h / 2;

    g.fillStyle = "rgba(34,184,240,0.07)";
    g.fillRect(Math.max(0, x(trim.start)), 0, Math.max(0, x(trim.end) - Math.max(0, x(trim.start))), h);
    g.fillStyle = "rgba(0,0,0,0.45)";
    g.fillRect(0, 0, Math.max(0, Math.min(w, x(trim.start))), h);
    g.fillRect(Math.min(w, Math.max(0, x(trim.end))), 0, w, h);

    if (loop) {
      g.fillStyle = loop.active ? "rgba(52,211,153,0.28)" : "rgba(52,211,153,0.12)";
      g.fillRect(x(loop.start), 0, x(loop.end) - x(loop.start), h);
    }
    for (const d of drops) {
      g.fillStyle = "rgba(244,114,182,0.22)";
      g.fillRect(x(d.at), 0, x(d.end) - x(d.at), h);
    }

    if (bpm > 0) {
      const beat = 60 / bpm;
      const first = Math.ceil((viewStart - beatOffset) / beat);
      for (let k = first; ; k++) {
        const t = beatOffset + k * beat;
        if (t > viewStart + windowSeconds) break;
        const bar = ((k % 4) + 4) % 4 === 0;
        g.fillStyle = bar ? "rgba(255,255,255,0.28)" : "rgba(255,255,255,0.09)";
        g.fillRect(Math.round(x(t)), bar ? 0 : h * 0.3, 1, bar ? h : h * 0.4);
      }
    }

    const grad = g.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#22b8f0");
    grad.addColorStop(1, "#9662e8");
    g.fillStyle = grad;
    const step = Math.max(1, Math.floor(w / 900));
    for (let px = 0; px < w; px += step) {
      const t = viewStart + (px / w) * windowSeconds;
      const i = Math.min(data.length - 1, Math.floor((t / duration) * data.length));
      const amp = (data[i] / 255) * (mid - 6);
      g.fillRect(px, mid - amp, Math.max(1, step - 0.4), Math.max(1, amp * 2));
    }

    for (const cue of cues) {
      const cx = x(cue.time);
      if (cx < -20 || cx > w + 20) continue;
      g.fillStyle = CUE_COLORS[cue.slot % CUE_COLORS.length];
      g.fillRect(cx, 0, 2, h);
      g.fillRect(cx, 0, 16, 16);
      g.fillStyle = "#0b0f14";
      g.font = "bold 11px sans-serif";
      g.fillText(String(cue.slot + 1), cx + 4, 12);
    }

    const px = x(position);
    g.fillStyle = "#ffffff";
    g.fillRect(px - 1, 0, 2, h);
    g.beginPath();
    g.moveTo(px - 6, 0);
    g.lineTo(px + 6, 0);
    g.lineTo(px, 8);
    g.closePath();
    g.fill();
  }, [data, duration, position, bpm, beatOffset, cues, loop, trim, drops, viewStart, windowSeconds]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    const el = canvas.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [draw]);

  const seekFromPointer = (clientX: number) => {
    const el = canvas.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const t = viewStart + ((clientX - rect.left) / rect.width) * windowSeconds;
    onSeek(Math.max(0, Math.min(t, duration)));
  };

  return (
    <canvas
      ref={canvas}
      role="slider"
      aria-label="Waveform. Click to move the playhead."
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(position)}
      tabIndex={0}
      className="h-40 w-full cursor-crosshair touch-none rounded-xl border border-border bg-background/60 md:h-48"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        seekFromPointer(e.clientX);
      }}
      onPointerMove={(e) => {
        if (e.buttons === 1) seekFromPointer(e.clientX);
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onSeek(Math.max(0, position - 1));
        if (e.key === "ArrowRight") onSeek(Math.min(duration, position + 1));
      }}
    />
  );
}
