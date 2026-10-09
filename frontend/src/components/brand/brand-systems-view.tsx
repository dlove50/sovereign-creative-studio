"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Palette, Plus, Trash2, X } from "lucide-react";

import { api } from "@/lib/api";
import type { BrandKit, Project } from "@/lib/types";

type Entry = { project: Project; kit: BrandKit };

const EMPTY: BrandKit = {
  brand_name: "", brand_voice: "", target_audience: "", primary_colors: "",
  style_keywords: "", negative_keywords: "", product_positioning: "", campaign_notes: "",
};

const FIELDS: { key: keyof BrandKit; label: string; hint: string; long?: boolean }[] = [
  { key: "brand_name", label: "Brand name", hint: "How the brand is written" },
  { key: "brand_voice", label: "Voice and tone", hint: "e.g. warm, plain-spoken, confident", long: true },
  { key: "target_audience", label: "Who it is for", hint: "e.g. small business owners in Canada" },
  { key: "primary_colors", label: "Colors", hint: "Comma separated, e.g. #22b8f0, #0b1220, white" },
  { key: "style_keywords", label: "Look and feel", hint: "e.g. clean, bright, editorial" },
  { key: "negative_keywords", label: "Avoid", hint: "e.g. clutter, stock-photo smiles" },
  { key: "product_positioning", label: "What it offers", hint: "One or two sentences", long: true },
  { key: "campaign_notes", label: "Notes", hint: "Anything else videos should respect", long: true },
];

/** Comma-separated colors that browsers understand, for the swatches. */
export function swatches(colors: string | null): string[] {
  return (colors ?? "").split(",").map((c) => c.trim()).filter((c) => c && typeof CSS !== "undefined" && CSS.supports("color", c)).slice(0, 6);
}

export function BrandSystemsView() {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [naming, setNaming] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const projects = await api.listProjects();
    const kits = await Promise.all(projects.map((p) => api.getBrandKit(p.id).catch(() => EMPTY)));
    setEntries(projects.map((project, i) => ({ project, kit: kits[i] })));
  }
  useEffect(() => { load().catch(() => setEntries([])); }, []);

  async function createBrand() {
    if (!newName.trim()) return;
    setError(null);
    try {
      const project = await api.createProject(newName.trim());
      const kit = { ...EMPTY, brand_name: newName.trim() };
      await api.updateBrandKit(project.id, kit);
      setNaming(false);
      setNewName("");
      await load();
      setEditing({ project, kit });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The brand system could not be created.");
    }
  }

  async function removeBrand(entry: Entry) {
    if (!window.confirm(`Delete the brand system “${entry.kit.brand_name || entry.project.name}”? Its colors, fonts and logos are removed.`)) return;
    setError(null);
    try {
      await api.deleteProject(entry.project.id);
      await load();
    } catch (e) {
      // The server refuses when videos or other work still belong to it, and says what is attached.
      setError(e instanceof Error ? e.message : "The brand system could not be deleted.");
    }
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateBrandKit(editing.project.id, editing.kit);
      await load();
      setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Changes could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  const configured = (entries ?? []).filter((e) => Object.values(e.kit).some((v) => v && String(v).trim()));
  return (
    <div className="mx-auto max-w-[1040px]">
      <h1 className="pt-2 text-4xl font-extrabold tracking-[-0.03em]">Brand systems</h1>
      <p className="mt-1 text-sm text-muted-foreground">A brand system keeps every video consistent without restyling elements one by one. Pick one in the Video agent to shape its scripts.</p>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <li>
          {naming ? (
            <div className="flex aspect-[16/10] flex-col justify-center gap-2 rounded-2xl border border-primary/60 bg-card p-4">
              <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && createBrand()} placeholder="Brand name" aria-label="Brand name" className="h-10 rounded-xl border border-input bg-background px-3 text-sm" />
              <span className="flex gap-2">
                <button type="button" onClick={createBrand} disabled={!newName.trim()} className="rounded-full bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground disabled:opacity-60">Create</button>
                <button type="button" onClick={() => { setNaming(false); setNewName(""); }} className="rounded-full px-3 py-1.5 text-sm text-muted-foreground hover:bg-raised">Cancel</button>
              </span>
            </div>
          ) : (
            <button type="button" onClick={() => setNaming(true)} className="flex aspect-[16/10] w-full items-center justify-center gap-2 rounded-2xl border border-border bg-card/50 text-sm font-semibold hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Plus className="h-4 w-4" /> Add new
            </button>
          )}
        </li>
        {entries === null ? (
          <li className="flex items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…</li>
        ) : (
          configured.map((e) => {
            const colors = swatches(e.kit.primary_colors);
            return (
              <li key={e.project.id}>
                <button type="button" onClick={() => setEditing(e)} className="block w-full text-left focus-visible:outline-none">
                  <div className="flex aspect-[16/10] flex-col justify-between overflow-hidden rounded-2xl border border-border bg-card/70 p-4 transition-colors hover:border-primary/60">
                    <Palette className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                    <span>
                      <span className="line-clamp-2 text-sm text-muted-foreground">{e.kit.brand_voice || e.kit.product_positioning || "No voice or description yet"}</span>
                      <span className="mt-3 flex h-6 overflow-hidden rounded-md border border-border">
                        {colors.length ? colors.map((c) => <span key={c} style={{ background: c }} className="flex-1" title={c} />) : <span className="flex-1 bg-raised" />}
                      </span>
                    </span>
                  </div>
                  <p className="mt-2 truncate text-sm font-semibold">{e.kit.brand_name || e.project.name}</p>
                </button>
                <span className="mt-2 flex items-center justify-between gap-3">
                  <Link href={`/brand/${e.project.id}`} className="text-sm text-primary hover:underline">Edit colors, fonts, and logos</Link>
                  <button type="button" onClick={() => removeBrand(e)} aria-label={`Delete brand system ${e.kit.brand_name || e.project.name}`} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /> Delete</button>
                </span>
              </li>
            );
          })
        )}
      </ul>
      {entries && configured.length === 0 ? <p className="mt-6 text-sm text-muted-foreground">No brand systems yet. Use Add new to make your first.</p> : null}

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label="Edit brand system" onClick={() => setEditing(null)}>
          <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-3xl border border-border bg-card p-5" onClick={(ev) => ev.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">{editing.kit.brand_name || editing.project.name}</h2>
              <button type="button" onClick={() => setEditing(null)} aria-label="Close" className="rounded-full p-1 text-muted-foreground hover:bg-raised"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-4 space-y-3">
              {FIELDS.map((f) => (
                <label key={f.key} className="block text-xs font-medium text-muted-foreground">
                  {f.label}
                  {f.long ? (
                    <textarea value={editing.kit[f.key] ?? ""} rows={2} placeholder={f.hint} onChange={(ev) => setEditing({ ...editing, kit: { ...editing.kit, [f.key]: ev.target.value } })} className="mt-1 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm text-foreground" />
                  ) : (
                    <input value={editing.kit[f.key] ?? ""} placeholder={f.hint} onChange={(ev) => setEditing({ ...editing, kit: { ...editing.kit, [f.key]: ev.target.value } })} className="mt-1 h-10 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground" />
                  )}
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setEditing(null)} className="rounded-full px-4 py-2 text-sm text-muted-foreground hover:bg-raised">Cancel</button>
              <button type="button" onClick={save} disabled={saving} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
