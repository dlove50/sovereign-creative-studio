"use client";

import { useEffect, useState } from "react";
import { Loader2, Play, Plus, RotateCcw, Trash2 } from "lucide-react";

import { api, assetUrl } from "@/lib/api";
import { TrainingPlayer as Player } from "./training-player";
import { cn } from "@/lib/utils";
import { confirmDialog } from "@/components/ui/confirm-host";

type Item = Awaited<ReturnType<typeof api.getInteractive>>;
type Node = Item["nodes"][number];
type Clip = Awaited<ReturnType<typeof api.listInteractiveClips>>[number];

const MAX_CHOICES = 4;
const newId = () => Math.random().toString(36).slice(2, 10);

export function InteractiveEditorView({ itemId }: { itemId: string }) {
  const [item, setItem] = useState<Item | null>(null);
  const [title, setTitle] = useState("");
  const [nodes, setNodes] = useState<Node[]>([]);
  const [startId, setStartId] = useState<string | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [tab, setTab] = useState<"edit" | "play">("edit");
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<"scorm12" | "scorm2004" | "xapi">("scorm12");
  const [saved, setSaved] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getInteractive(itemId).then((i) => { setItem(i); setTitle(i.title); setNodes(i.nodes); setStartId(i.start_node_id); })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not open it."));
    api.listInteractiveClips().then(setClips).catch(() => setClips([]));
  }, [itemId]);

  const edit = (fn: () => void) => { fn(); setSaved(false); };
  const patchNode = (id: string, patch: Partial<Node>) => edit(() => setNodes((all) => all.map((n) => (n.id === id ? { ...n, ...patch } : n))));

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const out = await api.updateInteractive(itemId, { title, nodes, start_node_id: startId });
      setNodes(out.nodes);
      setStartId(out.start_node_id);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function exportScorm() {
    setExporting(true);
    setError(null);
    try { await api.exportInteractivePackage(itemId, exportFormat); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not export the lesson."); }
    finally { setExporting(false); }
  }

  if (!item) return <p className="py-20 text-center text-sm text-muted-foreground">{error ?? "Opening…"}</p>;
  const field = "h-10 rounded-xl border border-input bg-background px-3 text-sm text-foreground";
  return (
    <div className="mx-auto max-w-[900px]">
      <div className="flex flex-wrap items-center gap-3 pt-4">
        <input disabled={saving} value={title} onChange={(e) => edit(() => setTitle(e.target.value.slice(0, 200)))} aria-label="Title" className="min-w-[220px] flex-1 bg-transparent text-3xl font-extrabold tracking-[-0.03em] focus:outline-none" />
        <div role="tablist" className="flex rounded-full border border-border p-1 text-sm">
          {(["edit", "play"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)} className={cn("rounded-full px-4 py-1.5 font-medium", tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
              {t === "edit" ? "Edit" : "Preview"}
            </button>
          ))}
        </div>
        <button type="button" disabled={saving || saved} onClick={save} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}{saved ? "Saved" : "Save"}
        </button>
      </div>
      {error ? <p className="mt-3 rounded-xl bg-destructive/15 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor="export-format">Export format</label>
        <select id="export-format" value={exportFormat} disabled={exporting} onChange={(e) => setExportFormat(e.target.value as "scorm12" | "scorm2004" | "xapi")} className="h-10 rounded-full border border-border bg-background px-3 text-sm">
          <option value="scorm12">SCORM 1.2</option>
          <option value="scorm2004">SCORM 2004 (4th Edition)</option>
          <option value="xapi">xAPI (Tin Can)</option>
        </select>
        <button type="button" disabled={!saved || saving || exporting || !nodes.length} onClick={exportScorm} className="rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised disabled:opacity-50">{exporting ? "Packaging lesson…" : "Export lesson"}</button>
        <p className="text-xs text-muted-foreground">{saved ? (exportFormat === "xapi" ? "Includes clips, branching and quizzes. Your learning record store supplies its address when it launches the lesson. Up to 512 MB of media." : "Includes clips, branching, quizzes, and LMS progress tracking. Up to 512 MB of media.") : "Save changes before exporting."}</p>
      </div>

      {tab === "play" ? (
        <div className="mt-6">
          {saved ? <Player key={`${startId}-${nodes.length}`} nodes={nodes} startId={startId} /> : <p className="py-10 text-center text-sm text-muted-foreground">Save your changes to preview them.</p>}
        </div>
      ) : (
        <>
          <fieldset disabled={saving} className="disabled:opacity-70"><ul className="mt-6 space-y-3">
            {nodes.map((node, index) => (
              <li key={node.id} className="rounded-3xl border border-border bg-card/60 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <input value={node.title} onChange={(e) => patchNode(node.id, { title: e.target.value.slice(0, 120) })} placeholder={`Clip ${index + 1}`} aria-label={`Name of clip ${index + 1}`} className={cn(field, "flex-1 min-w-[160px]")} />
                  <select value={node.video_url} onChange={(e) => patchNode(node.id, { video_url: e.target.value })} aria-label={`Video for clip ${index + 1}`} className={cn(field, "max-w-[280px]")}>
                    <option value="">Choose a video…</option>
                    {node.video_url && !clips.some((c) => c.url === node.video_url) ? <option value={node.video_url}>{node.video_url.split("/").pop()}</option> : null}
                    {clips.map((c) => <option key={c.url} value={c.url}>{c.title}</option>)}
                  </select>
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <input type="radio" name="start" checked={startId === node.id} onChange={() => edit(() => setStartId(node.id))} /> Start here
                  </label>
                  <button type="button" aria-label={`Delete clip ${index + 1}`} onClick={async () => { if (await confirmDialog(`Delete clip ${index + 1} and the choices that lead to it?`)) edit(() => {
                    setNodes((all) => all.filter((n) => n.id !== node.id).map((n) => ({ ...n, choices: n.choices.filter((c) => c.next !== node.id) })));
                    if (startId === node.id) setStartId(nodes.find((n) => n.id !== node.id)?.id ?? null);
                  }); }} className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-raised hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
                </div>
                <label className="mt-4 block text-sm font-medium">Step instructions<textarea maxLength={2000} value={node.body||""} onChange={e=>patchNode(node.id,{body:e.target.value})} className="mt-2 w-full rounded-lg border border-border bg-background p-3 text-foreground"/></label>
                <label className="mt-4 block text-sm font-medium">Knowledge-check question (optional)<textarea maxLength={1000} value={node.question||""} onChange={e=>patchNode(node.id,{question:e.target.value,choices:node.choices.map(c=>({...c,is_correct:e.target.value.trim()?(c.is_correct??false):null}))})} className="mt-2 w-full rounded-lg border border-border bg-background p-3 text-foreground" placeholder="What should the learner do next?"/></label>
                {node.question&&<p className="mt-2 text-sm text-muted-foreground">Mark at least one correct choice. Link incorrect choices to a retry or explanation step.</p>}
                <ul className="mt-3 space-y-2">
                  {node.choices.map((choice, ci) => (
                    <li key={ci} className="flex flex-wrap items-center gap-2 pl-3">
                      <span className="text-xs text-muted-foreground">Viewer picks</span>
                      <input value={choice.label} onChange={(e) => patchNode(node.id, { choices: node.choices.map((c, i) => (i === ci ? { ...c, label: e.target.value.slice(0, 80) } : c)) })} placeholder="Button text" aria-label={`Choice ${ci + 1} text`} className={cn(field, "w-[200px]")} />
                      <span className="text-xs text-muted-foreground">and goes to</span>
                      <select value={choice.next} onChange={(e) => patchNode(node.id, { choices: node.choices.map((c, i) => (i === ci ? { ...c, next: e.target.value } : c)) })} aria-label={`Choice ${ci + 1} goes to`} className={cn(field, "w-[200px]")}>
                        {nodes.map((n, i) => <option key={n.id} value={n.id}>{n.title || `Clip ${i + 1}`}</option>)}
                      </select>
                      {node.question&&<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={choice.is_correct===true} onChange={e=>patchNode(node.id,{choices:node.choices.map((c,i)=>i===ci?{...c,is_correct:e.target.checked}:c)})}/>Correct answer</label>}
                      <label className="w-full text-sm">Feedback shown before continuing<textarea maxLength={1000} value={choice.feedback||""} onChange={e=>patchNode(node.id,{choices:node.choices.map((c,i)=>i===ci?{...c,feedback:e.target.value}:c)})} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-foreground"/></label>
                      <button type="button" aria-label="Remove choice" onClick={() => patchNode(node.id, { choices: node.choices.filter((_, i) => i !== ci) })} className="text-xs text-muted-foreground hover:text-destructive">Remove</button>
                    </li>
                  ))}
                </ul>
                {node.choices.length < MAX_CHOICES ? (
                  <button type="button" onClick={() => patchNode(node.id, { choices: [...node.choices, { label: "", is_correct: node.question?false:null, next: nodes.find((n) => n.id !== node.id)?.id ?? node.id }] })} className="mt-2 ml-3 text-xs font-medium text-primary hover:underline">
                    + Add a choice
                  </button>
                ) : null}
              </li>
            ))}
          </ul></fieldset>
          <button disabled={saving} type="button" onClick={() => edit(() => {
            const id = newId();
            setNodes((all) => [...all, { id, title: "", video_url: "", choices: [] }]);
            setStartId((cur) => cur ?? id);
          })} className="mt-4 inline-flex items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium hover:bg-raised">
            <Plus className="h-4 w-4" /> Add a clip
          </button>
          {nodes.length > 0 ? <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground"><Play className="h-3.5 w-3.5" /> Save, then open Preview to try it.</p> : null}
        </>
      )}
    </div>
  );
}
