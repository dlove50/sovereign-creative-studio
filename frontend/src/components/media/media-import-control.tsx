"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Loader2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { musicApi } from "@/lib/api/music";
import type { Project } from "@/lib/types";
import { Button } from "@/components/ui/button";

export function MediaImportControl({ kind, projectId, onImported }: {
  kind: "music" | "video";
  projectId?: string;
  onImported: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [destination, setDestination] = useState(projectId ?? "");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!projectId);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (projectId) { setDestination(projectId); return; }
    api.listProjects().then(setProjects).catch((e) => setError(e instanceof Error ? e.message : "Projects could not be loaded.")).finally(() => setLoading(false));
  }, [projectId]);

  async function importFiles(files: File[]) {
    if (!files.length || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    let added = 0;
    const errors: string[] = [];
    // One request per file keeps a large batch within the upload limit.
    for (const file of files) {
      try {
        const result = kind === "music"
          ? await musicApi.importSongs([file], destination || undefined)
          : await api.importVideos([file], destination);
        added += "songs" in result ? result.songs.length : result.videos.length;
        errors.push(...result.errors.map((e) => `${e.filename}: ${e.error}`));
      } catch (e) {
        errors.push(`${file.name}: ${e instanceof Error ? e.message : "Import failed."}`);
      }
    }
    setBusy(false);
    if (input.current) input.current.value = "";
    setMessage(added ? `Imported ${added} file${added === 1 ? "" : "s"}${destination ? " into the project" : " into Music Library"}.` : "");
    setError(errors.join(" "));
    if (added) onImported();
  }

  return (
    <div className="min-w-0 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {!projectId ? (
          <select aria-label={`${kind === "music" ? "Music" : "Video"} import destination`} value={destination} onChange={(e) => setDestination(e.target.value)} disabled={busy || loading}
            className="h-11 w-full max-w-64 rounded-md border border-input bg-background px-3 text-sm sm:w-56">
            <option value="">{loading ? "Loading projects..." : kind === "music" ? "Music Library (no project)" : "Choose destination project"}</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        ) : null}
        <input ref={input} type="file" multiple className="hidden" aria-label={`Import ${kind} files`}
          accept={kind === "music" ? ".mp3,.wav,.m4a,.flac,.ogg,.aac,.opus,.wma,audio/*" : ".mp4,.mov,.webm,.mkv,.avi,.m4v,video/*"}
          onChange={(e) => void importFiles(Array.from(e.target.files ?? []))} />
        <Button type="button" onClick={() => input.current?.click()} disabled={busy || loading || (kind === "video" && !destination)}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
          {busy ? "Importing..." : `Import ${kind}`}
        </Button>
        {!projectId && !loading && !projects.length ? <Link href="/projects" className="text-sm text-primary underline">Create a project</Link> : null}
      </div>
      {message ? <p role="status" className="max-w-prose text-sm text-primary">{message}</p> : null}
      {error ? <p role="alert" className="max-w-prose break-words text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
