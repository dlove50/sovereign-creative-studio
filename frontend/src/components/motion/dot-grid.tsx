"use client";

// Adapted from React Bits "DotGrid" (MIT + Commons Clause: fine to use in this studio, not to resell as a component library).
// Changes for this app: it only redraws while something is moving (the original redraws every frame, always),
// it pauses while the tab is hidden or the grid is off screen, it only reacts to the pointer over the grid, and
// reduced-motion users get a still grid.

import { useCallback, useEffect, useRef } from "react";
import { gsap } from "gsap";
import { InertiaPlugin } from "gsap/InertiaPlugin";

import { useMotionPreference } from "./motion-provider";

gsap.registerPlugin(InertiaPlugin);

type Dot = { cx: number; cy: number; xOffset: number; yOffset: number; busy: boolean };

export interface DotGridProps {
  dotSize?: number;
  gap?: number;
  baseColor?: string;
  activeColor?: string;
  proximity?: number;
  speedTrigger?: number;
  shockRadius?: number;
  shockStrength?: number;
  maxSpeed?: number;
  resistance?: number;
  returnDuration?: number;
  className?: string;
}

function rgb(hex: string) {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  return m ? { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16) } : { r: 0, g: 0, b: 0 };
}

export function DotGrid({
  dotSize = 3, gap = 26, baseColor = "#454c5a", activeColor = "#22b8f0", proximity = 120, speedTrigger = 100,
  shockRadius = 200, shockStrength = 4, maxSpeed = 5000, resistance = 750, returnDuration = 1.4, className = "",
}: DotGridProps) {
  const { motionEnabled } = useMotionPreference();
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const dots = useRef<Dot[]>([]);
  const pointer = useRef({ x: -9999, y: -9999, lastX: 0, lastY: 0, lastTime: 0 });
  const dirty = useRef(true);
  const running = useRef(true); // false while hidden or off screen

  const draw = useCallback(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, el.width / dpr, el.height / dpr);
    const base = rgb(baseColor);
    const active = rgb(activeColor);
    const limit = proximity * proximity;
    for (const dot of dots.current) {
      const dx = dot.cx - pointer.current.x;
      const dy = dot.cy - pointer.current.y;
      const d2 = dx * dx + dy * dy;
      if (d2 <= limit) {
        const t = 1 - Math.sqrt(d2) / proximity;
        ctx.fillStyle = `rgb(${Math.round(base.r + (active.r - base.r) * t)},${Math.round(base.g + (active.g - base.g) * t)},${Math.round(base.b + (active.b - base.b) * t)})`;
      } else {
        ctx.fillStyle = baseColor;
      }
      ctx.beginPath();
      ctx.arc(dot.cx + dot.xOffset, dot.cy + dot.yOffset, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [baseColor, activeColor, proximity, dotSize]);

  const build = useCallback(() => {
    const wrap = wrapper.current;
    const el = canvas.current;
    if (!wrap || !el) return;
    const { width, height } = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    el.width = Math.max(1, Math.round(width * dpr));
    el.height = Math.max(1, Math.round(height * dpr));
    el.style.width = `${width}px`;
    el.style.height = `${height}px`;
    const cell = dotSize + gap;
    const cols = Math.max(1, Math.floor((width + gap) / cell));
    const rows = Math.max(1, Math.floor((height + gap) / cell));
    const startX = (width - (cell * cols - gap)) / 2 + dotSize / 2;
    const startY = (height - (cell * rows - gap)) / 2 + dotSize / 2;
    const next: Dot[] = [];
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      next.push({ cx: startX + x * cell, cy: startY + y * cell, xOffset: 0, yOffset: 0, busy: false });
    }
    dots.current = next;
    dirty.current = true;
  }, [dotSize, gap]);

  useEffect(() => {
    const wrap = wrapper.current;
    if (!wrap) return;
    build();
    draw();
    const resize = new ResizeObserver(() => { build(); draw(); });
    resize.observe(wrap);

    if (!motionEnabled) return () => resize.disconnect(); // a quiet, still grid

    // Redraw only when something changed, and never while hidden or scrolled away.
    const onTick = () => {
      if (!running.current || !dirty.current) return;
      dirty.current = false;
      draw();
    };
    gsap.ticker.add(onTick);
    const visible = new IntersectionObserver(([entry]) => { running.current = entry.isIntersecting && !document.hidden; });
    visible.observe(wrap);
    const onVisibility = () => { running.current = !document.hidden; };
    document.addEventListener("visibilitychange", onVisibility);

    const push = (dot: Dot, x: number, y: number) => {
      dot.busy = true;
      gsap.killTweensOf(dot);
      gsap.to(dot, {
        inertia: { xOffset: x, yOffset: y, resistance },
        onUpdate: () => { dirty.current = true; },
        onComplete: () => {
          gsap.to(dot, {
            xOffset: 0, yOffset: 0, duration: returnDuration, ease: "elastic.out(1,0.75)",
            onUpdate: () => { dirty.current = true; }, onComplete: () => { dot.busy = false; },
          });
        },
      });
    };

    let lastMove = 0;
    const onMove = (event: PointerEvent) => {
      const now = performance.now();
      if (now - lastMove < 40) return; // about 25 updates a second is plenty
      lastMove = now;
      const box = wrap.getBoundingClientRect();
      const x = event.clientX - box.left;
      const y = event.clientY - box.top;
      const inside = x >= -proximity && x <= box.width + proximity && y >= -proximity && y <= box.height + proximity;
      const p = pointer.current;
      const dt = p.lastTime ? now - p.lastTime : 16;
      let vx = ((event.clientX - p.lastX) / dt) * 1000;
      let vy = ((event.clientY - p.lastY) / dt) * 1000;
      const speed = Math.hypot(vx, vy);
      if (speed > maxSpeed) { vx *= maxSpeed / speed; vy *= maxSpeed / speed; }
      p.lastTime = now; p.lastX = event.clientX; p.lastY = event.clientY;
      if (!inside) {
        if (p.x !== -9999) { p.x = -9999; p.y = -9999; dirty.current = true; }
        return;
      }
      p.x = x; p.y = y; dirty.current = true;
      if (Math.min(speed, maxSpeed) > speedTrigger) {
        for (const dot of dots.current) {
          if (dot.busy || Math.hypot(dot.cx - x, dot.cy - y) >= proximity) continue;
          push(dot, dot.cx - x + vx * 0.005, dot.cy - y + vy * 0.005);
        }
      }
    };
    const onClick = (event: MouseEvent) => {
      const box = wrap.getBoundingClientRect();
      const x = event.clientX - box.left;
      const y = event.clientY - box.top;
      if (x < 0 || y < 0 || x > box.width || y > box.height) return; // clicks elsewhere on the page do nothing here
      for (const dot of dots.current) {
        const dist = Math.hypot(dot.cx - x, dot.cy - y);
        if (dot.busy || dist >= shockRadius) continue;
        const falloff = Math.max(0, 1 - dist / shockRadius);
        push(dot, (dot.cx - x) * shockStrength * falloff, (dot.cy - y) * shockStrength * falloff);
      }
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("click", onClick);

    return () => {
      resize.disconnect();
      visible.disconnect();
      gsap.ticker.remove(onTick);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("click", onClick);
      dots.current.forEach((dot) => gsap.killTweensOf(dot));
    };
  }, [build, draw, maxSpeed, motionEnabled, speedTrigger, proximity, resistance, returnDuration, shockRadius, shockStrength]);

  return (
    <div ref={wrapper} data-motion-decoration className={`relative h-full w-full ${className}`} aria-hidden="true">
      <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
    </div>
  );
}
