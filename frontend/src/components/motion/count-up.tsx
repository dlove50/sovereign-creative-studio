"use client";

import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";

import { useMotionPreference } from "./motion-provider";

/** Shows a number that tweens from its previous value to the new one. Plain text for reduced motion. */
export function CountUp({ value }: { value: number }) {
  const { motionEnabled } = useMotionPreference();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (!motionEnabled || from.current === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const state = { n: from.current };
    const tween = gsap.to(state, {
      n: value, duration: 0.8, ease: "power2.out",
      onUpdate: () => setShown(Math.round(state.n)),
      onComplete: () => { from.current = value; setShown(value); },
    });
    return () => { tween.kill(); from.current = value; };
  }, [motionEnabled, value]);
  return <>{shown}</>;
}
