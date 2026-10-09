"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Download, Loader2, PenLine } from "lucide-react";

import { api } from "@/lib/api";
import type {
  CopyGeneration,
  CopyTone,
  CopyType,
  ProductAsset,
  ProductSceneGeneration,
  Project,
} from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CopyProviderBanner } from "@/components/copy-provider-banner";
import { BriefSelect } from "@/components/brief-select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { consumeHandoff } from "@/lib/stores/useMediaHandoff";
import { cn } from "@/lib/utils";
import { safeInterval } from "@/lib/safe-interval";

const COPY_TYPES: { value: CopyType; label: string }[] = [
  { value: "product_description", label: "Product description" },
  { value: "instagram_caption", label: "Instagram caption" },
  { value: "facebook_ad", label: "Facebook ad" },
  { value: "tiktok_hook", label: "TikTok hook" },
  { value: "seo_title", label: "SEO title" },
];

const TONES: CopyTone[] = ["luxury", "friendly", "bold", "professional", "playful"];

const STATUS_VARIANT = {
  queued: "muted",
  running: "default",
  completed: "success",
  failed: "destructive",
} as const;

const READY_ASSET_STATUSES = new Set(["uploaded", "completed"]);

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function CopyStudioView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<ProductAsset[]>([]);
  const [scenes, setScenes] = useState<ProductSceneGeneration[]>([]);
  const [copies, setCopies] = useState<CopyGeneration[]>([]);

  const [projectId, setProjectId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [copyType, setCopyType] = useState<CopyType>("product_description");
  const [tone, setTone] = useState<CopyTone>("professional");
  const [audience, setAudience] = useState("");
  const [briefId, setBriefId] = useState("");
  const [prompt, setPrompt] = useState("");

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transcriptNote, setTranscriptNote] = useState<string | null>(null);

  // "Send to Copy Studio" from a transcript: prefill the prompt with the
  // transcript text (carried in ephemeral handoff state, never in the URL).
  useEffect(() => {
    const pending = consumeHandoff();
    const text = pending?.media?.metadata.transcriptText;
    if (pending?.media?.type === "transcript" && text) {
      setPrompt(text);
      setTranscriptNote("Prefilled from your transcript. Edit the text or generate copy below.");
    }
  }, []);

  const projectAssets = useMemo(
    () =>
      assets.filter(
        (a) => a.project_id === projectId && READY_ASSET_STATUSES.has(a.status),
      ),
    [assets, projectId],
  );
  const projectScenes = useMemo(
    () =>
      scenes.filter((s) => s.project_id === projectId && s.status === "completed"),
    [scenes, projectId],
  );

  useEffect(() => {
    async function load() {
      try {
        const [projectList, assetList, sceneList, copyList] = await Promise.all([
          api.listProjects(),
          api.listAssets(undefined, "product_scenes"),
          api.listProductScenes(),
          api.listCopy(),
        ]);
        setProjects(projectList);
        setAssets(assetList);
        setScenes(sceneList);
        setCopies(copyList);
        setProjectId(assetList[0]?.project_id ?? projectList[0]?.id ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load Copy Studio");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Reset optional links when the selected project changes.
  useEffect(() => {
    setAssetId("");
    setSceneId("");
  }, [projectId]);

  // Poll any queued/running copies until they settle.
  useEffect(() => {
    const active = copies.filter(
      (c) => c.status === "queued" || c.status === "running",
    );
    if (active.length === 0) return;
    const poll = safeInterval(async () => {
      const updates = await Promise.all(active.map((c) => api.getCopy(c.id)));
      setCopies((current) =>
        current.map((c) => updates.find((u) => u.id === c.id) ?? c),
      );
    }, 2500);
    return poll;
  }, [copies]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!projectId || !prompt.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const copy = await api.createCopy({
        project_id: projectId,
        product_asset_id: assetId || null,
        product_scene_id: sceneId || null,
        copy_type: copyType,
        tone,
        audience: audience.trim() || null,
        prompt: prompt.trim(),
        brief_id: briefId || null,
      });
      setCopies((current) => [copy, ...current]);
      setPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Copy generation failed");
    } finally {
      setSubmitting(false);
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
    <>
      <CopyProviderBanner />
      {transcriptNote ? (
        <p className="mb-4 flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
          {transcriptNote}
        </p>
      ) : null}
      <div className="grid gap-8 lg:grid-cols-[380px_1fr]">
      <form
        onSubmit={handleSubmit}
        className="h-fit space-y-5 rounded-lg border border-border bg-card p-6"
      >
        <div className="space-y-2">
          <Label htmlFor="copy-project">Project</Label>
          <select
            id="copy-project"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className={selectClass}
          >
            {projects.length === 0 ? <option value="">No projects</option> : null}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="copy-asset">Product asset (optional)</Label>
            <select
              id="copy-asset"
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              className={selectClass}
            >
              <option value="">None</option>
              {projectAssets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.filename}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="copy-scene">Product scene (optional)</Label>
            <select
              id="copy-scene"
              value={sceneId}
              onChange={(e) => setSceneId(e.target.value)}
              className={selectClass}
            >
              <option value="">None</option>
              {projectScenes.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.prompt.slice(0, 40)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="copy-type">Copy type</Label>
          <select
            id="copy-type"
            value={copyType}
            onChange={(e) => setCopyType(e.target.value as CopyType)}
            className={selectClass}
          >
            {COPY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <Label>Tone</Label>
          <div className="grid grid-cols-3 gap-2">
            {TONES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTone(t)}
                className={cn(
                  "rounded-md border px-3 py-2 text-sm font-medium capitalize transition-colors",
                  tone === t
                    ? "border-primary bg-primary/15 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="copy-audience">Audience (optional)</Label>
          <Input
            id="copy-audience"
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            placeholder="e.g. busy parents, gen z shoppers"
          />
        </div>

        <BriefSelect
          projectId={projectId}
          value={briefId}
          onChange={setBriefId}
          id="copy-brief"
        />

        <div className="space-y-2">
          <Label htmlFor="copy-prompt">Prompt / context</Label>
          <Textarea
            id="copy-prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="What is the product? Any key details to highlight?"
            className="min-h-[110px]"
          />
        </div>

        {error ? (
          <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button
          type="submit"
          size="lg"
          disabled={!projectId || !prompt.trim() || submitting}
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Generating…
            </>
          ) : (
            <>
              <PenLine className="h-4 w-4" /> Generate copy
            </>
          )}
        </Button>
      </form>

      <div>
        <h3 className="mb-4 text-sm font-semibold">Copy history</h3>
        {copies.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            <PenLine className="h-7 w-7" />
            No copy generated yet.
          </div>
        ) : (
          <div className="space-y-3">
            {copies.map((copy) => (
              <CopyCard key={copy.id} copy={copy} />
            ))}
          </div>
        )}
      </div>
      </div>
    </>
  );
}

function CopyCard({ copy }: { copy: CopyGeneration }) {
  const [copied, setCopied] = useState(false);
  const typeLabel =
    COPY_TYPES.find((t) => t.value === copy.copy_type)?.label ?? copy.copy_type;

  async function handleCopy() {
    if (!copy.result_text) return;
    await navigator.clipboard.writeText(copy.result_text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{typeLabel}</span>
          <span className="text-muted-foreground capitalize">· {copy.tone}</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[copy.status]} className="capitalize">
            {copy.status}
          </Badge>
          {copy.status === "completed" && copy.result_text ? (
            <>
              <Button variant="ghost" size="sm" onClick={handleCopy}>
                {copied ? (
                  <>
                    <Check className="h-4 w-4" /> Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" /> Copy
                  </>
                )}
              </Button>
              <a
                href={api.exportCopyUrl(copy.id)}
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                <Download className="h-4 w-4" /> .txt
              </a>
            </>
          ) : null}
        </div>
      </div>

      <p className="mb-2 line-clamp-1 text-xs text-muted-foreground">
        {copy.prompt}
      </p>

      {copy.status === "completed" && copy.result_text ? (
        <pre className="whitespace-pre-wrap rounded-md bg-background/50 p-3 text-sm text-foreground/90">
          {copy.result_text}
        </pre>
      ) : copy.status === "failed" ? (
        <p className="text-sm text-destructive">{copy.error ?? "Generation failed"}</p>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {copy.status === "running" ? "Writing…" : "Queued…"}
        </p>
      )}
    </div>
  );
}
