"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FlaskConical, Loader2, XCircle } from "lucide-react";

import { api } from "@/lib/api";
import type { FamilyUser, SandboxTopup, TopupPackage } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const STATUS_VARIANT: Record<SandboxTopup["status"], "muted" | "default" | "success" | "destructive"> = {
  pending: "default",
  completed: "success",
  cancelled: "muted",
  failed: "destructive",
};

export function AdminTopupsView() {
  const [packages, setPackages] = useState<TopupPackage[]>([]);
  const [users, setUsers] = useState<FamilyUser[]>([]);
  const [topups, setTopups] = useState<SandboxTopup[]>([]);
  const [userId, setUserId] = useState("");
  const [packageId, setPackageId] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [u, t] = await Promise.all([api.listFamilyUsers(), api.listTopups()]);
    setUsers(u);
    setTopups(t);
  }

  useEffect(() => {
    async function load() {
      try {
        const [pkgs, u, t] = await Promise.all([
          api.listTopupPackages(),
          api.listFamilyUsers(),
          api.listTopups(),
        ]);
        setPackages(pkgs);
        setUsers(u);
        setTopups(t);
        setUserId(u[0]?.id ?? "");
        setPackageId(pkgs[0]?.id ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load top-ups");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function createCheckout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!userId || !packageId || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTopup({ user_id: userId, package_id: packageId, note: note || null });
      setNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create top-up");
    } finally {
      setBusy(false);
    }
  }

  async function complete(id: string) {
    if (!window.confirm("Mark this top-up as paid and add its credits to the account?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.completeTopup(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not complete top-up");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.cancelTopup(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel top-up");
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
    <div className="space-y-6">
      <Link
        href="/admin"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to Admin
      </Link>

      <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
        <FlaskConical className="mt-0.5 h-5 w-5 text-amber-400" />
        <div className="text-sm">
          <p className="font-semibold text-amber-300">
            Local credits only — no real money is processed.
          </p>
          <p className="text-muted-foreground">
            Grants local credits to a family member. No cards, no payment providers,
            no billing. Completing a top-up posts to the local Credit Ledger.
          </p>
        </div>
      </div>

      {error ? (
        <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Credit packages</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {packages.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md border border-border bg-background/40 px-3 py-2 text-sm"
              >
                <span className="font-medium">{p.name}</span>
                <span className="text-muted-foreground">
                  {p.credits} credits · {p.price_display}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add local credits</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={createCheckout} className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Family user</label>
                <select value={userId} onChange={(e) => setUserId(e.target.value)} className={selectClass}>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.display_name} ({u.credit_balance} cr)
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Package</label>
                <select value={packageId} onChange={(e) => setPackageId(e.target.value)} className={selectClass}>
                  {packages.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} — {p.credits} credits ({p.price_display})
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Note (optional)</label>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. monthly family top-up"
                  className={selectClass}
                />
              </div>
              <Button type="submit" disabled={busy || !userId || !packageId}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
                Add credits
              </Button>
            </form>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent top-ups</CardTitle>
        </CardHeader>
        <CardContent>
          {topups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No top-ups yet.</p>
          ) : (
            <div className="space-y-2">
              {topups.map((t) => (
                <div
                  key={t.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-background/40 px-3 py-2 text-sm"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">
                      {t.user_name} · {t.package_name} · {t.credits} credits
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {t.amount_display} · created {new Date(t.created_at).toLocaleString()}
                      {t.completed_at ? ` · completed ${new Date(t.completed_at).toLocaleString()}` : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={STATUS_VARIANT[t.status]} className="capitalize">
                      {t.status}
                    </Badge>
                    {t.status === "pending" ? (
                      <>
                        <Button size="sm" onClick={() => complete(t.id)} disabled={busy}>
                          <CheckCircle2 className="h-4 w-4" /> Complete
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => cancel(t.id)} disabled={busy}>
                          <XCircle className="h-4 w-4" /> Cancel
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
