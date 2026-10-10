"use client";

import { useEffect, useRef, type RefObject } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

import { useMotionPreference } from "./motion-provider";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const MAX_ANIMATED = 24; // cards beyond this simply appear; a long list should not take seconds to arrive

/**
 * The direct children of `container` rise in one after another the first time the list has content.
 * Later changes (deleting a card, loading more) are not animated again. Skipped for reduced motion.
 */
export function useStaggerIn(container: RefObject<HTMLElement | null>, count: number) {
  const played = useRef(false);
  const { motionEnabled } = useMotionPreference();
  useGSAP(() => {
    const root = container.current;
    if (!root || !motionEnabled || count === 0 || played.current) return;
    played.current = true;
    const items = Array.from(root.children).slice(0, MAX_ANIMATED);
    const tween = gsap.from(items, {
      opacity: 0, y: 18, duration: 0.5, ease: "power2.out", stagger: 0.04, clearProps: "opacity,transform",
    });
    return () => tween.revert();
  }, { scope: container, dependencies: [count > 0, motionEnabled] });
}

/** Elements marked `data-reveal` inside `container` fade up as they scroll into view. */
export function useScrollReveal(container: RefObject<HTMLElement | null>) {
  const { motionEnabled } = useMotionPreference();
  useGSAP(() => {
    const root = container.current;
    if (!root || !motionEnabled) return;
    const tweens = gsap.utils.toArray<HTMLElement>(root.querySelectorAll("[data-reveal]")).map((el) =>
      gsap.from(el, {
        opacity: 0, y: 28, duration: 0.7, ease: "power2.out", clearProps: "opacity,transform",
        scrollTrigger: { trigger: el, start: "top 88%", once: true },
      }),
    );
    return () => tweens.forEach((tween) => tween.revert());
  }, { scope: container, dependencies: [motionEnabled] });
}

/**
 * A soft light follows the pointer across any child marked `data-spotlight` (see `.spotlight` in globals.css).
 * One listener on the container, not one per card; nothing runs while the pointer is elsewhere.
 */
export function useSpotlight(container: RefObject<HTMLElement | null>) {
  const { motionEnabled } = useMotionPreference();
  useEffect(() => {
    const root = container.current;
    if (!root || !motionEnabled) return;
    const move = (event: PointerEvent) => {
      const card = (event.target as Element | null)?.closest<HTMLElement>("[data-spotlight]");
      if (!card || !root.contains(card)) return;
      const box = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${event.clientX - box.left}px`);
      card.style.setProperty("--my", `${event.clientY - box.top}px`);
    };
    root.addEventListener("pointermove", move, { passive: true });
    return () => root.removeEventListener("pointermove", move);
  }, [container, motionEnabled]);
}
