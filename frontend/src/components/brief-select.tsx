"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { CreativeBrief } from "@/lib/types";
import { Label } from "@/components/ui/label";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Optional creative-brief picker for generation pages. Loads the selected
 * project's briefs and clears a stale selection when the project changes.
 */
export function BriefSelect({
  projectId,
  value,
  onChange,
  id = "brief-select",
}: {
  projectId: string;
  value: string;
  onChange: (briefId: string) => void;
  id?: string;
}) {
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);

  useEffect(() => {
    if (!projectId) {
      setBriefs([]);
      return;
    }
    let active = true;
    api
      .listBriefs(projectId)
      .then((loaded) => {
        if (!active) return;
        setBriefs(loaded);
        // Drop a selection that doesn't belong to this project.
        if (value && !loaded.some((b) => b.id === value)) onChange("");
      })
      .catch(() => {
        if (active) setBriefs([]);
      });
    return () => {
      active = false;
    };
    // Reload whenever the project changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>Creative brief (optional)</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={selectClass}
      >
        <option value="">No brief</option>
        {briefs.map((brief) => (
          <option key={brief.id} value={brief.id}>
            {brief.title}
          </option>
        ))}
      </select>
    </div>
  );
}
