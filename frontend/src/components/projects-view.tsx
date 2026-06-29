"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Folder, Loader2, Plus } from "lucide-react";

import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";

export function ProjectsView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }

  useEffect(refresh, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      await api.createProject(name.trim(), description.trim());
      setName("");
      setDescription("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        {projects.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-center text-sm text-muted-foreground">
            <Folder className="h-6 w-6" />
            No projects yet. Create one to organize your generations.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.map((p) => (
              <Card key={p.id} className="transition-colors hover:bg-muted/40">
                <CardContent className="p-5">
                  <Link href={`/projects/${p.id}`} className="block">
                    <div className="mb-2 flex items-center gap-2">
                      <Folder className="h-4 w-4 text-primary" />
                      <h3 className="font-medium">{p.name}</h3>
                    </div>
                    <p className="line-clamp-2 text-sm text-muted-foreground">
                      {p.description || "No description"}
                    </p>
                  </Link>
                  <Link
                    href={`/projects/${p.id}`}
                    className={`${buttonVariants({
                      variant: "outline",
                      size: "sm",
                    })} mt-4`}
                  >
                    <ExternalLink className="h-4 w-4" />
                    Open workspace
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <form
        onSubmit={handleCreate}
        className="h-fit space-y-4 rounded-lg border border-border bg-card p-6"
      >
        <h3 className="text-sm font-semibold">New project</h3>
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Q3 product launch"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project for?"
            className="min-h-[90px]"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={creating || !name.trim()}>
          {creating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Create project
        </Button>
      </form>
    </div>
  );
}
