"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Images, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type { Generation } from "@/lib/types";
import { buttonVariants } from "@/components/ui/button";
import { GenerationCard } from "@/components/generation-card";

export function GalleryView() {
  const [generations, setGenerations] = useState<Generation[] | null>(null);

  useEffect(() => {
    api.listGenerations().then(setGenerations).catch(() => setGenerations([]));
  }, []);

  if (generations === null) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (generations.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border text-center text-sm text-muted-foreground">
        <Images className="h-6 w-6" />
        Nothing here yet.
        <Link href="/create" className={buttonVariants()}>
          Create your first generation
        </Link>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {generations.map((g) => (
        <GenerationCard key={g.id} generation={g} onDeleted={(id) => setGenerations((all) => (all ?? []).filter((x) => x.id !== id))} />
      ))}
    </div>
  );
}
