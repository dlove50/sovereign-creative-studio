"use client";

import { ChangeEvent, DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle, Check, CheckCircle2, Clipboard, Download, FileImage, FileText,
  History, Loader2, Play, RotateCcw, ScanText, Server, Trash2, UploadCloud, X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

const API = "/api/ocr";
const HISTORY_KEY = "sovereign-ocr-history-v1";

type Status = "checking" | "online" | "offline";
type Mode = "markdown" | "plain" | "raw";
type PageInput = { id: string; name: string; dataUrl: string; previewUrl: string };
type PageResult = { name: string; raw: string; clean: string };
type HistoryItem = { id: string; title: string; createdAt: string; pages: number; content: string };

function cleanOutput(raw: string) {
  const lines = raw.split(/\r?\n/);
  const blocks: string[] = [];
  let current: string[] = [];
  for (const line of lines) {
    const match = line.match(/^<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|\/det\|>(.*)$/);
    if (match) {
      if (current.length) blocks.push(current.join("\n"));
      current = match[1] === "image" ? [] : [match[2].trim()].filter(Boolean);
    } else {
      current.push(line);
    }
  }
  if (current.length) blocks.push(current.join("\n"));
  return blocks.join("\n\n")
    .replace(/<\|ref\|>/g, "").replace(/<\|\/ref\|>/g, "")
    .replace(/<\|det\|>.*?<\|\/det\|>/g, "").trim();
}

function asPlain(markdown: string) {
  return markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "").replace(/[*_~`>]/g, "")
    .replace(/^\s*[-+]\s+/gm, "• ").trim();
}

function downloadText(content: string, filename: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}

export function OcrStudioView() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>("checking");
  const [pages, setPages] = useState<PageInput[]>([]);
  const [results, setResults] = useState<PageResult[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<Mode>("markdown");
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const checkStatus = useCallback(async () => {
    setStatus("checking");
    try {
      const response = await fetch(`${API}/status`, { signal: AbortSignal.timeout(5000), credentials: "include" });
      const info = response.ok ? await response.json() : null;
      setStatus(info?.available ? "online" : "offline");
    } catch { setStatus("offline"); }
  }, []);

  useEffect(() => {
    checkStatus();
    try { setHistory(JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]")); } catch { /* ignore */ }
  }, [checkStatus]);

  const combined = useMemo(() => results.map((r, i) =>
    results.length > 1 ? `## Page ${i + 1}\n\n${r.clean}` : r.clean).join("\n\n---\n\n"), [results]);
  const visibleContent = mode === "raw"
    ? results.map((r, i) => `--- ${r.name} ---\n${r.raw}`).join("\n\n")
    : mode === "plain" ? asPlain(combined) : combined;

  async function fileToPages(file: File): Promise<PageInput[]> {
    if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
      const bytes = new Uint8Array(await file.arrayBuffer());
      const pdf = await pdfjs.getDocument({ data: bytes }).promise;
      const rendered: PageInput[] = [];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 2 });
        const canvas = document.createElement("canvas");
        canvas.width = viewport.width; canvas.height = viewport.height;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Could not render PDF page.");
        await page.render({ canvasContext: context, viewport }).promise;
        const dataUrl = canvas.toDataURL("image/jpeg", 0.94);
        rendered.push({ id: crypto.randomUUID(), name: `${file.name} · page ${pageNumber}`, dataUrl, previewUrl: dataUrl });
      }
      return rendered;
    }
    if (!file.type.startsWith("image/")) throw new Error(`${file.name} is not a supported image or PDF.`);
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file);
    });
    return [{ id: crypto.randomUUID(), name: file.name, dataUrl, previewUrl: dataUrl }];
  }

  async function addFiles(files: File[]) {
    setError("");
    try {
      const additions: PageInput[] = [];
      for (const file of files) additions.push(...await fileToPages(file));
      setPages((current) => [...current, ...additions]);
      setResults([]);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not open that file."); }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); setDragging(false); addFiles(Array.from(event.dataTransfer.files));
  }

  async function runOcr() {
    if (!pages.length || running) return;
    if (status !== "online") { setError("The local OCR engine is not available. Check that you are signed in and the backend is running, then retry."); return; }
    setRunning(true); setResults([]); setError(""); setProgress(0);
    const completed: PageResult[] = [];
    try {
      for (let i = 0; i < pages.length; i++) {
        const page = pages[i];
        setProgress(i);
        const response = await fetch(`${API}/read`, {
          method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
          body: JSON.stringify({ image: page.dataUrl }),
        });
        if (!response.ok) throw new Error(`OCR failed on ${page.name}: ${await response.text()}`);
        const payload = await response.json();
        const raw: string = payload.text || "";
        completed.push({ name: page.name, raw, clean: cleanOutput(raw) });
        setResults([...completed]); setProgress(i + 1);
      }
      const content = completed.map((r, i) => completed.length > 1 ? `## Page ${i + 1}\n\n${r.clean}` : r.clean).join("\n\n---\n\n");
      const item: HistoryItem = { id: crypto.randomUUID(), title: pages[0].name, createdAt: new Date().toISOString(), pages: pages.length, content };
      const next = [item, ...history].slice(0, 12); setHistory(next); localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    } catch (e) { setError(e instanceof Error ? e.message : "OCR request failed."); }
    finally { setRunning(false); }
  }

  async function copyResult() {
    await navigator.clipboard.writeText(visibleContent); setCopied(true); setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="mx-auto max-w-[1500px] animate-fade-up pb-12">
      <header className="mb-7 flex flex-col justify-between gap-4 xl:flex-row xl:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-primary">
            <ScanText className="h-4 w-4" /> Local document intelligence
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">OCR Studio</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Turn scans, screenshots, and PDFs into clean Markdown with the local RapidOCR engine (CPU, no download). Your files stay on this computer.</p>
        </div>
        <button onClick={checkStatus} className={cn("flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium", status === "online" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : status === "offline" ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-border bg-muted text-muted-foreground") }>
          {status === "checking" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className={cn("h-2 w-2 rounded-full", status === "online" ? "bg-emerald-400" : "bg-red-400")} />}
          {status === "online" ? "Local OCR ready" : status === "offline" ? "OCR unavailable · retry" : "Checking OCR"}
        </button>
      </header>

      <div className="grid gap-5 xl:grid-cols-[minmax(330px,0.78fr)_minmax(520px,1.4fr)_280px]">
        <section className="rounded-2xl border border-border bg-card/70 p-4 shadow-2xl shadow-black/10">
          <div className="mb-4 flex items-center justify-between">
            <div><h2 className="font-semibold">Documents</h2><p className="text-xs text-muted-foreground">PNG, JPG, WEBP or PDF</p></div>
            {pages.length ? <button onClick={() => { setPages([]); setResults([]); }} className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Clear documents"><Trash2 className="h-4 w-4" /></button> : null}
          </div>
          <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop} onClick={() => inputRef.current?.click()} className={cn("group flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-5 text-center transition", dragging ? "border-primary bg-primary/10" : "border-border bg-background/30 hover:border-primary/60 hover:bg-primary/5")}>
            <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15 text-primary"><UploadCloud className="h-6 w-6" /></span>
            <p className="text-sm font-medium">Drop documents here</p><p className="mt-1 text-xs text-muted-foreground">or click to browse your computer</p>
            <input ref={inputRef} type="file" multiple accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff,application/pdf" className="hidden" onChange={(e: ChangeEvent<HTMLInputElement>) => { addFiles(Array.from(e.target.files || [])); e.target.value = ""; }} />
          </div>
          {pages.length ? <div className="mt-4 max-h-[360px] space-y-2 overflow-y-auto pr-1">{pages.map((page, index) => (
            <div key={page.id} className="flex items-center gap-3 rounded-xl border border-border bg-background/35 p-2">
              <img src={page.previewUrl} alt="" className="h-14 w-11 rounded-md bg-white object-contain" />
              <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{page.name}</p><p className="mt-1 text-[11px] text-muted-foreground">Page {index + 1}</p></div>
              {running && index === progress ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : index < progress ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <button onClick={(e) => { e.stopPropagation(); setPages((all) => all.filter((p) => p.id !== page.id)); }} className="p-1 text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>}
            </div>
          ))}</div> : null}
          <button onClick={runOcr} disabled={!pages.length || running || status !== "online"} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40">
            {running ? <><Loader2 className="h-4 w-4 animate-spin" /> Reading page {Math.min(progress + 1, pages.length)} of {pages.length}</> : <><Play className="h-4 w-4 fill-current" /> Run OCR</>}
          </button>
          {error ? <div className="mt-3 flex gap-2 rounded-xl border border-red-500/25 bg-red-500/10 p-3 text-xs leading-5 text-red-200"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}
        </section>

        <section className="min-h-[650px] overflow-hidden rounded-2xl border border-border bg-card/70 shadow-2xl shadow-black/10">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="flex rounded-lg bg-muted p-1">{(["markdown", "plain", "raw"] as Mode[]).map((item) => <button key={item} onClick={() => setMode(item)} className={cn("rounded-md px-3 py-1.5 text-xs font-medium capitalize transition", mode === item ? "bg-card text-foreground shadow" : "text-muted-foreground hover:text-foreground")}>{item}</button>)}</div>
            <div className="flex items-center gap-1">
              <button disabled={!visibleContent} onClick={copyResult} className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30">{copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Clipboard className="h-4 w-4" />}{copied ? "Copied" : "Copy"}</button>
              <button disabled={!visibleContent} onClick={() => downloadText(visibleContent, `unlimited-ocr-${new Date().toISOString().slice(0,10)}.${mode === "markdown" ? "md" : "txt"}`)} className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30"><Download className="h-4 w-4" /> Download</button>
            </div>
          </div>
          <div className="h-[650px] overflow-y-auto p-6 md:p-8">
            {!results.length && !running ? <div className="flex h-full flex-col items-center justify-center text-center"><span className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-muted/60 text-muted-foreground"><FileText className="h-7 w-7" /></span><h3 className="font-medium">Your document will appear here</h3><p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Add an image or PDF, then run OCR. Tables, headings, lists, and document structure will be preserved as Markdown.</p></div> : null}
            {running && !results.length ? <div className="flex h-full flex-col items-center justify-center text-center"><Loader2 className="mb-5 h-9 w-9 animate-spin text-primary" /><h3 className="font-medium">Reading your document</h3><p className="mt-2 text-sm text-muted-foreground">The first page may take a little longer.</p></div> : null}
            {mode === "markdown" && results.length ? <article className="ocr-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{combined}</ReactMarkdown></article> : null}
            {mode !== "markdown" && results.length ? <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7 text-foreground/90">{visibleContent}</pre> : null}
            {running && results.length ? <div className="mt-8 flex items-center gap-2 border-t border-border pt-5 text-xs text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin text-primary" /> Continuing with page {progress + 1}…</div> : null}
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-border bg-card/70 p-4">
            <div className="mb-4 flex items-center gap-2"><Server className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">Private & local</h2></div>
            <div className="space-y-3 text-xs leading-5 text-muted-foreground"><p>Pages go from this browser to the OCR engine running on this computer.</p><p>No cloud upload. No credits. No third-party OCR service.</p></div>
          </section>
          <section className="rounded-2xl border border-border bg-card/70 p-4">
            <div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-2"><History className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">Recent results</h2></div>{history.length ? <button onClick={() => { setHistory([]); localStorage.removeItem(HISTORY_KEY); }} className="text-[11px] text-muted-foreground hover:text-foreground">Clear</button> : null}</div>
            {!history.length ? <p className="text-xs leading-5 text-muted-foreground">Completed OCR sessions will be saved in this browser.</p> : <div className="space-y-2">{history.map((item) => <button key={item.id} onClick={() => { setResults([{ name: item.title, raw: item.content, clean: item.content }]); setMode("markdown"); }} className="w-full rounded-xl border border-border bg-background/30 p-3 text-left hover:border-primary/40 hover:bg-primary/5"><p className="truncate text-xs font-medium">{item.title}</p><p className="mt-1 text-[11px] text-muted-foreground">{item.pages} page{item.pages === 1 ? "" : "s"} · {new Date(item.createdAt).toLocaleDateString()}</p></button>)}</div>}
          </section>
          <button onClick={() => { setPages([]); setResults([]); setError(""); setProgress(0); }} className="flex w-full items-center justify-center gap-2 rounded-xl border border-border px-3 py-2.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"><RotateCcw className="h-4 w-4" /> New session</button>
        </aside>
      </div>
    </div>
  );
}
