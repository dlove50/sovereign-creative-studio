"use client";

import { useEffect, useRef, useState } from "react";
import { Images } from "lucide-react";

import { api } from "@/lib/api";
import type { Generation } from "@/lib/types";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonGrid } from "@/components/ui/skeleton";
import { GenerationCard } from "@/components/generation-card";
import { useStaggerIn } from "@/components/motion/use-motion";

export function GalleryView() {
  const [generations, setGenerations] = useState<Generation[] | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  useStaggerIn(grid, generations?.length ?? 0);

  useEffect(() => {
    api.listGenerations().then(setGenerations).catch(() => setGenerations([]));
  }, []);

  if (generations === null) {
    return <SkeletonGrid count={8} />;
  }

  if (generations.length === 0) {
    return (
      <EmptyState
        icon={Images}
        title="No pictures or videos yet"
        body="Everything you generate lands here, ready to download or reuse."
        action={{ label: "Create your first generation", href: "/create" }}
      />
    );
  }

  return (
    <div ref={grid} className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {generations.map((g) => (
        <GenerationCard key={g.id} generation={g} onDeleted={(id) => setGenerations((all) => (all ?? []).filter((x) => x.id !== id))} />
      ))}
    </div>
  );
}
