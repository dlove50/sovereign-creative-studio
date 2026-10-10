"use client";
import { confirmDialog } from "@/components/ui/confirm-host";

import { useEffect, useMemo, useState } from "react";
import type React from "react";
import Link from "next/link";
import {
  Check,
  ClipboardList,
  Clipboard,
  Download,
  ExternalLink,
  FileText,
  Film,
  ImageIcon,
  Layers,
  Loader2,
  PackagePlus,
  Pencil,
  PenLine,
  PlaySquare,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
  X,
  XCircle,
} from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import type {
  BrandKit,
  CampaignBundle,
  CreativeBrief,
  CreativeBriefInput,
  LibraryItem,
  ProjectWorkspace,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { formatDate, TextAreaField, TextField } from "@/components/project-workspace/project-workspace-sections";


const EMPTY_BRIEF: CreativeBriefInput = {
  title: "",
  campaign_goal: "",
  target_channels: "",
  deliverables: "",
  key_messages: "",
  creative_direction: "",
  reference_notes: "",
  selected_asset_ids: [],
  status: "draft",
};

const BRIEF_STATUSES = ["draft", "in_review", "approved", "archived"];

function buildBriefSummary(brief: CreativeBrief): string {
  const lines = [`# ${brief.title}`, `Status: ${brief.status}`];
  const add = (label: string, value: string | null) => {
    if (value && value.trim()) lines.push(`\n${label}:\n${value.trim()}`);
  };
  add("Goal", brief.campaign_goal);
  add("Channels", brief.target_channels);
  add("Deliverables", brief.deliverables);
  add("Key messages", brief.key_messages);
  add("Creative direction", brief.creative_direction);
  add("Reference notes", brief.reference_notes);
  return lines.join("\n");
}

export function CreativeBriefsTab({
  briefs,
  onChange,
  projectId,
}: {
  briefs: CreativeBrief[];
  onChange: (next: CreativeBrief[]) => void;
  projectId: string;
}) {
  const [mode, setMode] = useState<"list" | "edit">("list");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CreativeBriefInput>(EMPTY_BRIEF);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryOf, setSummaryOf] = useState<CreativeBrief | null>(null);
  const [copied, setCopied] = useState(false);

  function setField(field: keyof CreativeBriefInput, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function startNew() {
    setForm(EMPTY_BRIEF);
    setEditingId(null);
    setError(null);
    setMode("edit");
  }

  function startEdit(brief: CreativeBrief) {
    setForm({
      title: brief.title,
      campaign_goal: brief.campaign_goal ?? "",
      target_channels: brief.target_channels ?? "",
      deliverables: brief.deliverables ?? "",
      key_messages: brief.key_messages ?? "",
      creative_direction: brief.creative_direction ?? "",
      reference_notes: brief.reference_notes ?? "",
      selected_asset_ids: brief.selected_asset_ids,
      status: brief.status,
    });
    setEditingId(brief.id);
    setError(null);
    setMode("edit");
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        const updated = await api.updateBrief(projectId, editingId, form);
        onChange(briefs.map((b) => (b.id === updated.id ? updated : b)));
      } else {
        const created = await api.createBrief(projectId, form);
        onChange([created, ...briefs]);
      }
      setMode("list");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save brief");
    } finally {
      setSaving(false);
    }
  }

  async function remove(brief: CreativeBrief) {
    if (!await confirmDialog(`Delete brief "${brief.title}"?`)) return;
    try {
      await api.deleteBrief(projectId, brief.id);
      onChange(briefs.filter((b) => b.id !== brief.id));
      if (summaryOf?.id === brief.id) setSummaryOf(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete brief");
    }
  }

  async function copySummary(brief: CreativeBrief) {
    await navigator.clipboard.writeText(buildBriefSummary(brief));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (mode === "edit") {
    return (
      <form
        onSubmit={save}
        className="space-y-5 rounded-lg border border-border bg-card p-5"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            {editingId ? "Edit brief" : "New brief"}
          </h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setMode("list")}
          >
            <X className="h-4 w-4" />
            Cancel
          </Button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label="Title"
            value={form.title ?? ""}
            onChange={(next) => setField("title", next)}
            placeholder="Spring launch campaign"
          />
          <div className="space-y-2">
            <Label>Status</Label>
            <select
              value={form.status ?? "draft"}
              onChange={(event) => setField("status", event.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background/40 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {BRIEF_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
        </div>
        <TextAreaField
          label="Campaign goal"
          value={form.campaign_goal ?? ""}
          onChange={(next) => setField("campaign_goal", next)}
          placeholder="What should this campaign achieve?"
        />
        <TextField
          label="Target channels"
          value={form.target_channels ?? ""}
          onChange={(next) => setField("target_channels", next)}
          placeholder="Instagram, TikTok, email"
        />
        <TextAreaField
          label="Deliverables"
          value={form.deliverables ?? ""}
          onChange={(next) => setField("deliverables", next)}
          placeholder="3 product scenes, 2 captions, 1 short video"
        />
        <TextAreaField
          label="Key messages"
          value={form.key_messages ?? ""}
          onChange={(next) => setField("key_messages", next)}
          placeholder="Premium, limited edition, sustainably made"
        />
        <TextAreaField
          label="Creative direction"
          value={form.creative_direction ?? ""}
          onChange={(next) => setField("creative_direction", next)}
          placeholder="Bright daylight, pastel palette, editorial framing"
        />
        <TextAreaField
          label="Reference notes"
          value={form.reference_notes ?? ""}
          onChange={(next) => setField("reference_notes", next)}
          placeholder="Links or notes for inspiration"
        />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" disabled={saving}>
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {editingId ? "Save brief" : "Create brief"}
        </Button>
      </form>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Plan a campaign before generating. A selected brief can be attached to
          scene and copy generation to keep outputs on-plan.
        </p>
        <Button type="button" onClick={startNew}>
          <Plus className="h-4 w-4" />
          New brief
        </Button>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {briefs.length === 0 ? (
        <EmptyState message="No creative briefs yet. Create one to plan a campaign." />
      ) : (
        <div className="space-y-3">
          {briefs.map((brief) => (
            <div
              key={brief.id}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <ClipboardList className="h-4 w-4 text-primary" />
                    <span className="truncate text-sm font-semibold">
                      {brief.title}
                    </span>
                    <Badge
                      variant={brief.status === "approved" ? "success" : "muted"}
                      className="capitalize"
                    >
                      {brief.status.replace("_", " ")}
                    </Badge>
                  </div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {brief.campaign_goal || "No campaign goal yet."}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {brief.target_channels ? (
                      <span>Channels: {brief.target_channels}</span>
                    ) : null}
                    {brief.deliverables ? (
                      <span className="line-clamp-1">
                        Deliverables: {brief.deliverables}
                      </span>
                    ) : null}
                    <span>Updated {formatDate(brief.updated_at)}</span>
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setSummaryOf((current) =>
                        current?.id === brief.id ? null : brief,
                      )
                    }
                  >
                    <FileText className="h-4 w-4" />
                    Summary
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => startEdit(brief)}
                  >
                    <Pencil className="h-4 w-4" />
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => remove(brief)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              {summaryOf?.id === brief.id ? (
                <div className="mt-3 space-y-2 rounded-md border border-border bg-background/50 p-3">
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => copySummary(brief)}
                    >
                      {copied ? (
                        <Check className="h-4 w-4" />
                      ) : (
                        <Clipboard className="h-4 w-4" />
                      )}
                      {copied ? "Copied" : "Copy summary"}
                    </Button>
                  </div>
                  <pre className="whitespace-pre-wrap text-sm text-foreground/90">
                    {buildBriefSummary(brief)}
                  </pre>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
