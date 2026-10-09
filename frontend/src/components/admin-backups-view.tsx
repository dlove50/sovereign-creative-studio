"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Database, Download, HardDriveDownload, Loader2, ShieldAlert, Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import type { Backup } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

export function AdminBackupsView() {
  const [backups, setBackups] = useState<Backup[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setBackups(await api.listBackups());
  }

  useEffect(() => {
    api
      .listBackups()
      .then(setBackups)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load backups"))
      .finally(() => setLoading(false));
  }, []);

  async function create() {
    setCreating(true);
    setError(null);
    try {
      await api.createBackup();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create backup");
    } finally {
      setCreating(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this backup? You will not be able to restore from it afterwards.")) return;
    setBusyId(id);
    setError(null);
    try {
      await api.deleteBackup(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete backup");
    } finally {
      setBusyId(null);
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

      <div className="flex items-start gap-3 rounded-lg border border-border bg-background/40 p-4">
        <Database className="mt-0.5 h-5 w-5 text-muted-foreground" />
        <div className="text-sm">
          <p className="font-semibold">Local / private backup — stored on this machine only.</p>
          <p className="text-muted-foreground">
            A backup is a timestamped ZIP under <code>backend/storage/backups/</code> containing the
            SQLite database, the <code>storage/</code> folder, workflow config, env files, workflow
            templates, and the README. No cloud, no external services.
          </p>
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
        <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-400" />
        <div className="text-sm">
          <p className="font-semibold text-amber-300">
            Restore is manual for safety. Do not overwrite the live database while the app is running.
          </p>
          <p className="text-muted-foreground">
            Stop the studio first, copy your current files somewhere safe, then restore from a ZIP. See
            the “Backup and Recovery” section of the{" "}
            <Link href="/status" className="text-primary hover:underline">
              README
            </Link>{" "}
            for the full step-by-step.
          </p>
        </div>
      </div>

      {error ? (
        <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}

      <Button type="button" onClick={create} disabled={creating}>
        {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <HardDriveDownload className="h-4 w-4" />}
        Create Backup
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent backups</CardTitle>
        </CardHeader>
        <CardContent>
          {backups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No backups yet. Create one to get started.</p>
          ) : (
            <div className="space-y-2">
              {backups.map((b) => (
                <div
                  key={b.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-background/40 px-3 py-2 text-sm"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">{b.filename}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatSize(b.size_bytes)} · {new Date(b.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <a
                      href={api.backupDownloadUrl(b.id)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
                    >
                      <Download className="h-4 w-4" /> Download
                    </a>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => remove(b.id)}
                      disabled={busyId === b.id}
                    >
                      {busyId === b.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                      Delete
                    </Button>
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
