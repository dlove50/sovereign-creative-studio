"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import {
  MOTION_STORAGE_KEY,
  parseMotionPreference,
  resolveMotionEnabled,
  type MotionPreference,
} from "@/lib/motion-preference";

gsap.registerPlugin(ScrollTrigger);

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const SMOOTH_PAGES = new Set(["/", "/gallery", "/projects", "/apps", "/avatars", "/developers", "/brand"]);
const OWN_SCROLL = '[role="dialog"], [role="log"], [data-lenis-prevent], select, textarea';

type MotionContextValue = {
  preference: MotionPreference;
  motionEnabled: boolean;
  setPreference: (preference: MotionPreference) => void;
};

const MotionContext = createContext<MotionContextValue | null>(null);

export function useMotionPreference(): MotionContextValue {
  const value = useContext(MotionContext);
  if (!value) throw new Error("useMotionPreference must be used inside MotionProvider");
  return value;
}

export function MotionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [preference, setPreferenceState] = useState<MotionPreference>("system");
  const [systemReduced, setSystemReduced] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const motionEnabled = hydrated && resolveMotionEnabled(preference, systemReduced);

  const setPreference = useCallback((next: MotionPreference) => {
    localStorage.setItem(MOTION_STORAGE_KEY, next);
    setPreferenceState(next);
  }, []);

  useEffect(() => {
    const media = window.matchMedia(REDUCED_MOTION_QUERY);
    const syncSystem = () => setSystemReduced(media.matches);
    const syncStorage = (event: StorageEvent) => {
      if (event.key === MOTION_STORAGE_KEY) setPreferenceState(parseMotionPreference(event.newValue));
    };

    setPreferenceState(parseMotionPreference(localStorage.getItem(MOTION_STORAGE_KEY)));
    syncSystem();
    setHydrated(true);
    media.addEventListener("change", syncSystem);
    window.addEventListener("storage", syncStorage);
    return () => {
      media.removeEventListener("change", syncSystem);
      window.removeEventListener("storage", syncStorage);
    };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.motion = motionEnabled ? "on" : "off";
  }, [motionEnabled]);

  useEffect(() => {
    if (!motionEnabled || !SMOOTH_PAGES.has(pathname)) return;

    const lenis = new Lenis({
      autoRaf: false,
      lerp: 0.1,
      prevent: (node) => node instanceof Element && node.closest(OWN_SCROLL) !== null,
    });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(tick);
      lenis.destroy();
      ScrollTrigger.refresh();
    };
  }, [motionEnabled, pathname]);

  const value = useMemo(
    () => ({ preference, motionEnabled, setPreference }),
    [motionEnabled, preference, setPreference],
  );

  return <MotionContext.Provider value={value}>{children}</MotionContext.Provider>;
}
