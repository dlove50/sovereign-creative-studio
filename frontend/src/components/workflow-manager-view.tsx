"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  CircleSlash,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { api } from "@/lib/api";
import type {
  WorkflowCheck,
  WorkflowConfigUpdate,
  WorkflowManagerModels,
  WorkflowManagerStatus,
  WorkflowOption,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function WorkflowManagerView() {
  const [status, setStatus] = useState<WorkflowManagerStatus | null>(null);
  const [models, setModels] = useState<WorkflowManagerModels | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowCheck[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [s, m, w] = await Promise.all([
        api.getWorkflowManagerStatus(),
        api.getWorkflowManagerModels(),
        api.getWorkflowManagerWorkflows(),
      ]);
      setStatus(s);
      setModels(m);
      setWorkflows(w);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load workflow manager");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function apply(field: keyof WorkflowConfigUpdate, value: string) {
    setSaving(`${field}:${value}`);
    setWarnings([]);
    setError(null);
    try {
      const result = await api.updateWorkflowConfig({ [field]: value });
      setStatus(result.status);
      setWarnings(result.warnings);
      // Refresh model availability/active flags.
      setModels(await api.getWorkflowManagerModels());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(null);
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (error && !status) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Badge variant={status?.comfyui_reachable ? "success" : "destructive"}>
            ComfyUI {status?.comfyui_reachable ? "online" : "offline"}
          </Badge>
          <span className="font-mono text-xs">{status?.comfyui_base_url}</span>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={load}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {warnings.length > 0 ? (
        <div className="space-y-1 rounded-md border border-border bg-destructive/10 p-3">
          {warnings.map((w) => (
            <p key={w} className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" /> {w}
            </p>
          ))}
        </div>
      ) : null}

      {error && status ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : null}

      {models ? (
        <>
          <OptionSection
            title="Product Scene Models"
            description="Model family used for product-scene generation, such as Flux Kontext, Qwen Image, HiDream, or the legacy SD checkpoints."
            options={models.image_models}
            saving={saving}
            onSelect={(id) => apply("image_model", id)}
            field="image_model"
          />
          <OptionSection
            title="Product Scene Modes"
            description="Generation strategy for Product Scenes, such as img2img, inpaint, segmented composite, fashion editorial, or creative edit."
            options={models.scene_modes}
            saving={saving}
            onSelect={(id) => apply("scene_mode", id)}
            field="scene_mode"
          />
          <OptionSection
            title="Video Backend"
            description="Mock is the safe preview backend. Real ComfyUI/LTX video can be selected when the local video workflow is ready."
            options={models.video_models}
            saving={saving}
            onSelect={(id) => apply("video_backend", id)}
            field="video_backend"
          />
          <OptionSection
            title="Copy Provider"
            description="Text generation provider for copy, including mock, OpenAI, Claude, Gemini, Ollama, Qwen, or DeepSeek."
            options={models.copy_models}
            saving={saving}
            onSelect={(id) => apply("copy_backend", id)}
            field="copy_backend"
          />
        </>
      ) : null}

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Workflow Presets</h3>
          <p className="text-sm text-muted-foreground">
            Detected ComfyUI workflow files.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {workflows.map((workflow) => (
            <div
              key={`${workflow.name}-${workflow.path}`}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{workflow.name}</span>
                <Badge variant={workflow.exists ? "success" : "destructive"}>
                  {workflow.exists ? "available" : "missing"}
                </Badge>
              </div>
              <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                <Badge variant="muted">{workflow.kind}</Badge>
                {workflow.active ? <Badge>active</Badge> : null}
                {workflow.experimental ? (
                  <Badge variant="muted">experimental</Badge>
                ) : null}
              </div>
              <p className="mt-2 truncate font-mono text-xs text-muted-foreground">
                {workflow.path}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function OptionSection({
  description,
  field,
  onSelect,
  options,
  saving,
  title,
}: {
  description: string;
  field: string;
  onSelect: (id: string) => void;
  options: WorkflowOption[];
  saving: string | null;
  title: string;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {options.map((option) => {
          const isSaving = saving === `${field}:${option.id}`;
          const disabled = !option.available || option.active || isSaving;
          return (
            <button
              key={option.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(option.id)}
              className={cn(
                "rounded-lg border p-4 text-left transition-colors",
                option.active
                  ? "border-primary bg-primary/15"
                  : option.available
                    ? "border-border bg-card hover:border-primary/50"
                    : "border-border bg-card opacity-60",
              )}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{option.name}</span>
                {isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : option.active ? (
                  <Check className="h-4 w-4 text-primary" />
                ) : !option.available ? (
                  <CircleSlash className="h-4 w-4 text-muted-foreground" />
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant={option.available ? "success" : "muted"}>
                  {option.active
                    ? "active"
                    : option.available
                      ? "available"
                      : "unavailable"}
                </Badge>
                {option.experimental ? (
                  <Badge variant="muted">experimental</Badge>
                ) : null}
                {option.backend ? (
                  <Badge variant="muted">{option.backend}</Badge>
                ) : null}
              </div>
              {option.note ? (
                <p className="mt-2 text-xs text-muted-foreground">{option.note}</p>
              ) : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
