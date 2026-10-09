"use client";

import { useEffect, useState } from "react";
import { Coins, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { LoadError } from "@/components/ui/load-error";

export function CreditsView() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api.getMe().then(setUser).catch((e) => setError(e instanceof Error ? e.message : "The studio didn't answer.")).finally(() => setLoading(false));
  };
  useEffect(load, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (error) return <LoadError what="your credits" message={error} onRetry={load} />;

  return (
    <div className="max-w-lg space-y-5">
      <div className="flex items-center gap-4 rounded-2xl border border-border bg-card p-6">
        <span className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary/15 text-primary">
          <Coins className="h-7 w-7" />
        </span>
        <div>
          <p className="text-3xl font-semibold">{user?.credits ?? "—"}</p>
          <p className="text-sm text-muted-foreground">credits available</p>
        </div>
      </div>

      <div className="space-y-2 rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">How credits work</p>
        <ul className="list-inside list-disc space-y-1">
          <li>Each successful video generation costs 10 credits.</li>
          <li>Failed generations are never charged.</li>
          <li>Image and copy creation may use credits depending on settings.</li>
          <li>Need more? Ask the studio admin to add credits to your account.</li>
        </ul>
      </div>
    </div>
  );
}
