"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, KeyRound, Loader2, Plug, Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import type { IntegrationProvider } from "@/lib/types";
import { cn } from "@/lib/utils";
import { IntegrationDirectory } from "./integration-directory";

const LOCAL_DEFAULTS = [
  { name: "Local ComfyUI / Flux", kind: "Images & product scenes", detail: "Default local/private image engine." },
  { name: "Local LTX", kind: "Video", detail: "Default local/private video provider; ready modes depend on workflow validation." },
  { name: "Local Qwen", kind: "Copy", detail: "Default local/private copy provider." },
];

const CONFIG_FIELDS: Record<string, [string, string][]> = {
  elevenlabs: [
    ["tts_model", "Text-to-speech model"],
    ["sts_model", "Voice changer model"],
    ["transcription_model", "Transcription model"],
  ],
  seedance: [
    ["base_url", "Base URL"],
    ["model_id", "Model ID"],
    ["create_endpoint", "Task creation endpoint"],
    ["status_endpoint", "Polling/status endpoint"],
  ],
  openai: [
    ["base_url", "Base URL"],
    ["image_model", "Image model"],
    ["image_size", "Image size"],
    ["image_quality", "Image quality"],
    ["organization", "Organization (optional)"],
    ["project", "Project (optional)"],
  ],
};

export function AdminIntegrationsView() {
  const [providers, setProviders] = useState<IntegrationProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [configDrafts, setConfigDrafts] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    setProviders(await api.listIntegrations());
  }

  useEffect(() => {
    api
      .listIntegrations()
      .then(setProviders)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load integrations"))
      .finally(() => setLoading(false));
  }, []);

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
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
      <div className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
        <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-400" />
        <div>
          <p className="font-semibold text-amber-300">
            Local models stay the default. These are optional premium providers.
          </p>
          <p className="text-muted-foreground">
            External API usage may cost money. API keys are stored on this machine only,
            never shown in full, and excluded from backups.
          </p>
        </div>
      </div>

      {error ? (
        <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Local defaults (always on)
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {LOCAL_DEFAULTS.map((d) => (
            <div key={d.name} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">{d.name}</p>
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
                  Local default
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{d.kind} · {d.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Optional premium providers
        </h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {providers.map((p) => (
            <div key={p.id} className="space-y-3 rounded-xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <Plug className="h-4 w-4 text-primary" />
                    <p className="font-semibold">{p.name}</p>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{p.note}</p>
                </div>
                <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                  Premium provider
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 font-medium",
                    p.configured
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {p.configured ? `Key: ${p.masked_key}` : "Not configured"}
                </span>
                <span className="text-muted-foreground">
                  {p.enabled ? "Enabled" : p.configured ? "Disabled (admin setup required to enable)" : "Admin setup required"}
                </span>
              </div>

              <div className="flex gap-2">
                <input
                  type="password"
                  placeholder="Paste API key"
                  value={drafts[p.id] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [p.id]: e.target.value }))}
                  className="flex h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <button
                  type="button"
                  disabled={busy === p.id || !(drafts[p.id] || "").trim()}
                  onClick={() =>
                    run(p.id, async () => {
                      await api.setIntegrationKey(p.id, (drafts[p.id] || "").trim());
                      setDrafts((d) => ({ ...d, [p.id]: "" }));
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
                >
                  <KeyRound className="h-4 w-4" /> Save
                </button>
              </div>

              {CONFIG_FIELDS[p.id] ? (
                <div className="grid gap-2 rounded-lg border border-border/70 bg-background/40 p-3">
                  {CONFIG_FIELDS[p.id].map(([key, label]) => (
                    <label key={key} className="grid gap-1 text-xs">
                      <span className="font-medium text-muted-foreground">{label}</span>
                      <input
                        value={configDrafts[p.id]?.[key] ?? p.config?.[key] ?? ""}
                        onChange={(e) =>
                          setConfigDrafts((cur) => ({
                            ...cur,
                            [p.id]: { ...(cur[p.id] ?? {}), [key]: e.target.value },
                          }))
                        }
                        placeholder={p.config?.[key] ?? ""}
                        className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      />
                    </label>
                  ))}
                  <button
                    type="button"
                    disabled={busy === p.id}
                    onClick={() =>
                      run(p.id, async () => {
                        await api.setIntegrationConfig(p.id, configDrafts[p.id] ?? {});
                        setConfigDrafts((cur) => ({ ...cur, [p.id]: {} }));
                      })
                    }
                    className="w-fit rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                  >
                    Save provider config
                  </button>
                </div>
              ) : null}

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy === p.id || !p.configured}
                  onClick={() => run(p.id, () => api.setIntegrationEnabled(p.id, !p.enabled))}
                  className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                >
                  {p.enabled ? "Disable" : "Enable"}
                </button>
                <button
                  type="button"
                  disabled={busy === p.id}
                  onClick={() => run(p.id, () => api.testIntegration(p.id))}
                  className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
                >
                  <Check className="h-4 w-4" /> Test connection
                </button>
                <button
                  type="button"
                  disabled={busy === p.id || !p.configured}
                  onClick={() => run(p.id, () => api.deleteIntegrationKey(p.id))}
                  className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm text-destructive hover:bg-muted disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" /> Delete key
                </button>
              </div>

              <p className="text-xs text-muted-foreground">
                Last test: {p.last_test_result ?? "—"}
              </p>
            </div>
          ))}
        </div>
      </section>
      <IntegrationDirectory />
    </div>
  );
}
