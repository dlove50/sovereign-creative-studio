"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, LogIn, Sparkles } from "lucide-react";

import { api } from "@/lib/api";

export function LoginView() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);

  // First run: if the administrator hasn't created a password yet, login can
  // never succeed — send them to the secure setup screen instead.
  useEffect(() => {
    api
      .adminSetupStatus()
      .then((s) => {
        if (s.needs_admin_password) {
          setNeedsSetup(true);
          router.replace("/setup/admin-password");
        }
      })
      .catch(() => {});
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.login({ username: username.trim(), password });
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-sm flex-col justify-center">
      <div className="mb-6 flex items-center gap-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Sparkles className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="text-sm text-muted-foreground">Welcome back to your studio.</p>
        </div>
      </div>
      {needsSetup ? (
        <div className="mb-4 rounded-2xl border border-border bg-card p-4 text-sm">
          <p className="font-medium">First-time setup</p>
          <p className="mt-1 text-muted-foreground">
            The administrator password hasn&apos;t been created yet.{" "}
            <Link href="/setup/admin-password" className="text-primary hover:underline">
              Create administrator password
            </Link>
            .
          </p>
        </div>
      ) : null}
      <form onSubmit={submit} className="space-y-4 rounded-2xl border border-border bg-card p-6">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
        ) : null}
        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
          Sign in
        </button>
        <p className="text-center text-sm text-muted-foreground">
          New here?{" "}
          <Link href="/signup" className="text-primary hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </div>
  );
}
