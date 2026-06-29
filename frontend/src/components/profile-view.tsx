"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Coins, Loader2, LogOut, ShieldCheck, UserCircle } from "lucide-react";

import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function ProfileView() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [authed, setAuthed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Prefer the real signed-in account (authMe ignores the "act as" header). Only
    // when no session exists do we show the local owner fallback (getMe).
    (async () => {
      try {
        setUser(await api.authMe());
        setAuthed(true);
      } catch {
        setAuthed(false);
        try {
          setUser(await api.getMe());
        } catch {
          setUser(null);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function logout() {
    setBusy(true);
    try {
      await api.logout();
      router.push("/login");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-lg space-y-5">
      <div className="flex items-center gap-4 rounded-2xl border border-border bg-card p-6">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/15 text-primary">
          <UserCircle className="h-8 w-8" />
        </span>
        <div className="min-w-0">
          <p className="text-lg font-semibold">{user?.name ?? "Studio user"}</p>
          <p className="text-sm text-muted-foreground">
            {user?.username ? `@${user.username}` : user?.email}
          </p>
          <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <ShieldCheck className="h-3.5 w-3.5" />
              {user?.role === "owner_admin" ? "Admin" : "Creator"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Coins className="h-3.5 w-3.5" /> {user?.credits ?? 0} credits
            </span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href="/credits"
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
        >
          <Coins className="h-4 w-4" /> View credits
        </Link>
        {authed ? (
          <button
            type="button"
            onClick={logout}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
            Log out
          </button>
        ) : (
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Sign in
          </Link>
        )}
      </div>

      {!authed ? (
        <p className="text-xs text-muted-foreground">
          You&apos;re using this studio as the local owner. Sign in to use your own account.
        </p>
      ) : null}
    </div>
  );
}
