"use client";

import { useEffect, useState } from "react";
import {
  Boxes,
  CheckCircle2,
  ClipboardList,
  Film,
  ImageIcon,
  Loader2,
  RefreshCw,
  Settings2,
  Type,
  Workflow,
  XCircle,
} from "lucide-react";

import { api } from "@/lib/api";
import type { ModelCheck, ModelManagerStatus, WorkflowCheck } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const CONFIG_COPY: Record<string, { label: string; description: string }> = {
  generator_backend: {
    label: "Base text-to-image backend",
    description: "Backend used by the generic Create page.",
  },
  image_model: {
    label: "Base text-to-image checkpoint",
    description: "Checkpoint from the generic text-to-image workflow.",
  },
  product_scene_backend: {
    label: "Product scene backend",
    description: "Backend used for Product Scenes and Film keyframes.",
  },
  product_scene_model: {
    label: "Product scene model",
    description: "Flux, Qwen, HiDream, or legacy scene model family.",
  },
  video_backend: {
    label: "Video backend",
    description: "ComfyUI/LTX generation (default). Mock fallback available.",
  },
  comfyui_video_engine: {
    label: "ComfyUI video engine",
    description: "LTX (default) or Wan engine.",
  },
  copy_backend: {
    label: "Copy provider",
    description: "Local Qwen (default). OpenAI, Claude, Gemini, Ollama, DeepSeek, or mock fallback.",
  },
  comfyui_base_url: {
    label: "ComfyUI URL",
    description: "Local ComfyUI API endpoint.",
  },
  comfyui_video_model_name: {
    label: "LTX video model file",
    description: "Model file used when LTX video mode is active.",
  },
  comfyui_wan_video_model_name: {
    label: "Wan video model file",
    description: "Model file used when Wan video mode is active.",
  },
};

export function ModelManagerView() {
  const [status, setStatus] = useState<ModelManagerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  function loadModels() {
    setRefreshing(true);
    setError(null);
    api
      .getModelStatus()
      .then(setStatus)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Unable to load models"),
      )
      .finally(() => setRefreshing(false));
  }

  useEffect(() => {
    loadModels();
  }, []);

  if (error) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <XCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!status) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Checking model status...</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={loadModels}
          disabled={refreshing}
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Settings2 className="h-4 w-4" />
                Current Active Configuration
              </CardTitle>
              <CardDescription>{status.comfyui.base_url}</CardDescription>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <StatusBadge
                label={status.comfyui.reachable ? "ComfyUI" : "Missing"}
                ok={status.comfyui.reachable}
              />
              {status.comfyui.version ? (
                <Badge variant="outline">v{status.comfyui.version}</Badge>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-md border border-border bg-background/40 p-3">
              <p className="text-xs text-muted-foreground">
                video generation ready
              </p>
              <p className="mt-1 truncate font-mono text-xs">
                {status.video_generation_ready}
              </p>
            </div>
            {Object.entries(status.current_config).map(([key, value]) => (
              <div
                key={key}
                className="rounded-md border border-border bg-background/40 p-3"
              >
                <p className="text-xs text-muted-foreground">{labelFor(key)}</p>
                <p className="mt-1 truncate font-mono text-xs">{value}</p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted-foreground">
                  {descriptionFor(key)}
                </p>
              </div>
            ))}
          </div>
          {!status.comfyui.reachable && status.comfyui.error ? (
            <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-3">
              <p className="text-sm font-medium text-destructive">
                ComfyUI offline
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Expected URL:{" "}
                <span className="font-mono">{status.comfyui.base_url}</span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Start with{" "}
                <span className="font-mono">
                  Start-Sovereign-Creative-Studio.bat
                </span>
                , then press Refresh.
              </p>
              <p className="mt-2 break-words text-xs text-destructive">
                {status.comfyui.error}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Section
        title="Product Scene / Image Models"
        description="Model families and checkpoints available for product-scene generation. The base text-to-image checkpoint is shown separately above."
        icon={ImageIcon}
        items={status.image_models}
      />
      <Section
        title="Video Models"
        description="Real ComfyUI/LTX video models. Default video backend is ComfyUI/LTX; mock fallback is available."
        icon={Film}
        items={status.video_models}
      />
      <Section
        title="Copy Providers"
        description="Provider availability for generated copy. Default is local Qwen; mock is the built-in fallback."
        icon={Type}
        items={status.copy_models}
      />
      <Section
        title="Support Models"
        description="Auxiliary models and nodes used for segmentation, encoders, VAE, and identity preservation."
        icon={Boxes}
        items={status.support_models}
      />
      <WorkflowSection workflows={status.workflows} />
    </div>
  );
}

function Section({
  title,
  description,
  icon: Icon,
  items,
}: {
  title: string;
  description: string;
  icon: typeof ImageIcon;
  items: ModelCheck[];
}) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-primary" />
          {title}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <ModelCard key={`${item.category}-${item.name}`} item={item} />
        ))}
      </div>
    </section>
  );
}

function labelFor(key: string) {
  return CONFIG_COPY[key]?.label ?? key.replaceAll("_", " ");
}

function descriptionFor(key: string) {
  return CONFIG_COPY[key]?.description ?? "Runtime configuration value.";
}

function ModelCard({ item }: { item: ModelCheck }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-sm">{item.name}</CardTitle>
            <CardDescription className="truncate">{item.source}</CardDescription>
          </div>
          {item.installed ? (
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
          ) : (
            <XCircle className="h-5 w-5 shrink-0 text-destructive" />
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={item.installed ? "Installed" : "Missing"} ok={item.installed} />
          {item.active ? <Badge>Active</Badge> : null}
          {item.experimental ? <Badge variant="outline">Experimental</Badge> : null}
          <Badge variant={item.backend === "Mock" ? "muted" : "outline"}>
            {item.backend}
          </Badge>
        </div>
        <DetailList title="Required models" values={item.required_models} />
        <DetailList title="Missing models" values={item.missing_models} danger />
        <DetailList title="Missing nodes" values={item.missing_nodes} danger />
        <DetailList title="Details" values={item.details} />
      </CardContent>
    </Card>
  );
}

function WorkflowSection({ workflows }: { workflows: WorkflowCheck[] }) {
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Workflow className="h-4 w-4 text-primary" />
        Workflows
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {workflows.map((workflow) => (
          <Card key={workflow.path}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <CardTitle className="truncate text-sm">
                    {workflow.name}
                  </CardTitle>
                  <CardDescription className="truncate">
                    {workflow.path}
                  </CardDescription>
                </div>
                <ClipboardList className="h-5 w-5 shrink-0 text-muted-foreground" />
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <StatusBadge
                  label={workflow.exists ? "Installed" : "Missing"}
                  ok={workflow.exists}
                />
                {workflow.active ? <Badge>Active</Badge> : null}
                {workflow.experimental ? (
                  <Badge variant="outline">Experimental</Badge>
                ) : null}
                <Badge variant="muted">{workflow.kind}</Badge>
              </div>
              <DetailList title="Required models" values={workflow.required_models} />
              <DetailList title="Details" values={workflow.details} />
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function StatusBadge({ label, ok }: { label: string; ok: boolean }) {
  return <Badge variant={ok ? "success" : "destructive"}>{label}</Badge>;
}

function DetailList({
  title,
  values,
  danger,
}: {
  title: string;
  values: string[];
  danger?: boolean;
}) {
  if (!values.length) return null;
  return (
    <div>
      <p className="mb-1 text-xs text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-1.5">
        {values.slice(0, 8).map((value) => (
          <Badge
            key={value}
            variant={danger ? "destructive" : "muted"}
            className="max-w-full truncate font-mono"
          >
            {value}
          </Badge>
        ))}
        {values.length > 8 ? (
          <Badge variant="outline">+{values.length - 8}</Badge>
        ) : null}
      </div>
    </div>
  );
}
