"use client";

// Adapted from React Bits AnimatedContent, copyright (c) 2026 David Haz.
// Full MIT + Commons Clause notice: docs/third-party/react-bits-LICENSE.md.
import { useEffect, useRef, type ReactNode } from "react";
import { gsap } from "gsap";

export function StudioReveal({ children, scene }: { children: ReactNode; scene: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      const targets = ref.current?.querySelectorAll("[data-studio-enter]");
      gsap.fromTo(targets?.length ? targets : ref.current,
        { y: 10, opacity: 0.9 },
        { y: 0, opacity: 1, duration: 0.45, stagger: 0.035, ease: "power3.out", clearProps: "transform,opacity" });
    }, ref);
    return () => media.revert();
  }, [scene]);
  return <div ref={ref}>{children}</div>;
}
