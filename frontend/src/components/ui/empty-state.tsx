import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

/** A composed "nothing here yet" panel: what this is, why it is empty, and the next step. */
export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body?: string; action?: { label: string; href: string } }) {
  return (
    <div className="mx-auto flex max-w-[460px] flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-6 py-14 text-center">
      <Icon className="mb-2 h-7 w-7 text-primary" aria-hidden="true" />
      <p className="text-base font-semibold">{title}</p>
      {body ? <p className="max-w-[40ch] text-sm leading-relaxed text-muted-foreground">{body}</p> : null}
      {action ? <Link href={action.href} className={`${buttonVariants()} mt-3`}>{action.label}</Link> : null}
    </div>
  );
}
