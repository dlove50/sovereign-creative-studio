"use client";
import { EmptyState } from "@/components/ui/empty-state";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDownWideNarrow, Download, Filter, Folder, FolderPlus, Loader2, Search, Trash2, Video, X } from "lucide-react";

import { CompletedVideoEditing } from "@/components/media/completed-video-editing";
import { MediaImportControl } from "@/components/media/media-import-control";
import { api, assetUrl } from "@/lib/api";
import { useStaggerIn } from "@/components/motion/use-motion";
import { SkeletonGrid } from "@/components/ui/skeleton";
import type { AvatarJob, Movie, Project, VideoGeneration } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";

type Kind = "avatar" | "clip" | "movie" | "cinematic";
type Item = { id: string; kind: Kind; title: string; url: string | null; status: string; createdAt: string };
type Sort = "newest" | "oldest" | "name";
const KIND_LABEL: Record<Kind, string> = { cinematic: "Cinematic video", avatar: "Avatar video", clip: "Video clip", movie: "Scene-by-scene video" };

function timeAgo(iso: string) {
  const ms = Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime();
  const minutes = Math.max(1, Math.round(ms / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function fmtDuration(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m ? `${m}m ${r}s` : `${r}s`;
}

function VideoCard({ item, onOpen }: { item: Item; onOpen: () => void }) {
  const [duration, setDuration] = useState<number | null>(null);
  const src = item.url ? assetUrl(item.url) : null;
  const inProgress = item.status === "queued" || item.status === "running" || item.status === "rendering";
  return (
    <button type="button" onClick={onOpen} disabled={!src && item.kind !== "movie"} className="group block w-full text-left focus-visible:outline-none">
      <div className="relative aspect-video overflow-hidden rounded-2xl border border-border bg-raised transition-colors group-hover:border-primary/60 group-focus-visible:ring-2 group-focus-visible:ring-ring">
        {src ? (
          // #t=0.5 makes the browser paint a frame as the thumbnail.
          <video src={`${src}#t=0.5`} muted preload="metadata" onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)} className="h-full w-full object-cover object-[50%_28%]" />
        ) : (
          <span className="flex h-full flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            {inProgress ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : <Video className="h-5 w-5" />}
            {inProgress ? "Rendering…" : item.status === "failed" ? "Failed" : item.status === "draft" ? "Continue editing" : "No file"}
          </span>
        )}
        {duration ? (
          <span className="absolute bottom-2 right-2 flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] text-white">
            <Video className="h-3 w-3" /> {fmtDuration(duration)}
          </span>
        ) : null}
        {item.status === "draft" ? <span className="absolute left-2 top-2 rounded-md bg-black/70 px-2 py-1 text-xs text-white">Draft</span> : null}
        {inProgress ? <span className="absolute left-2 top-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] text-white">In progress</span> : null}
      </div>
      <p className="mt-2 truncate text-sm font-semibold">{item.title}</p>
      <p className="text-xs text-muted-foreground">{timeAgo(item.createdAt)} · {KIND_LABEL[item.kind]}</p>
    </button>
  );
}

export function ProjectsLibraryView() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [items, setItems] = useState<Item[] | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("newest");
  const [kind, setKind] = useState<"all" | Kind>("all");
  const [naming, setNaming] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [open, setOpen] = useState<Item | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshItems = useCallback(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
    Promise.all([api.listAvatarJobs().catch(() => [] as AvatarJob[]), api.listVideos().catch(() => [] as VideoGeneration[]), api.listMovies().catch(() => { setError("Scene-by-scene videos could not be loaded. Reload to try again."); return [] as Movie[]; }), api.listCinematicOutputs().catch(() => { setError("Cinematic videos could not be loaded. Reload to try again."); return []; })]).then(([jobs, clips, movies, cinematic]) => {
      setItems([
        ...cinematic.map((v): Item => ({ id: `c-${v.id}`, kind: "cinematic", title: `${v.title} - Revision ${v.revision}`, url: v.result_url, status: v.status, createdAt: v.created_at })),
        ...movies.map((m): Item => ({ id: `m-${m.id}`, kind: "movie", title: m.title, url: m.output_video_path, status: m.status, createdAt: m.updated_at })),
        ...jobs.filter((j) => j.status !== "setup_required").map((j): Item => ({
          id: `a-${j.id}`, kind: "avatar", title: j.script_text?.trim() || "Talking avatar", url: j.output_video_path, status: j.status, createdAt: j.created_at,
        })),
        ...clips.map((v): Item => ({
          id: `v-${v.id}`, kind: "clip", title: v.prompt?.trim() || "Video clip", url: v.result_url, status: v.status, createdAt: v.created_at,
        })),
      ]);
    });
  }, []);

  useEffect(refreshItems, [refreshItems]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(null); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const q = query.trim().toLowerCase();
  const folders = projects.filter((p) => !q || p.name.toLowerCase().includes(q));
  const videos = useMemo(() => {
    const list = (items ?? []).filter((i) => (kind === "all" || i.kind === kind) && (!q || i.title.toLowerCase().includes(q)));
    return list.sort((a, b) =>
      sort === "name" ? a.title.localeCompare(b.title) : (sort === "newest" ? -1 : 1) * a.createdAt.localeCompare(b.createdAt),
    );
  }, [items, kind, q, sort]);

  const grid = useRef<HTMLUListElement>(null);
  useStaggerIn(grid, videos.length);

  async function trashItem(item: Item) {
    if (item.kind === "cinematic") return;
    const label = item.title.slice(0, 60);
    const ok = item.kind === "movie"
      ? await confirmDialog(`Delete “${label}”? Its scenes are removed with it.`)
      : await confirmDialog(`Move “${label}” to the trash? An admin can restore it.`);
    if (!ok) return;
    const [prefix, rawId] = [item.id.slice(0, 2), item.id.slice(2)];
    try {
      if (item.kind === "movie") await api.deleteMovie(rawId);
      else if (prefix === "a-") await api.trashAvatarJob(rawId);
      else await api.trashVideo(rawId);
      setItems((all) => (all ?? []).filter((i) => i.id !== item.id));
      setOpen((current) => (current?.id === item.id ? null : current));
    } catch (e) {
      setError(e instanceof Error ? e.message : "It could not be deleted.");
    }
  }

  async function trashOpen() {
    if (open) await trashItem(open);
  }

  async function createFolder() {
    if (!folderName.trim()) return;
    setError(null);
    try {
      const p = await api.createProject(folderName.trim());
      setProjects((all) => [p, ...all]);
      setFolderName("");
      setNaming(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The folder could not be created.");
    }
  }

  return (
    <div className="mx-auto max-w-[1120px]">
      <PageHeader title="Projects" description="Organize finished videos, active renders, and reusable production folders." />
      <div className="mb-4"><MediaImportControl kind="video" onImported={refreshItems} /></div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex min-h-11 min-w-[220px] flex-1 items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-2 focus-within:ring-2 focus-within:ring-ring">
          <Search className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search videos and folders" aria-label="Search videos and folders" className="w-full bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none" />
        </label>
        <label className="flex min-h-11 items-center gap-1.5 rounded-xl border border-border bg-card/60 px-3 py-2 text-sm">
          <ArrowDownWideNarrow className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort" className="bg-transparent focus:outline-none">
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="name">Name</option>
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-1.5 rounded-xl border border-border bg-card/60 px-3 py-2 text-sm">
          <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <select value={kind} onChange={(e) => setKind(e.target.value as "all" | Kind)} aria-label="Filter" className="bg-transparent focus:outline-none">
            <option value="all">All videos</option>
            <option value="avatar">Avatar videos</option>
            <option value="movie">Scene-by-scene videos</option>
            <option value="clip">Video clips</option>
            <option value="cinematic">Cinematic videos</option>
          </select>
        </label>
      </div>

      <div className="mt-8 flex items-center gap-2">
        <h2 className="text-base font-semibold">Folders</h2>
        <button type="button" onClick={() => setNaming((v) => !v)} aria-label="New folder" className="flex h-11 w-11 items-center justify-center rounded-full border border-border hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <FolderPlus className="h-3.5 w-3.5" />
        </button>
      </div>
      {naming ? (
        <div className="mt-3 flex max-w-md gap-2">
          <input
            autoFocus
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createFolder()}
            placeholder="Folder name"
            aria-label="Folder name"
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-input bg-subdued px-4 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button type="button" onClick={createFolder} disabled={!folderName.trim()} className="min-h-11 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">Create folder</button>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {folders.length ? (
        <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {folders.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`} className="flex items-center gap-2.5 rounded-xl border border-border bg-card/50 px-3 py-2.5 text-sm hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Folder className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                <span className="truncate">{p.name}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">{q ? "No folders match." : "No folders yet. Use the + button to make one."}</p>
      )}

      <h2 className="mb-4 mt-10 text-base font-semibold">Videos</h2>
      {items === null ? (
        <SkeletonGrid count={6} aspect="aspect-video" className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 md:grid-cols-3" />
      ) : videos.length === 0 ? (
        q || kind !== "all" ? <EmptyState icon={Video} title="No videos match." body="Try another word or clear the filter." /> : <EmptyState icon={Video} title="No videos yet" body="Finished avatar videos, movies and clips collect here." action={{ label: "Make your first video", href: "/video-agent" }} />
      ) : (
        <ul ref={grid} className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 md:grid-cols-3">
          {videos.map((item) => (
            <li key={item.id} className="group relative">
              <VideoCard item={item} onOpen={() => item.kind === "movie" ? router.push(`/movies/${item.id.slice(2)}`) : setOpen(item)} />
              {item.kind !== "cinematic" && !(item.status === "queued" || item.status === "running" || item.status === "rendering") ? (
                <button type="button" onClick={() => trashItem(item)} aria-label={`Delete ${item.title.slice(0, 60)}`} className="absolute right-2 top-2 rounded-full bg-black/70 p-1.5 text-white opacity-0 transition hover:bg-destructive focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
                  <Trash2 className="h-4 w-4" />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {open?.url ? createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" role="dialog" aria-modal="true" aria-label={open.title} onClick={() => setOpen(null)}>
          <div className="max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-3xl border border-border bg-card" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
              <p className="truncate font-semibold">{open.title}</p>
              <button type="button" onClick={() => setOpen(null)} aria-label="Close" className="rounded-full p-1 text-muted-foreground hover:bg-raised"><X className="h-4 w-4" /></button>
            </div>
            <video key={open.id} controls autoPlay playsInline src={assetUrl(open.url) ?? undefined} className="max-h-[60vh] w-full bg-black" />
            <div className="px-5 py-3"><CompletedVideoEditing id={open.id} url={open.url} title={open.title} origin="Projects" /></div>
            <div className="flex justify-between gap-3 px-5 py-3">
              <button hidden={open.kind === "cinematic"} type="button" onClick={trashOpen} className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm text-destructive hover:bg-raised">
                <Trash2 className="h-4 w-4" /> Move to trash
              </button>
              <a href={assetUrl(open.url) ?? "#"} download className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
                <Download className="h-4 w-4" /> Download
              </a>
            </div>
          </div>
        </div>, document.body
      ) : null}
    </div>
  );
}
