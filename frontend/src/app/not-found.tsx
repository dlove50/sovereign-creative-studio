import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight, Compass } from "lucide-react";

export const metadata: Metadata = { title: "Page not found | Sovereign Creative Studio" };

const WAYS_ON = [
  { href: "/", label: "Home", note: "Your setup and the Director templates." },
  { href: "/apps", label: "App library", note: "Every tool in the studio, searchable." },
  { href: "/gallery", label: "Gallery", note: "Pictures and videos you have made." },
  { href: "/projects", label: "Projects", note: "Drafts and finished work." },
];

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60dvh] max-w-[640px] flex-col justify-center py-10">
      <Compass className="mb-5 h-8 w-8 text-primary" aria-hidden="true" />
      <p className="text-sm font-medium text-muted-foreground">Error 404</p>
      <h1 className="mt-1 text-5xl font-extrabold tracking-[-0.03em]">That page isn’t here.</h1>
      <p className="mt-3 max-w-[52ch] text-[15px] leading-relaxed text-muted-foreground">
        The address may be mistyped, or the page was moved. Pick one of these to carry on.
      </p>
      <ul className="mt-8 grid gap-3 sm:grid-cols-2">
        {WAYS_ON.map((w) => (
          <li key={w.href}>
            <Link
              href={w.href}
              className="group flex items-center justify-between gap-3 rounded-2xl border border-border bg-card/60 px-4 py-3 transition duration-200 hover:border-primary/60 hover:bg-card motion-safe:active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span>
                <span className="block text-sm font-semibold">{w.label}</span>
                <span className="block text-[13px] text-muted-foreground">{w.note}</span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 motion-safe:group-hover:translate-x-0.5" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
