"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, UserPlus } from "lucide-react";

import { api } from "@/lib/api";

export function SignupView() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [requiresApproval, setRequiresApproval] = useState(false);

  useEffect(() => {
    api
      .authStatus()
      .then((s) => {
        setEnabled(s.public_signup_enabled);
        setRequiresApproval(s.requires_admin_approval);
      })
      .catch(() => setEnabled(true));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || password.length < 6 || password !== confirmPassword || busy) {
      if (password !== confirmPassword) setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.signup({ username: username.trim(), password, name: name.trim() || undefined });
      if (requiresApproval) {
        router.push("/login");
      } else {
        router.push("/");
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account");
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
          <h1 className="text-xl font-semibold">Create your account</h1>
          <p className="text-sm text-muted-foreground">Join the studio and start creating.</p>
        </div>
      </div>

      {!enabled ? (
        <div className="rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">
          Public signup is currently disabled. Ask the studio admin to create your account, then{" "}
          <Link href="/login" className="text-primary hover:underline">sign in</Link>.
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Display name (optional)</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
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
              autoComplete="new-password"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <span className="text-xs text-muted-foreground">At least 6 characters.</span>
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Confirm password</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          {requiresApproval ? (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              New accounts need admin approval before first sign-in.
            </p>
          ) : null}
          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
          ) : null}
          <button
            type="submit"
            disabled={busy || !username.trim() || password.length < 6 || password !== confirmPassword}
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            Create account
          </button>
          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">Sign in</Link>
          </p>
        </form>
      )}
    </div>
  );
}
