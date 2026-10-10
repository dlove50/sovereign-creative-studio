"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";
import { useMotionPreference } from "@/components/motion/motion-provider";

export type VisualStyle = "bars" | "radial" | "wave";

type Props = {
  /** frames x bands, one byte each (from the backend's real audio analysis). */
  frames: Uint8Array | null;
  bands: number;
  fps: number;
  /** Current song position in seconds, read every animation frame. */
  getPosition: () => number;
  active: boolean;
  visual: VisualStyle;
  className?: string;
};

// Sovereign's palette: sky-cyan primary into violet accent.
const CYAN = [34, 184, 240];
const VIOLET = [150, 98, 232];

function mix(t: number): string {
  const c = CYAN.map((v, i) => Math.round(v + (VIOLET[i] - v) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** Smooth, per-band levels for the current moment, 0..1. */
function levelsAt(frames: Uint8Array, bands: number, fps: number, position: number, out: Float32Array) {
  const total = Math.floor(frames.length / bands);
  const f = Math.max(0, Math.min(total - 1, position * fps));
  const a = Math.floor(f);
  const b = Math.min(total - 1, a + 1);
  const t = f - a;
  for (let i = 0; i < bands; i++) {
    out[i] = (frames[a * bands + i] * (1 - t) + frames[b * bands + i] * t) / 255;
  }
}

export function SpectrumCanvas({ frames, bands, fps, getPosition, active, visual, className }: Props) {
  const { motionEnabled } = useMotionPreference();
  const ref = useRef<HTMLCanvasElement>(null);
  const live = useRef({ frames, bands, fps, getPosition, active, visual });
  live.current = { frames, bands, fps, getPosition, active, visual };

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let width = 0;
    let height = 0;
    const smooth = new Float32Array(64);
    const peaks = new Float32Array(64);
    const raw = new Float32Array(64);

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    const draw = (now: number) => {
      const s = live.current;
      ctx.clearRect(0, 0, width, height);
      const n = Math.min(s.bands, 64);
      if (s.frames && s.active) {
        levelsAt(s.frames, s.bands, s.fps, s.getPosition(), raw);
      } else {
        // Idle shimmer so the stage never looks dead.
        for (let i = 0; i < n; i++) raw[i] = 0.06 + 0.04 * Math.sin(now / 900 + i * 0.7);
      }
      for (let i = 0; i < n; i++) {
        const target = motionEnabled ? raw[i] : raw[i] * 0.6;
        smooth[i] += (target - smooth[i]) * (target > smooth[i] ? 0.55 : 0.18);
        peaks[i] = Math.max(smooth[i], peaks[i] - 0.012);
      }
      if (s.visual === "radial") drawRadial(ctx, width, height, smooth, n, now);
      else if (s.visual === "wave") drawWave(ctx, width, height, smooth, n, now);
      else drawBars(ctx, width, height, smooth, peaks, n);
      if (motionEnabled) raf = requestAnimationFrame(draw);
    };
    if (motionEnabled) raf = requestAnimationFrame(draw);
    else draw(0);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [motionEnabled]);

  return <canvas ref={ref} className={cn("block h-full w-full", className)} aria-hidden="true" />;
}

function drawBars(ctx: CanvasRenderingContext2D, w: number, h: number, v: Float32Array, p: Float32Array, n: number) {
  const gap = Math.max(2, w / n / 6);
  const barW = (w - gap * (n + 1)) / n;
  const base = h * 0.92;
  for (let i = 0; i < n; i++) {
    const level = Math.pow(v[i], 1.15);
    const bh = Math.max(3, level * h * 0.82);
    const x = gap + i * (barW + gap);
    const grad = ctx.createLinearGradient(0, base, 0, base - bh);
    grad.addColorStop(0, mix(i / n));
    grad.addColorStop(1, mix(Math.min(1, i / n + 0.35)));
    ctx.shadowColor = mix(i / n);
    ctx.shadowBlur = 14 * level;
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x, base - bh, barW, bh, Math.min(8, barW / 2));
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(243,244,246,0.85)";
    ctx.fillRect(x, base - p[i] * h * 0.82 - 6, barW, 2);
    // Soft reflection
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = mix(i / n);
    ctx.fillRect(x, base + 4, barW, bh * 0.25);
    ctx.globalAlpha = 1;
  }
}

function drawRadial(ctx: CanvasRenderingContext2D, w: number, h: number, v: Float32Array, n: number, now: number) {
  const cx = w / 2;
  const cy = h / 2;
  const r0 = Math.min(w, h) * 0.2;
  const maxLen = Math.min(w, h) * 0.3;
  const spokes = n * 3;
  const rot = now / 9000;
  let energy = 0;
  for (let i = 0; i < n; i++) energy += v[i];
  energy /= n;
  ctx.shadowColor = mix(0.2);
  ctx.shadowBlur = 24 * energy;
  ctx.strokeStyle = mix(0.3);
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r0 * (0.92 + energy * 0.25), 0, Math.PI * 2);
  ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.lineCap = "round";
  ctx.lineWidth = Math.max(2, (Math.PI * 2 * r0) / spokes - 2);
  for (let i = 0; i < spokes; i++) {
    const band = i < spokes / 2 ? i / (spokes / 2) : 1 - (i - spokes / 2) / (spokes / 2);
    const level = v[Math.min(n - 1, Math.floor(band * (n - 1)))];
    const len = 4 + Math.pow(level, 1.2) * maxLen;
    const a = rot + (i / spokes) * Math.PI * 2;
    ctx.strokeStyle = mix(band);
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
    ctx.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
    ctx.stroke();
  }
}

function drawWave(ctx: CanvasRenderingContext2D, w: number, h: number, v: Float32Array, n: number, now: number) {
  const mid = h / 2;
  for (let layer = 0; layer < 3; layer++) {
    const amp = h * (0.34 - layer * 0.08);
    ctx.beginPath();
    for (let x = 0; x <= w; x += 4) {
      const t = x / w;
      const idx = Math.min(n - 1, Math.floor(t * (n - 1)));
      const level = v[idx];
      const y = mid + Math.sin(t * 9 + now / (500 + layer * 220) + layer) * amp * (0.15 + level);
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = mix(layer / 2.4);
    ctx.globalAlpha = 0.95 - layer * 0.25;
    ctx.lineWidth = 3 - layer * 0.6;
    ctx.shadowColor = mix(layer / 2.4);
    ctx.shadowBlur = 12;
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.shadowBlur = 0;
}
