"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api";

export function AdminPasswordSetupView() {
  const router = useRouter();
  const [phase, setPhase] = useState<"checking" | "ready" | "done">("checking");
  const [ownerName, setOwnerName] = useState("the administrator");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The setup screen is only usable while the owner/admin has no password yet.
  useEffect(() => {
    api
      .adminSetupStatus()
      .then((s) => {
        if (!s.needs_admin_password) {
          router.replace("/login");
          return;
        }
        if (s.owner_name) setOwnerName(s.owner_name);
        setPhase("ready");
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.setupAdminPassword({ password, confirm_password: confirm });
      setPassword("");
      setConfirm("");
      setPhase("done");
      setTimeout(() => router.replace("/login"), 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the password");
    } finally {
      setBusy(false);
    }
  }

  if (phase === "checking") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center">
      <div className="mb-6 flex items-center gap-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <ShieldCheck className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">Create administrator password</h1>
          <p className="text-sm text-muted-foreground">
            First-time setup for {ownerName}. This screen locks once a password exists.
          </p>
        </div>
      </div>

      {phase === "done" ? (
        <div className="rounded-2xl border border-border bg-card p-6 text-sm">
          <p className="font-medium">Password created.</p>
          <p className="mt-1 text-muted-foreground">Redirecting you to sign in…</p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">New password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Confirm password</span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <p className="text-xs text-muted-foreground">At least 8 characters. Stored hashed — never in plain text.</p>
          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
          ) : null}
          <button
            type="submit"
            disabled={busy || !password || !confirm}
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            Create password
          </button>
        </form>
      )}
    </div>
  );
}
