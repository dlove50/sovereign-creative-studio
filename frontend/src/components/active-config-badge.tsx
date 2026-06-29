"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { SlidersHorizontal } from "lucide-react";

import { api } from "@/lib/api";
import type { WorkflowManagerStatus } from "@/lib/types";

const LABELS: Record<string, string> = {
  image_model: "Product Scene Model",
  scene_mode: "Product Scene Mode",
  video_backend: "Video Backend",
  copy_backend: "Copy Provider",
};

type Field = "image_model" | "scene_mode" | "video_backend" | "copy_backend";

function valueFor(status: WorkflowManagerStatus, field: Field): string {
  switch (field) {
    case "image_model":
      return status.active_image_model;
    case "scene_mode":
      return status.active_scene_mode;
    case "video_backend":
      return status.active_video_backend;
    case "copy_backend":
      return status.active_copy_backend;
  }
}

/** Shows the active Workflow Manager settings relevant to a generation page. */
export function ActiveConfigBadge({ fields }: { fields: Field[] }) {
  const [status, setStatus] = useState<WorkflowManagerStatus | null>(null);

  useEffect(() => {
    api.getWorkflowManagerStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  if (!status) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
      {fields.map((field) => (
        <span key={field} className="flex items-center gap-1">
          {LABELS[field]}:
          <span className="font-medium text-foreground">
            {valueFor(status, field)}
          </span>
        </span>
      ))}
      <Link
        href="/workflow-manager"
        className="ml-auto flex items-center gap-1 text-primary hover:underline"
      >
        <SlidersHorizontal className="h-3.5 w-3.5" /> Change
      </Link>
    </div>
  );
}
