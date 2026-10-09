"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Coins, ShieldCheck, Sparkles } from "lucide-react";

import { GemIcon } from "@/components/gem-icon";
import { api } from "@/lib/api";
import type { AvatarJob } from "@/lib/types";
import { AVATAR_NAV, CREATE_NAV, RAIL_NAV, type NavigationItem } from "@/lib/navigation";
import { isAuthRoute } from "@/lib/routes";
import { cn } from "@/lib/utils";

const RECENTS_LIMIT = 10;

function isActive(href: string, pathname: string) {
  return href === "/" || href === "/admin" ? pathname === href : pathname.startsWith(href);
}

function timeAgo(iso: string) {
  const minutes = Math.max(1, Math.round((Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function RailItem({ item, pathname, onHover }: { item: NavigationItem; pathname: string; onHover?: () => void }) {
  const active = isActive(item.href, pathname);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      onMouseEnter={onHover}
      onFocus={onHover}
      className="group flex flex-col items-center gap-1 py-1.5 text-[11px] font-medium focus-visible:outline-none"
    >
      <span
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-xl transition-colors group-focus-visible:ring-2 group-focus-visible:ring-ring",
          active ? "bg-raised text-foreground" : "text-muted-foreground group-hover:bg-raised group-hover:text-foreground",
        )}
      >
        {item.href === "/credits" ? <GemIcon className="h-5 w-5" /> : <Icon className="h-5 w-5" aria-hidden="true" />}
      </span>
      <span className={active ? "text-foreground" : "text-muted-foreground"}>{item.label}</span>
    </Link>
  );
}

/** HeyGen-style navigation: a slim icon rail plus a "Create" fly-out with recents. */
export function AppRail() {
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState(false);
  const [initial, setInitial] = useState("S");
  const [panel, setPanel] = useState<"create" | "avatars" | null>(null);
  const open = panel === "create";
  const [recents, setRecents] = useState<AvatarJob[]>([]);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api
      .authMe()
      .then((u) => {
        setIsAdmin(u.role === "owner_admin");
        setInitial((u.name || "S").trim().charAt(0).toUpperCase());
      })
      .catch(() => setIsAdmin(false));
  }, [pathname]);

  useEffect(() => setPanel(null), [pathname]);

  useEffect(() => {
    if (!open) return;
    api
      .listAvatarJobs()
      .then((jobs) => setRecents(jobs.filter((j) => j.status === "completed").slice(0, RECENTS_LIMIT)))
      .catch(() => setRecents([]));
  }, [open]);

  if (isAuthRoute(pathname)) return null;

  function show(which: "create" | "avatars" = "create") {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setPanel(which);
  }
  function hideSoon() {
    closeTimer.current = setTimeout(() => setPanel(null), 180);
  }

  return (
    <div className="relative hidden shrink-0 md:block" onMouseLeave={hideSoon}>
      <aside className="sticky top-0 flex h-screen w-[76px] flex-col items-center gap-2 border-r border-border bg-card/60 py-4">
        <button
          type="button"
          onMouseEnter={() => show("create")}
          onFocus={() => show("create")}
          onClick={() => setPanel((v) => (v === "create" ? null : "create"))}
          aria-expanded={open}
          aria-label="Create"
          className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 via-primary to-violet-500 text-primary-foreground shadow-[0_0_24px_hsl(197_87%_54%/0.35)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Sparkles className="h-5 w-5" />
        </button>
        <nav className="flex flex-col gap-1" aria-label="Main">
          {RAIL_NAV.map((item) => (
            <RailItem key={item.href} item={item} pathname={pathname} onHover={() => (item.href === "/avatars" ? show("avatars") : setPanel(null))} />
          ))}
        </nav>
        <div className="mt-auto flex flex-col items-center gap-2">
          {isAdmin ? <RailItem item={{ href: "/admin", label: "Admin", icon: ShieldCheck }} pathname={pathname} /> : null}
          <RailItem item={{ href: "/credits", label: "Credits", icon: Coins }} pathname={pathname} />
          <Link
            href="/profile"
            aria-label="Profile"
            className="mt-1 flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 text-sm font-semibold text-white ring-2 ring-border focus-visible:outline-none focus-visible:ring-ring"
          >
            {initial}
          </Link>
        </div>
      </aside>

      {panel === "avatars" ? (
        <div
          onMouseEnter={() => show("avatars")}
          className="absolute left-[76px] top-0 z-40 flex h-screen w-[248px] flex-col border-r border-border bg-card shadow-2xl shadow-black/40"
        >
          <p className="px-5 pb-2 pt-5 text-xs font-medium text-muted-foreground">Manage avatars</p>
          <nav className="flex flex-col gap-0.5 px-3" aria-label="Manage avatars">
            {AVATAR_NAV.map((item) => {
              const Icon = item.icon;
              const active = item.href === "/avatars" ? pathname === "/avatars" || /^\/avatars\/(?!looks)/.test(pathname) : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "bg-raised text-foreground" : "text-foreground/85 hover:bg-raised",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      ) : null}

      {open ? (
        <div
          onMouseEnter={() => show("create")}
          className="absolute left-[76px] top-0 z-40 flex h-screen w-[248px] flex-col border-r border-border bg-card shadow-2xl shadow-black/40"
        >
          <p className="px-5 pb-2 pt-5 text-xs font-medium text-muted-foreground">Create</p>
          <nav className="flex flex-col gap-0.5 px-3" aria-label="Create">
            {CREATE_NAV.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href, pathname);
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "bg-raised text-foreground" : "text-foreground/85 hover:bg-raised",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-5 flex items-center justify-between px-5 pb-1">
            <p className="text-xs font-medium text-muted-foreground">Recents</p>
            <Link href="/assets-library" className="text-xs text-muted-foreground hover:text-foreground">
              See all
            </Link>
          </div>
          <ul className="flex-1 overflow-y-auto px-3 pb-4">
            {recents.length === 0 ? (
              <li className="px-3 py-2 text-xs text-muted-foreground">Your finished videos show up here.</li>
            ) : (
              recents.map((job) => (
                <li key={job.id}>
                  <Link href="/avatars/create" className="block rounded-lg px-3 py-2 hover:bg-raised">
                    <span className="block truncate text-sm">{job.script_text || "Talking avatar"}</span>
                    <span className="block text-[11px] text-muted-foreground">{timeAgo(job.created_at)} · Avatar video</span>
                  </Link>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
