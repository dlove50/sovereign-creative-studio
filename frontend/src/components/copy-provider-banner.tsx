"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, SlidersHorizontal } from "lucide-react";

import { api } from "@/lib/api";
import type {
  WorkflowManagerModels,
  WorkflowManagerStatus,
  WorkflowOption,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";

/** Shows the active Copy Studio provider, model, status, and any warnings. */
export function CopyProviderBanner() {
  const [status, setStatus] = useState<WorkflowManagerStatus | null>(null);
  const [active, setActive] = useState<WorkflowOption | null>(null);

  useEffect(() => {
    Promise.all([
      api.getWorkflowManagerStatus(),
      api.getWorkflowManagerModels(),
    ])
      .then(([s, m]: [WorkflowManagerStatus, WorkflowManagerModels]) => {
        setStatus(s);
        setActive(
          m.copy_models.find((o) => o.id === s.active_copy_backend) ?? null,
        );
      })
      .catch(() => {
        setStatus(null);
        setActive(null);
      });
  }, []);

  if (!status) return null;

  const isMock = status.active_copy_backend === "mock";
  const unavailable = active != null && !active.available;

  return (
    <div className="mb-4 space-y-2 rounded-md border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="text-muted-foreground">
          Copy provider:{" "}
          <span className="font-medium text-foreground">
            {active?.name ?? status.active_copy_backend}
          </span>
        </span>
        <span className="text-muted-foreground">
          Model:{" "}
          <span className="font-medium text-foreground">
            {status.active_copy_model}
          </span>
        </span>
        <Badge variant={isMock ? "muted" : unavailable ? "destructive" : "success"}>
          {isMock ? "mock" : unavailable ? "unavailable" : "live"}
        </Badge>
        <Link
          href="/workflow-manager"
          className="ml-auto flex items-center gap-1 text-primary hover:underline"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" /> Change provider
        </Link>
      </div>

      {isMock ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Using mock copy (templates). Pick a real provider in the Workflow
          Manager for AI-written copy.
        </p>
      ) : null}
      {unavailable ? (
        <p className="flex items-center gap-2 text-xs text-destructive">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {active?.note ??
            "This provider is currently unavailable; generation will fail until it's configured."}
        </p>
      ) : null}
    </div>
  );
}
