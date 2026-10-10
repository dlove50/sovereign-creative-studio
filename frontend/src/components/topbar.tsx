"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { GemIcon } from "@/components/gem-icon";
import { CountUp } from "@/components/motion/count-up";
import { Ban, LogOut, Monitor, Sparkles, UserCircle, Zap } from "lucide-react";

import { api } from "@/lib/api";
import { ADMIN_NAV, CREATE_NAV, CREATOR_NAV, RAIL_NAV } from "@/lib/navigation";
import { isAuthRoute } from "@/lib/routes";
import { Badge } from "@/components/ui/badge";
import { MobileNavigation } from "@/components/mobile-navigation";
import { useMotionPreference } from "@/components/motion/motion-provider";
import type { MotionPreference } from "@/lib/motion-preference";

const ALL_NAV = [...RAIL_NAV, ...CREATE_NAV, ...CREATOR_NAV, ...ADMIN_NAV];
const MOTION_OPTIONS: { value: MotionPreference; label: string; detail: string; icon: typeof Monitor }[] = [
  { value: "system", label: "Follow system", detail: "Respect Windows settings", icon: Monitor },
  { value: "on", label: "Always on", detail: "Show interface motion", icon: Zap },
  { value: "off", label: "Off", detail: "Keep the interface still", icon: Ban },
];

/** The page pill at the top left, like HeyGen's "Home" / "Avatars" label. */
function pageTitle(pathname: string) {
  if (pathname.startsWith("/movies/")) return "Scene by scene";
  const match = ALL_NAV.filter((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match?.label ?? "Sovereign";
}

export function Topbar() {
  const router = useRouter();
  const pathname = usePathname();
  const onAuthRoute = isAuthRoute(pathname);
  const [credits, setCredits] = useState<number | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [authed, setAuthed] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLButtonElement>(null);
  const { preference, setPreference } = useMotionPreference();

  useEffect(() => {
    // Identity + credits come from the real logged-in session only (authMe ignores
    // the "act as" header), so the greeting never reflects an impersonated user.
    api
      .authMe()
      .then((u) => {
        setCredits(u.credits);
        setName(u.name);
        setAuthed(true);
        setIsAdmin(u.role === "owner_admin");
      })
      .catch(() => {
        setCredits(null);
        setName(null);
        setAuthed(false);
        setIsAdmin(false);
      });
  }, [pathname]);

  useEffect(() => {
    function onClick(e: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && open) {
        setOpen(false);
        accountRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function logout() {
    await api.logout();
    setOpen(false);
    router.push("/login");
    router.refresh();
  }

  // Clean logged-out header on the auth/setup screens — no greeting, credits, or menu.
  if (onAuthRoute) {
    return (
      <header className="flex h-16 items-center border-b border-border px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold">Sovereign Creative Studio</span>
        </Link>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border/80 bg-background/85 px-4 backdrop-blur-xl sm:px-6 md:px-8 lg:px-10">
      <div className="flex items-center gap-2 md:hidden">
        <MobileNavigation isAdmin={isAdmin} />
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold">Sovereign</span>
        </Link>
      </div>
      <div className="hidden md:block">
        <span className="rounded-xl border border-border bg-card/70 px-3 py-1.5 text-sm font-medium">{pageTitle(pathname)}</span>
      </div>

      <div className="flex items-center gap-3">
        <Link href="/credits" aria-label="Credits" className="flex min-h-11 items-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <div className="flex min-h-10 items-center gap-1.5 rounded-lg border border-primary/30 bg-gradient-to-r from-primary/15 to-transparent px-3 py-1.5 transition-colors hover:border-primary hover:bg-primary/20">
            <GemIcon className="h-4 w-4" />
            <span className="tabular text-sm font-semibold text-foreground">{credits === null ? "—" : <CountUp value={credits} />}</span>
          </div>
        </Link>

        <div className="relative" ref={menuRef}>
          <button
            ref={accountRef}
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex h-11 w-11 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Account menu"
            aria-expanded={open}
            aria-controls="account-panel"
          >
            <UserCircle className="h-5 w-5" />
          </button>
          {open ? (
            <div id="account-panel" className="absolute right-0 z-50 mt-2 w-72 overflow-hidden rounded-xl border border-border/80 bg-card/95 p-2 shadow-elevated backdrop-blur-xl">
              <div className="border-b border-border px-2 pb-3 pt-1">
                <p className="truncate text-sm font-semibold">{name || "Sovereign account"}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">Studio preferences and account</p>
              </div>
              <div className="py-2" role="radiogroup" aria-label="Motion">
                <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Motion</p>
                {MOTION_OPTIONS.map((option) => {
                  const Icon = option.icon;
                  const selected = preference === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-label={option.label}
                      aria-checked={selected}
                      onClick={() => setPreference(option.value)}
                      className="flex min-h-11 w-full items-center gap-3 rounded-lg px-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span className={selected ? "text-primary" : "text-muted-foreground"}><Icon className="h-4 w-4" aria-hidden="true" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{option.label}</span>
                        <span aria-hidden="true" className="block text-xs text-muted-foreground">{option.detail}</span>
                      </span>
                      <span aria-hidden="true" className={selected ? "h-2 w-2 rounded-full bg-primary shadow-[0_0_10px_hsl(var(--primary)/0.6)]" : "h-2 w-2 rounded-full border border-border"} />
                    </button>
                  );
                })}
              </div>
              <div className="border-t border-border pt-2">
              <Link href="/profile" onClick={() => setOpen(false)} className="flex min-h-11 items-center rounded-lg px-3 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Profile
              </Link>
              <Link href="/credits" onClick={() => setOpen(false)} className="flex min-h-11 items-center rounded-lg px-3 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Credits
              </Link>
              {authed ? (
                <button
                  type="button"
                  onClick={logout}
                  className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-destructive hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <LogOut className="h-4 w-4" /> Log out
                </button>
              ) : (
                <Link href="/login" onClick={() => setOpen(false)} className="flex min-h-11 items-center rounded-lg px-3 text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  Sign in
                </Link>
              )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
