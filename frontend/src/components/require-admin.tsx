"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, ShieldAlert } from "lucide-react";

import { api } from "@/lib/api";

// Client-side admin guard. Family/guest users see a clear message instead of
// admin tools. The backend independently enforces admin-only access, so this is
// UX, not the security boundary.
export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "allowed" | "denied">("checking");

  useEffect(() => {
    // Gate on the real session (authMe), not the "act as" header, so the owner/admin
    // is never locked out of admin tools while impersonating a family user.
    api
      .authMe()
      .then((u) => setState(u.role === "owner_admin" ? "allowed" : "denied"))
      .catch(() => setState("denied"));
  }, []);

  if (state === "checking") {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (state === "denied") {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
        <ShieldAlert className="h-8 w-8 text-muted-foreground" />
        <p className="text-base font-semibold">Admin access required</p>
        <p className="max-w-md text-sm text-muted-foreground">
          This area is for the studio owner/admin. Head back to your creator dashboard.
        </p>
        <Link
          href="/"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          Go to Home
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
