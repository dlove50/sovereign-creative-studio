"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { GemIcon } from "@/components/gem-icon";
import { Coins, LogOut, Sparkles, UserCircle } from "lucide-react";

import { api } from "@/lib/api";
import { ADMIN_NAV, CREATE_NAV, CREATOR_NAV, RAIL_NAV } from "@/lib/navigation";
import { isAuthRoute } from "@/lib/routes";
import { Badge } from "@/components/ui/badge";
import { MobileNavigation } from "@/components/mobile-navigation";

const ALL_NAV = [...RAIL_NAV, ...CREATE_NAV, ...CREATOR_NAV, ...ADMIN_NAV];

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
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

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
    <header className="flex h-16 items-center justify-between border-b border-border px-6">
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
        <Link href="/credits">
          <div className="flex items-center gap-1.5 rounded-lg border border-primary/30 bg-gradient-to-r from-primary/15 to-transparent px-3 py-1.5 transition-colors hover:border-primary hover:bg-primary/20">
            <GemIcon className="h-4 w-4" />
            <span className="text-sm font-semibold text-foreground">{credits === null ? "—" : credits}</span>
          </div>
        </Link>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-border text-muted-foreground hover:bg-muted"
            aria-label="Account menu"
          >
            <UserCircle className="h-5 w-5" />
          </button>
          {open ? (
            <div className="absolute right-0 z-50 mt-2 w-44 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
              <Link href="/profile" onClick={() => setOpen(false)} className="block px-4 py-2 text-sm hover:bg-muted">
                Profile
              </Link>
              <Link href="/credits" onClick={() => setOpen(false)} className="block px-4 py-2 text-sm hover:bg-muted">
                Credits
              </Link>
              {authed ? (
                <button
                  type="button"
                  onClick={logout}
                  className="flex w-full items-center gap-2 border-t border-border px-4 py-2 text-left text-sm text-destructive hover:bg-muted"
                >
                  <LogOut className="h-4 w-4" /> Log out
                </button>
              ) : (
                <Link href="/login" onClick={() => setOpen(false)} className="block border-t border-border px-4 py-2 text-sm hover:bg-muted">
                  Sign in
                </Link>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
