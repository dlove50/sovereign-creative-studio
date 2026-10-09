"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Coins, Folder, Images, Wand2 } from "lucide-react";

import { api } from "@/lib/api";
import type { Generation, Project, User } from "@/lib/types";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GenerationCard } from "@/components/generation-card";
import { LoadError } from "@/components/ui/load-error";

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Coins;
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="text-2xl font-semibold">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [generations, setGenerations] = useState<Generation[]>([]);

  const [loadError, setLoadError] = useState<string | null>(null);

  const load = () => {
    setLoadError(null);
    const fail = (e: unknown) => setLoadError(e instanceof Error ? e.message : "The studio didn't answer.");
    api.getMe().then(setUser).catch(fail);
    api.listProjects().then(setProjects).catch(fail);
    api.listGenerations().then(setGenerations).catch(fail);
  };
  useEffect(load, []);

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-xl border border-border bg-card p-8">
        <p className="text-sm text-primary">Sovereign Creative Studio</p>
        <h2 className="mt-2 max-w-xl text-3xl font-semibold tracking-tight">
          Turn a single prompt into on-brand visuals.
        </h2>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">
          Describe an idea and the studio generates a result you can reuse —
          running the full local stack (ComfyUI/LTX + local Qwen) on this machine.
        </p>
        <Link href="/create" className={`${buttonVariants({ size: "lg" })} mt-6`}>
          <Wand2 className="h-4 w-4" /> Start creating
        </Link>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <StatCard icon={Coins} label="Credits" value={user?.credits ?? "—"} />
        <StatCard icon={Folder} label="Projects" value={loadError ? "—" : projects.length} />
        <StatCard icon={Images} label="Generations" value={loadError ? "—" : generations.length} />
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium">Recent generations</h3>
          <Link
            href="/gallery"
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        </div>
        {loadError ? (
          <LoadError what="your recent work" message={loadError} onRetry={load} />
        ) : generations.length === 0 ? (
          <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
            No generations yet — your recent work will show up here.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {generations.slice(0, 4).map((g) => (
              <GenerationCard key={g.id} generation={g} onDeleted={(id) => setGenerations((all) => all.filter((x) => x.id !== id))} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
