"use client";

import { useEffect, useState } from "react";
import { Brain, Loader2, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import type {
  CreativeBrief,
  CreativeDirectorResult,
  Project,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function CreativeDirectorView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);
  const [projectId, setProjectId] = useState("");
  const [briefId, setBriefId] = useState("");
  const [result, setResult] = useState<CreativeDirectorResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((loaded) => {
        setProjects(loaded);
        setProjectId(loaded[0]?.id ?? "");
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load projects"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!projectId) {
      setBriefs([]);
      return;
    }
    api
      .listBriefs(projectId)
      .then((loaded) => {
        setBriefs(loaded);
        setBriefId((current) =>
          loaded.some((brief) => brief.id === current)
            ? current
            : loaded[0]?.id ?? "",
        );
      })
      .catch(() => setBriefs([]));
  }, [projectId]);

  async function runDirector() {
    if (!projectId) return;
    setRunning(true);
    setError(null);
    try {
      setResult(
        await api.getCreativeDirectorRecommendations({
          project_id: projectId,
          brief_id: briefId || null,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create recommendations");
    } finally {
      setRunning(false);
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
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-primary" />
            Inputs
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="director-project">Project</Label>
            <select
              id="director-project"
              value={projectId}
              onChange={(event) => {
                setProjectId(event.target.value);
                setResult(null);
              }}
              className={selectClass}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="director-brief">Creative brief</Label>
            <select
              id="director-brief"
              value={briefId}
              onChange={(event) => setBriefId(event.target.value)}
              className={selectClass}
            >
              <option value="">No selected brief</option>
              {briefs.map((brief) => (
                <option key={brief.id} value={brief.id}>
                  {brief.title}
                </option>
              ))}
            </select>
          </div>
          {error ? (
            <p className="rounded-md bg-destructive/15 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <Button type="button" disabled={!projectId || running} onClick={runDirector}>
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Generate recommendations
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {!result ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-center text-sm text-muted-foreground">
            <Brain className="h-7 w-7" />
            Select a project and generate recommendations.
          </div>
        ) : (
          <>
            <Card>
              <CardContent className="p-5">
                <p className="text-sm text-muted-foreground">{result.summary}</p>
              </CardContent>
            </Card>
            <div className="grid gap-4 xl:grid-cols-2">
              {result.recommendations.map((item) => (
                <Card key={item.category}>
                  <CardContent className="space-y-3 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-semibold capitalize">{item.category}</h3>
                      <Badge variant="outline">
                        {Math.round(item.confidence * 100)}% confidence
                      </Badge>
                    </div>
                    <p className="text-sm">{item.recommendation}</p>
                    <p className="text-sm text-muted-foreground">{item.rationale}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
