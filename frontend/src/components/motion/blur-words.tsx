"use client";

import { useRef } from "react";
import { gsap } from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/**
 * Headline text whose words sharpen in one after another, from blurred and slightly low.
 * Same idea as React Bits' BlurText, written with GSAP so no extra animation library is needed.
 * Screen readers get the whole sentence at once; reduced-motion users get plain text.
 */
export function BlurWords({ text, className, delay = 0 }: { text: string; className?: string; delay?: number }) {
  const root = useRef<HTMLSpanElement>(null);
  const words = text.split(/\s+/).filter(Boolean);

  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.fromTo(
        root.current!.querySelectorAll("[data-word]"),
        { opacity: 0, filter: "blur(12px)", y: 14 },
        { opacity: 1, filter: "blur(0px)", y: 0, duration: 0.7, ease: "power3.out", stagger: 0.09, delay, clearProps: "filter,transform" },
      );
    });
    return () => mm.revert();
  }, { scope: root, dependencies: [text] });

  return (
    <span ref={root} className={className} aria-label={text}>
      {words.map((word, i) => (
        <span key={`${word}-${i}`} data-word aria-hidden="true" className="inline-block">
          {word}{i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
}
