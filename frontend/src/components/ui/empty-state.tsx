import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

/** A composed "nothing here yet" panel: what this is, why it is empty, and the next step. */
export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body?: string; action?: { label: string; href: string } }) {
  return (
    <section aria-label={title} className="mx-auto flex max-w-[460px] flex-col items-center gap-2 rounded-2xl border border-dashed border-border/90 bg-subdued/45 px-6 py-14 text-center shadow-card">
      <span className="mb-2 flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
        <Icon className="h-6 w-6 text-primary" aria-hidden="true" />
      </span>
      <h2 className="text-base font-semibold">{title}</h2>
      {body ? <p className="max-w-[40ch] text-sm leading-relaxed text-muted-foreground">{body}</p> : null}
      {action ? <Link href={action.href} className={`${buttonVariants()} mt-3`}>{action.label}</Link> : null}
    </section>
  );
}
