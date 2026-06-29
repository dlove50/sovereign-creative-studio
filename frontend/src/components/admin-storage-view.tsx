"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Database, HardDrive, Loader2, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import type { AdminStorageReport, StorageCleanupPlan, StorageCleanupResult } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AdminStorageView() {
  const [report, setReport] = useState<AdminStorageReport | null>(null);
  const [plan, setPlan] = useState<StorageCleanupPlan | null>(null);
  const [result, setResult] = useState<StorageCleanupResult | null>(null);
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setReport(await api.getAdminStorage());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load storage report");
    } finally {
      setLoading(false);
    }
  }

  async function createPlan() {
    setPlanning(true);
    setError(null);
    setResult(null);
    try {
      setPlan(await api.createStorageCleanupPlan());
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create cleanup plan");
    } finally {
      setPlanning(false);
    }
  }

  async function execute() {
    if (!plan || confirm !== plan.confirm_phrase) return;
    setExecuting(true);
    setError(null);
    try {
      setResult(await api.executeStorageCleanup(confirm));
      setPlan(await api.createStorageCleanupPlan());
      setReport(await api.getAdminStorage());
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not execute cleanup");
    } finally {
      setExecuting(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading && !report) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/admin" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Admin
      </Link>

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {result ? (
        <div className="rounded-md border border-primary/30 bg-primary/10 p-3 text-sm">
          {result.message}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Local storage inspection and safe cleanup</p>
          <p className="text-xs text-muted-foreground">
            Always create a backup first. Cleanup is dry-run-first and protects original uploads plus live referenced assets.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
          <Button type="button" size="sm" onClick={createPlan} disabled={planning}>
            {planning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            Dry-run cleanup
          </Button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard label="Total size" value={formatBytes(report?.total_size_bytes ?? 0)} icon={HardDrive} />
        <StatCard label="Files" value={report?.total_file_count ?? 0} icon={Database} />
        <StatCard label="Cleanup candidates" value={plan?.total_candidate_count ?? "Dry-run first"} icon={ShieldCheck} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Folder Sizes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {report?.folders.map((folder) => (
              <div key={folder.name} className="flex items-center justify-between rounded-md border border-border p-3">
                <div>
                  <p className="text-sm font-medium">{folder.name}</p>
                  <p className="text-xs text-muted-foreground">{folder.file_count} files</p>
                </div>
                <Badge variant="outline">{formatBytes(folder.size_bytes)}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Largest Files</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {report?.largest_files.map((file) => (
              <div key={file.path} className="rounded-md border border-border p-3">
                <p className="break-all text-sm font-medium">{file.path}</p>
                <p className="mt-1 text-xs text-muted-foreground">{formatBytes(file.size_bytes)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cleanup Dry-Run Plan</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-border bg-background/40 p-3">
            <p className="text-sm font-medium">Protected by cleanup</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(plan?.protected ?? [
                "Original uploads",
                "Live referenced generated assets",
                "Newest backups",
                "Workflow config, database, and env files",
              ]).map((item) => (
                <Badge key={item} variant="outline">{item}</Badge>
              ))}
            </div>
          </div>

          {!plan ? (
            <p className="text-sm text-muted-foreground">Run a dry-run plan before deleting anything.</p>
          ) : (
            <>
              <div className="grid gap-3 md:grid-cols-3">
                <StatCard label="Candidate files" value={plan.total_candidate_count} icon={Trash2} />
                <StatCard label="Candidate size" value={formatBytes(plan.total_candidate_bytes)} icon={HardDrive} />
                <StatCard label="Confirmation" value={plan.confirm_phrase} icon={ShieldCheck} compact />
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(plan.by_category).map(([category, count]) => (
                  <Badge key={category} variant="muted">{category}: {count}</Badge>
                ))}
              </div>
              <div className="max-h-96 space-y-2 overflow-auto pr-1">
                {plan.candidates.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No safe cleanup candidates found.</p>
                ) : (
                  plan.candidates.map((candidate) => (
                    <div key={`${candidate.category}-${candidate.path}`} className="rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="break-all text-sm font-medium">{candidate.path}</p>
                        <Badge variant="outline">{formatBytes(candidate.size_bytes)}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{candidate.category}</p>
                    </div>
                  ))
                )}
              </div>
              {plan.candidates.length > 0 ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3">
                  <p className="text-sm font-medium">Execute cleanup</p>
                  <p className="text-xs text-muted-foreground">
                    Type <span className="font-mono">{plan.confirm_phrase}</span> exactly. The backend re-validates all protection rules before deleting.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <input
                      className="min-w-72 rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
                      onChange={(event) => setConfirm(event.target.value)}
                      placeholder={plan.confirm_phrase}
                      value={confirm}
                    />
                    <Button type="button" variant="destructive" size="sm" onClick={execute} disabled={executing || confirm !== plan.confirm_phrase}>
                      {executing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      Delete safe candidates
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ compact = false, icon: Icon, label, value }: { compact?: boolean; icon: typeof HardDrive; label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <p className={`${compact ? "truncate font-mono text-sm" : "text-xl font-semibold"}`}>{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[unit]}`;
}
