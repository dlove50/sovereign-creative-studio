"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// Smooth scrolling is only for browsing pages. The editors, Music Lab, forms and pop-ups keep normal scrolling so
// timelines, lists and dialogs never fight it.
const SMOOTH_PAGES = new Set(["/", "/gallery", "/projects", "/apps", "/avatars", "/developers", "/brand"]);

// Inner scrollers and dialogs scroll on their own, even on a smooth page.
const OWN_SCROLL = '[role="dialog"], [role="log"], [data-lenis-prevent], select, textarea';

export function MotionProvider() {
  const pathname = usePathname();

  useEffect(() => {
    if (!SMOOTH_PAGES.has(pathname)) return;
    const quiet = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (quiet.matches) return;

    const lenis = new Lenis({
      autoRaf: false,
      lerp: 0.1,
      prevent: (node) => node instanceof Element && node.closest(OWN_SCROLL) !== null,
    });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    // Someone who turns reduced motion on while the page is open gets normal scrolling straight away.
    const stopIfAsked = () => { if (quiet.matches) lenis.destroy(); };
    quiet.addEventListener("change", stopIfAsked);

    return () => {
      quiet.removeEventListener("change", stopIfAsked);
      gsap.ticker.remove(tick);
      lenis.destroy();
      ScrollTrigger.refresh();
    };
  }, [pathname]);

  return null;
}
