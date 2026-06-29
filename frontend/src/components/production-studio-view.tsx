"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Check,
  Download,
  Film,
  ImageIcon,
  Loader2,
  Package,
  Plus,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  Production,
  Project,
  Shot,
  Storyboard,
  VideoGeneration,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function ProductionStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [productions, setProductions] = useState<Production[]>([]);
  const [storyboards, setStoryboards] = useState<Storyboard[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [videos, setVideos] = useState<VideoGeneration[]>([]);

  const [selectedProductionId, setSelectedProductionId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("planning");
  const [storyboardIds, setStoryboardIds] = useState<string[]>([]);
  const [shotIds, setShotIds] = useState<string[]>([]);
  const [videoIds, setVideoIds] = useState<string[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedProduction = useMemo(
    () =>
      productions.find((production) => production.id === selectedProductionId) ??
      null,
    [productions, selectedProductionId],
  );

  useEffect(() => {
    api
      .listProjects()
      .then((list) => {
        setProjects(list);
        setProjectId(list[0]?.id ?? "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load projects"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    loadProject(projectId);
  }, [projectId]);

  useEffect(() => {
    if (!selectedProduction) return;
    setTitle(selectedProduction.title);
    setDescription(selectedProduction.description ?? "");
    setStatus(selectedProduction.status);
    setStoryboardIds(selectedProduction.storyboard_ids);
    setShotIds(selectedProduction.shot_ids);
    setVideoIds(selectedProduction.video_ids);
  }, [selectedProduction]);

  async function loadProject(id: string) {
    setError(null);
    setNotice(null);
    try {
      const [productionList, storyboardList, videoList] = await Promise.all([
        api.listProductions(id),
        api.listStoryboards(id),
        api.listVideos(id),
      ]);
      const shotLists = await Promise.all(
        storyboardList.map((storyboard) => api.listShots(storyboard.id)),
      );
      setProductions(productionList);
      setStoryboards(storyboardList);
      setShots(shotLists.flat());
      setVideos(videoList);
      setSelectedProductionId(productionList[0]?.id ?? "");
      if (productionList.length === 0) resetForm();
    } catch (err) {
      setProductions([]);
      setStoryboards([]);
      setShots([]);
      setVideos([]);
      setError(err instanceof Error ? err.message : "Could not load production data");
    }
  }

  function resetForm() {
    setTitle("");
    setDescription("");
    setStatus("planning");
    setStoryboardIds([]);
    setShotIds([]);
    setVideoIds([]);
    setSelectedProductionId("");
  }

  function toggle(list: string[], value: string, setter: (next: string[]) => void) {
    setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  function linkedVideoIdsForShots(ids: string[]) {
    return shots
      .filter((shot) => ids.includes(shot.id) && shot.video_id)
      .map((shot) => shot.video_id as string);
  }

  function toggleShot(id: string) {
    const nextShotIds = shotIds.includes(id)
      ? shotIds.filter((item) => item !== id)
      : [...shotIds, id];
    setShotIds(nextShotIds);
    setVideoIds((current) =>
      Array.from(new Set([...current, ...linkedVideoIdsForShots(nextShotIds)])),
    );
  }

  async function createFromStoryboard(storyboard: Storyboard) {
    if (!projectId || saving) return;
    const boardShots = shots
      .filter((shot) => shot.storyboard_id === storyboard.id)
      .sort((a, b) => a.shot_number - b.shot_number);
    const linkedVideos = boardShots
      .filter((shot) => shot.video_id)
      .map((shot) => shot.video_id as string);
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const production = await api.createProduction(projectId, {
        title: `${storyboard.title} Production`,
        description: storyboard.description,
        status: "assembly",
        storyboard_ids: [storyboard.id],
        shot_ids: boardShots.map((shot) => shot.id),
        video_ids: linkedVideos,
      });
      setProductions((current) => [production, ...current]);
      setSelectedProductionId(production.id);
      setNotice("Production created from storyboard.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create production");
    } finally {
      setSaving(false);
    }
  }

  async function saveProduction() {
    if (!projectId || saving) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    const payload = {
      title: title.trim() || "Untitled production",
      description: description.trim() || null,
      status,
      storyboard_ids: storyboardIds,
      shot_ids: shotIds,
      video_ids: videoIds,
    };
    try {
      const saved = selectedProductionId
        ? await api.updateProduction(projectId, selectedProductionId, payload)
        : await api.createProduction(projectId, payload);
      setProductions((current) => {
        const exists = current.some((production) => production.id === saved.id);
        return exists
          ? current.map((production) =>
              production.id === saved.id ? saved : production,
            )
          : [saved, ...current];
      });
      setSelectedProductionId(saved.id);
      setNotice("Production saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save production");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProduction(id: string) {
    if (!projectId) return;
    setError(null);
    try {
      await api.deleteProduction(projectId, id);
      setProductions((current) =>
        current.filter((production) => production.id !== id),
      );
      if (selectedProductionId === id) resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete production");
    }
  }

  async function exportProduction() {
    if (!projectId || !selectedProductionId || exporting) return;
    setExporting(true);
    setError(null);
    setNotice(null);
    try {
      await api.downloadProductionPackage(projectId, selectedProductionId);
      await loadProject(projectId);
      setNotice("Production package downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export production");
    } finally {
      setExporting(false);
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
    <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
      <div className="space-y-5">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="space-y-2">
              <Label htmlFor="production-project">Project</Label>
              <select
                id="production-project"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                className={selectClass}
              >
                {projects.length === 0 ? <option value="">No projects</option> : null}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            {error ? (
              <div className="flex items-center gap-2 rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" /> {error}
              </div>
            ) : null}
            {notice ? (
              <div className="flex items-center gap-2 rounded-md bg-emerald-500/15 px-3 py-2 text-sm text-emerald-300">
                <Check className="h-4 w-4" /> {notice}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Productions</h2>
              <Button type="button" variant="outline" size="sm" onClick={resetForm}>
                New
              </Button>
            </div>
            {productions.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                No productions yet.
              </p>
            ) : (
              <div className="space-y-2">
                {productions.map((production) => (
                  <div
                    key={production.id}
                    className={cn(
                      "rounded-md border p-3",
                      selectedProductionId === production.id
                        ? "border-primary bg-primary/10"
                        : "border-border bg-background/40",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedProductionId(production.id)}
                      className="block w-full text-left"
                    >
                      <p className="truncate text-sm font-semibold">
                        {production.title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {production.status} · {production.video_ids.length} videos
                      </p>
                    </button>
                    <div className="mt-2 flex justify-between gap-2">
                      <Badge variant="outline">
                        {production.export_urls.length} exports
                      </Badge>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => deleteProduction(production.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="production-title">Title</Label>
                <Input
                  id="production-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Spring campaign film"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="production-status">Status</Label>
                <select
                  id="production-status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                  className={selectClass}
                >
                  <option value="planning">Planning</option>
                  <option value="assembly">Assembly</option>
                  <option value="review">Review</option>
                  <option value="exported">Exported</option>
                </select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="production-description">Description</Label>
              <Textarea
                id="production-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                placeholder="Production notes, target channels, edit direction"
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-4">
              <Stat label="Storyboards" value={storyboardIds.length} />
              <Stat label="Shots" value={shotIds.length} />
              <Stat label="Videos" value={videoIds.length} />
              <Stat
                label="Completed"
                value={videos.filter((video) => videoIds.includes(video.id) && video.status === "completed").length}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={saveProduction} disabled={!projectId || saving}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Saving
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" /> Save Production
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={exportProduction}
                disabled={!selectedProductionId || exporting}
              >
                {exporting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Exporting
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" /> Export Package
                  </>
                )}
              </Button>
              <Link
                href="/videos"
                className={cn(buttonVariants({ variant: "outline" }))}
              >
                <Film className="h-4 w-4" /> Generate Videos
              </Link>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-5 lg:grid-cols-3">
            <SelectionPanel
              title="Storyboards"
              empty="No storyboards yet."
              items={storyboards.map((storyboard) => ({
                id: storyboard.id,
                title: storyboard.title,
                meta: storyboard.status,
              }))}
              selectedIds={storyboardIds}
              onToggle={(id) => toggle(storyboardIds, id, setStoryboardIds)}
            />
          <SelectionPanel
            title="Shots"
            empty="No shots yet."
            items={shots.map((shot) => ({
              id: shot.id,
              title: `${shot.shot_number}. ${shot.description || "Untitled shot"}`,
              meta: `${shot.duration_seconds}s`,
            }))}
            selectedIds={shotIds}
            onToggle={toggleShot}
          />
          <SelectionPanel
            title="Generated Videos"
            empty="No videos yet."
            items={videos.map((video) => ({
              id: video.id,
              title: video.prompt,
              meta: `${video.mode} · ${video.status}`,
            }))}
            selectedIds={videoIds}
            onToggle={(id) => toggle(videoIds, id, setVideoIds)}
          />
        </div>

        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Storyboard handoff</h2>
              <Badge variant="outline">{storyboards.length}</Badge>
            </div>
            {storyboards.length === 0 ? (
              <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                Create a storyboard first.
              </p>
            ) : (
              <div className="grid gap-2 md:grid-cols-2">
                {storyboards.map((storyboard) => {
                  const boardShots = shots.filter(
                    (shot) => shot.storyboard_id === storyboard.id,
                  );
                  const linkedVideos = boardShots.filter((shot) => shot.video_id);
                  return (
                    <div key={storyboard.id} className="rounded-md border border-border bg-background/40 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium">{storyboard.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {boardShots.length} shots - {linkedVideos.length} linked videos
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => createFromStoryboard(storyboard)}
                          disabled={saving}
                        >
                          <Plus className="h-4 w-4" /> Create
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center gap-2">
              <Package className="h-5 w-5 text-primary" />
              <h2 className="text-sm font-semibold">Sequence assembly</h2>
            </div>
            <div className="space-y-2">
              {shotIds.length === 0 && videoIds.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Select shots and generated videos to assemble a sequence plan.
                </p>
              ) : (
                <SequenceList
                  selectedShotIds={shotIds}
                  selectedVideoIds={videoIds}
                  shots={shots}
                  videos={videos}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SelectionPanel({
  empty,
  items,
  onToggle,
  selectedIds,
  title,
}: {
  empty: string;
  items: { id: string; title: string; meta: string }[];
  onToggle: (id: string) => void;
  selectedIds: string[];
  title: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          <Badge variant="outline">{selectedIds.length}</Badge>
        </div>
        {items.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
            {empty}
          </p>
        ) : (
          <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
            {items.map((item) => {
              const selected = selectedIds.includes(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onToggle(item.id)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors",
                    selected
                      ? "border-primary bg-primary/10"
                      : "border-border hover:bg-muted",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border",
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border",
                    )}
                  >
                    {selected ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm font-medium">
                      {item.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {item.meta}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SequenceList({
  selectedShotIds,
  selectedVideoIds,
  shots,
  videos,
}: {
  selectedShotIds: string[];
  selectedVideoIds: string[];
  shots: Shot[];
  videos: VideoGeneration[];
}) {
  const selectedShots = shots
    .filter((shot) => selectedShotIds.includes(shot.id))
    .sort((a, b) => a.shot_number - b.shot_number);
  const linkedVideoIds = new Set(
    selectedShots.filter((shot) => shot.video_id).map((shot) => shot.video_id),
  );
  const extraVideos = videos.filter(
    (video) => selectedVideoIds.includes(video.id) && !linkedVideoIds.has(video.id),
  );

  return (
    <div className="space-y-3">
      {selectedShots.map((shot, index) => {
        const video = videos.find((item) => item.id === shot.video_id);
        const videoUrl = assetUrl(video?.result_url ?? null);
        return (
          <div
            key={shot.id}
            className="grid gap-3 rounded-md border border-border bg-background/40 p-3 md:grid-cols-[120px_minmax(0,1fr)]"
          >
            <div className="aspect-video overflow-hidden rounded border border-border bg-background/60">
              {videoUrl ? (
                <video src={videoUrl} className="h-full w-full object-cover" muted />
              ) : (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  <ImageIcon className="h-5 w-5" />
                </div>
              )}
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sequence {index + 1}</p>
              <p className="text-sm font-medium">
                Shot {shot.shot_number}: {shot.description || "Untitled shot"}
              </p>
              <p className="line-clamp-2 text-sm text-muted-foreground">
                {video?.prompt ?? shot.generation_prompt ?? "No linked video yet"}
              </p>
              {video ? (
                <Badge variant={video.status === "completed" ? "success" : "outline"} className="mt-2 capitalize">
                  {video.status}
                </Badge>
              ) : null}
            </div>
          </div>
        );
      })}
      {extraVideos.map((video, index) => (
        <div
          key={video.id}
          className="rounded-md border border-border bg-background/40 p-3"
        >
          <p className="text-xs text-muted-foreground">
            Extra clip {index + 1}
          </p>
          <p className="line-clamp-2 text-sm">{video.prompt}</p>
        </div>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3 text-center">
      <p className="text-xl font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
