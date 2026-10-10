"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Sparkles, X } from "lucide-react";

import { ADMIN_NAV, CREATOR_NAV, isNavigationActive, type NavigationItem } from "@/lib/navigation";
import { cn } from "@/lib/utils";

function MobileNavLink({ item, pathname, onNavigate }: {
  item: NavigationItem;
  pathname: string;
  onNavigate: () => void;
}) {
  const active = isNavigationActive(item.href, pathname);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active
          ? "bg-primary/15 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {item.label}
    </Link>
  );
}

export function MobileNavigation({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousPathname = useRef(pathname);

  useEffect(() => {
    if (previousPathname.current !== pathname) setOpen(false);
    previousPathname.current = pathname;
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
      if (event.key === "Tab" && panelRef.current) {
        const focusable = Array.from(
          panelRef.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Open navigation"
        aria-expanded={open}
        aria-controls="mobile-navigation"
        onClick={() => setOpen(true)}
        className="flex h-11 w-11 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      {open ? createPortal(
        <div className="fixed inset-0 z-[70] md:hidden" role="dialog" aria-modal="true" aria-label="Studio navigation">
          <div
            aria-hidden="true"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/65"
          />
          <aside
            ref={panelRef}
            id="mobile-navigation"
            className="absolute inset-y-0 left-0 flex w-[86vw] max-w-xs flex-col overflow-y-auto border-r border-border bg-card px-4 py-5 shadow-2xl"
          >
            <div className="mb-5 flex items-center justify-between px-2">
              <Link href="/" onClick={() => setOpen(false)} className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Sparkles className="h-5 w-5" aria-hidden="true" />
                </span>
                <span className="text-sm font-semibold leading-tight">
                  Sovereign
                  <span className="block text-xs font-normal text-muted-foreground">Creative Studio</span>
                </span>
              </Link>
              <button
                ref={closeRef}
                type="button"
                aria-label="Close navigation"
                onClick={() => {
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Create & work</p>
            <nav className="flex flex-col gap-1" aria-label="Creator tools">
              {CREATOR_NAV.map((item) => (
                <MobileNavLink key={item.href} item={item} pathname={pathname} onNavigate={() => setOpen(false)} />
              ))}
            </nav>

            {isAdmin ? (
              <>
                <p className="mt-6 border-t border-border px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Admin & advanced
                </p>
                <nav className="flex flex-col gap-1" aria-label="Admin tools">
                  {ADMIN_NAV.map((item) => (
                    <MobileNavLink key={item.href} item={item} pathname={pathname} onNavigate={() => setOpen(false)} />
                  ))}
                </nav>
              </>
            ) : null}
          </aside>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
