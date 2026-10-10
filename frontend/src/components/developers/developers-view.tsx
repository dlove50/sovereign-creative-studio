"use client";
import { SkeletonGrid } from "@/components/ui/skeleton";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { api } from "@/lib/api";
import { API_BASE } from "@/lib/api/core";

type Endpoint = Awaited<ReturnType<typeof api.developerEndpoints>>["endpoints"][number];

const METHOD_STYLE: Record<string, string> = {
  GET: "bg-sky-500/15 text-sky-300",
  POST: "bg-emerald-500/15 text-emerald-300",
  PUT: "bg-amber-500/15 text-amber-300",
  PATCH: "bg-amber-500/15 text-amber-300",
  DELETE: "bg-rose-500/15 text-rose-300",
};

// A copy-and-paste curl command for one endpoint, against this studio's own backend address.
function curlFor(endpoint: Endpoint, origin: string) {
  const path = endpoint.path.replace(/\{([^}]+)\}/g, (_, name: string) => `<${name}>`);
  const base = `curl${endpoint.method === "GET" ? "" : ` -X ${endpoint.method}`} "${origin}${path}${endpoint.query_params.length ? `?${endpoint.query_params.map((q) => `${q}=<${q}>`).join("&")}` : ""}"`;
  if (endpoint.body === "json") return `${base} -H "Content-Type: application/json" -d '{ ... }'`;
  if (endpoint.body === "multipart") return `${base} -F "file=@<your-file>"`;
  return base;
}

export function DevelopersView() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.developerEndpoints>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  // Addresses depend on the browser's location, so they are set after the page loads (not during server rendering).
  const [origin, setOrigin] = useState(API_BASE);
  // The interactive docs and OpenAPI file are served by the backend itself (port 8002), not by the web app.
  const [backend, setBackend] = useState("");

  useEffect(() => {
    if (!API_BASE) setOrigin(window.location.origin);
    setBackend(`${window.location.protocol}//${window.location.hostname}:8002`);
    api.developerEndpoints().then(setData).catch((e) => setError(e instanceof Error ? e.message : "The endpoint list could not be loaded."));
  }, []);

  const groups = useMemo(() => Array.from(new Set((data?.endpoints ?? []).map((e) => e.group))).sort(), [data]);
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.endpoints ?? []).filter((e) => (!group || e.group === group)
      && (!needle || `${e.method} ${e.path} ${e.summary} ${e.description}`.toLowerCase().includes(needle)));
  }, [data, query, group]);

  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="pt-4 text-center text-4xl font-extrabold tracking-[-0.03em]">Developer API</h1>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm text-muted-foreground">
        Everything the studio does is available through its local API. This list is read from the running backend, so it is always current.
        You can also try requests in the <a className="text-primary underline" href={`${backend}/docs`}>interactive docs</a> or download the <a className="text-primary underline" href={`${backend}/openapi.json`}>OpenAPI file</a>.
      </p>
      <p className="mx-auto mt-2 max-w-xl text-center text-xs text-muted-foreground">
        The API is on this computer only. Without a login it acts as the studio owner; with a login it uses that account. File uploads are multipart form posts.
      </p>

      {error ? <p role="alert" className="mt-6 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {!data && !error ? <SkeletonGrid count={3} className="grid grid-cols-1 gap-4 py-8 sm:grid-cols-3" /> : null}

      {data ? (
        <>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <label className="relative min-w-[220px] flex-1">
              <span className="sr-only">Search endpoints</span>
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by path or description" className="h-10 w-full rounded-xl border border-input bg-background pl-9 pr-3 text-sm" />
            </label>
            <label>
              <span className="sr-only">Group</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)} className="h-10 rounded-xl border border-input bg-background px-3 text-sm">
                <option value="">All groups ({data.count})</option>
                {groups.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
          </div>
          <p className="mt-3 text-xs text-muted-foreground" aria-live="polite">{shown.length} of {data.count} endpoints</p>
          <ul className="mt-2 space-y-1.5" aria-label="API endpoints">
            {shown.map((e) => {
              const id = `${e.method} ${e.path}`;
              return (
                <li key={id} className="rounded-xl border border-border bg-card/50">
                  <button type="button" aria-expanded={open === id} onClick={() => setOpen(open === id ? null : id)} className="flex w-full flex-wrap items-center gap-3 px-3 py-2 text-left">
                    <span className={`w-16 shrink-0 rounded-md px-2 py-0.5 text-center text-xs font-semibold ${METHOD_STYLE[e.method] ?? ""}`}>{e.method}</span>
                    <code className="min-w-0 flex-1 break-all text-sm">{e.path}</code>
                    <span className="text-xs text-muted-foreground">{e.group}</span>
                  </button>
                  {open === id ? (
                    <div className="space-y-2 border-t border-border px-3 py-3 text-sm">
                      {e.summary || e.description ? <p className="text-muted-foreground">{e.description || e.summary}</p> : null}
                      <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-[120px_1fr]">
                        {e.path_params.length ? <><dt>Path values</dt><dd>{e.path_params.join(", ")}</dd></> : null}
                        {e.query_params.length ? <><dt>Query values</dt><dd>{e.query_params.join(", ")}</dd></> : null}
                        <dt>Request body</dt><dd>{e.body === "json" ? "JSON" : e.body === "multipart" ? "File upload (multipart form)" : "None"}</dd>
                      </dl>
                      <pre className="overflow-x-auto rounded-lg bg-background p-3 text-xs"><code>{curlFor(e, origin)}</code></pre>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}
