"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Lenis from "lenis";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Clapperboard, Download, Film, History, ImagePlus, Loader2, Plus, RefreshCw, Upload, Volume2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { motionApi, type MotionJob, type MotionStatus } from "@/lib/api/motion-studio";
import { StudioReveal } from "./studio-reveal";
import styles from "./motion-studio.module.css";

const DEFAULT_PROMPT = "Replace the primary character in @Video1 with @Image1. Match the reference character's full appearance, clothing and hairstyle. Preserve the original movement, expression, lip timing, camera, background and lighting.";
const STAGES = ["Upload", "Review", "Draft", "Export"];
const ACTIVE = ["preparing", "submitting", "rendering", "exporting"];

export function MotionStudioView() {
  const [jobs, setJobs] = useState<MotionJob[]>([]);
  const [job, setJob] = useState<MotionJob | null>(null);
  const [status, setStatus] = useState<MotionStatus | null>(null);
  const [stage, setStage] = useState(0);
  const [source, setSource] = useState<File | null>(null);
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState(0);
  const [seconds, setSeconds] = useState(10);
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [scene, setScene] = useState("");
  const [watched, setWatched] = useState(false);
  const [draftWatched, setDraftWatched] = useState(false);
  const [charges, setCharges] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const historyWrapper = useRef<HTMLDivElement>(null);
  const historyContent = useRef<HTMLDivElement>(null);
  const locked = useRef(false);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const uploadId = useRef<string | null>(null);

  function accept(next: MotionJob) {
    setJob(next);
    setJobs(previous => [next, ...previous.filter(item => item.id !== next.id)]);
  }
  useEffect(() => {
    let live = true;
    Promise.all([motionApi.jobs(), motionApi.status()]).then(([list, ready]) => {
      if (live) { setJobs(list); setStatus(ready); }
    }).catch(e => { if (live) setError(e.message); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!job || !ACTIVE.includes(job.status)) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await (job!.status === "rendering" ? motionApi.refresh(job!.id) : motionApi.get(job!.id));
        if (!live) return;
        accept(next);
        if (ACTIVE.includes(next.status)) timer = setTimeout(poll, 7000);
      } catch (e) { if (live) { setError(e instanceof Error ? e.message : "Could not refresh this project."); timer = setTimeout(poll, 15000); } }
    }
    timer = setTimeout(poll, 3000);
    return () => { live = false; clearTimeout(timer); };
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!historyOpen || !historyWrapper.current || !historyContent.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ wrapper: historyWrapper.current, content: historyContent.current, autoRaf: true, smoothWheel: true, lerp: 0.18 });
    return () => lenis.destroy();
  }, [historyOpen]);

  useEffect(() => { setSelectedDraft(job?.selected_draft || null); setDraftWatched(false); }, [job?.selected_draft]);

  useEffect(() => {
    if (!source) { setSourcePreview(null); return; }
    const url = URL.createObjectURL(source); setSourcePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [source]);

  const active = busy || !!job && ACTIVE.includes(job.status);
  const drafts = job?.operations.filter(op => op.kind === "draft" && op.status === "completed") || [];
  const draft = drafts.find(op => op.id === selectedDraft) || drafts.find(op => op.id === job?.selected_draft) || drafts[drafts.length - 1];
  const prepared = !!job?.files.includes("prepared.mp4");
  const expired = !!draft?.expires_at && new Date(draft.expires_at).getTime() <= Date.now();
  const currentFile = stage === 3 ? job?.final_file || draft?.file : stage === 2 ? draft?.file || (prepared ? "prepared.mp4" : null) : prepared ? "prepared.mp4" : null;
  const fileUrl = stage === 0 && sourcePreview ? sourcePreview : job && currentFile ? motionApi.file(job.id, currentFile) : null;

  async function run(action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Action failed. Try again."); }
    finally { locked.current = false; setBusy(false); }
  }
  function move(next: number) { setStage(next); setCharges(false); }
  function choose(next: MotionJob) {
    accept(next); setStage(next.final_file ? 3 : next.operations.some(op => op.kind === "draft" && op.status === "completed") ? 2 : next.approved ? 2 : 1);
    const last = next.operations.filter(op => op.kind === "draft").at(-1);
    setPrompt(last?.prompt || DEFAULT_PROMPT); setScene(last?.scene || ""); setSelectedDraft(next.selected_draft);
    setWatched(false); setDraftWatched(false); setCharges(false); setError(null); setHistoryOpen(false); pending.current = null;
  }
  async function upload() {
    if (!source) return;
    if (source.size > 200 * 1024 * 1024) throw new Error("Choose a video no larger than 200 MB.");
    uploadId.current ||= crypto.randomUUID();
    const form = new FormData(); form.append("request_id", uploadId.current); form.append("file", source);
    form.append("title", title || source.name.replace(/\.[^.]+$/, "")); form.append("start", String(start)); form.append("seconds", String(seconds));
    accept(await motionApi.upload(form)); move(1); setWatched(false);
  }
  async function render(kind: "draft" | "final") {
    if (!job) return;
    const body = { accept_charges: true, prompt: kind === "draft" ? prompt : "", scene: kind === "draft" ? scene : "", draft_id: kind === "final" ? draft?.id : null };
    const signature = JSON.stringify([job.id, kind, body]);
    if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
    accept(await motionApi.render(job.id, kind, { ...body, request_id: pending.current.id }));
    pending.current = null; setCharges(false); setDraftWatched(false);
  }

  return <div className={styles.studio}>
    <header className={styles.header}>
      <div><Link href="/apps" className={styles.back}><ArrowLeft size={15} /> All studios</Link><h1>Motion Studio</h1></div>
      <div className={styles.headerActions}>
        <Button variant="outline" onClick={() => setHistoryOpen(!historyOpen)} aria-expanded={historyOpen}><History size={16} /> Projects <span className={styles.count}>{jobs.length}</span></Button>
        {job && <Button variant="outline" disabled={busy} onClick={() => { setJob(null); move(0); setSource(null); setTitle(""); setError(null); uploadId.current = null; setPrompt(DEFAULT_PROMPT); setScene(""); setSelectedDraft(null); }}><Plus size={16} /> New</Button>}
      </div>
    </header>
    {historyOpen && <section className={styles.history} aria-label="Motion projects"><div ref={historyWrapper} className={styles.historyScroll}><div ref={historyContent}>
      {!jobs.length ? <p className={styles.empty}>No motion projects yet.</p> : jobs.map(item => <button key={item.id} className={styles.historyRow} onClick={() => choose(item)}><Film size={18} /><span><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString()} &middot; {item.seconds.toFixed(1)}s</small></span><span className={styles.status}>{item.status}</span><ArrowRight size={16} /></button>)}
    </div></div></section>}
    <nav className={styles.stages} aria-label="Production stages">{STAGES.map((label, index) => <button key={label} aria-current={stage === index ? "step" : undefined} disabled={index > 0 && !job || index === 2 && !job?.approved || index === 3 && !draft} onClick={() => move(index)}><span className={styles.stageNumber}>{index < stage ? <Check size={14} /> : index + 1}</span>{label}</button>)}</nav>
    {error && <div role="alert" className={styles.error}>{error}</div>}
    {job?.error && <div role="status" className={styles.error}>{job.error}</div>}
    {loading ? <div className={styles.loading}><Loader2 className="animate-spin" /> Loading Motion Studio</div> : <StudioReveal scene={`${stage}-${job?.id || "new"}`}><div className={styles.workspace}>
      <section className={styles.controls} aria-label={`${STAGES[stage]} controls`}>
        {stage === 0 && <>
          <h2>Source footage</h2>
          <label className={styles.drop}><Upload size={25} /><strong>{source?.name || "Choose a source video"}</strong><span>MP4 or MOV &middot; up to 200 MB</span><input aria-label="Source video" type="file" accept="video/mp4,video/quicktime,.mp4,.mov" disabled={busy} onChange={e => { setSource(e.target.files?.[0] || null); uploadId.current = null; }} /></label>
          <label className={styles.field}>Project name<input value={title} maxLength={120} onChange={e => { setTitle(e.target.value); uploadId.current = null; }} placeholder="Untitled motion project" /></label>
          <div className={styles.pair}><label className={styles.field}>Start time (s)<input type="number" min={0} max={86400} step={0.1} value={start} onChange={e => { setStart(Number(e.target.value)); uploadId.current = null; }} /></label><label className={styles.field}>Clip length (s)<input type="number" min={2} max={30} step={0.1} value={seconds} onChange={e => { setSeconds(Number(e.target.value)); uploadId.current = null; }} /></label></div>
          <Button disabled={!source || busy || !status?.local_ready || seconds < 2 || seconds > 30 || start < 0} onClick={() => run(upload)}>{busy ? <Loader2 className="animate-spin" size={16} /> : <Clapperboard size={16} />} Prepare clip</Button>
          {status && !status.local_ready && <p className={styles.notice}>FFmpeg and FFprobe are required for preparation.</p>}
        </>}
        {stage === 1 && <>
          <h2>Review the source</h2>
          <dl className={styles.details}><div><dt>Project</dt><dd>{job?.title}</dd></div><div><dt>Duration</dt><dd>{job?.seconds.toFixed(1)} seconds</dd></div><div><dt>Soundtrack</dt><dd>{job?.media.has_audio ? "Original audio retained" : "Silent source"}</dd></div><div><dt>Preparation</dt><dd>{prepared ? "Ready for review" : job?.status}</dd></div></dl>
          <label className={styles.checkbox}><input type="checkbox" checked={job?.approved || watched} disabled={!watched || job?.approved} onChange={e => setWatched(e.target.checked)} />Reviewed the full clip</label>
          <Button disabled={active || !prepared || !(watched || job?.approved)} onClick={() => run(async () => { if (job) { accept(await motionApi.approve(job.id)); move(2); } })}><CheckCircle2 size={16} /> Approve source</Button>
        </>}
        {stage === 2 && <>
          <h2>Cast your characters</h2>
          <div className={styles.characters}>{[1, 2].map(slot => <div className={styles.characterSlot} key={slot}><label className={styles.character}>
            {job?.characters.includes(slot) ? <img alt={`Character ${slot} reference`} src={`${motionApi.file(job.id, `character-${slot}.jpg`)}?v=${job.updated_at}`} /> : <ImagePlus size={26} />}
            <strong>Character {slot}</strong><span>{job?.characters.includes(slot) ? "Added" : slot === 2 ? "Optional" : "Required"}</span><span className={styles.referenceAction}><Upload size={13} /> {job?.characters.includes(slot) ? "Change image" : "Choose image"}</span><input type="file" accept="image/png,image/jpeg,image/webp" aria-label={`Character ${slot} reference`} disabled={active} onChange={e => { const file = e.target.files?.[0]; if (file && job) run(async () => accept(await motionApi.character(job.id, slot, file))); e.target.value = ""; }} />
          </label>{job?.characters.includes(slot) && <Button className={styles.removeCharacter} variant="outline" size="icon" title={`Remove character ${slot}`} aria-label={`Remove character ${slot}`} disabled={active} onClick={() => run(async () => accept(await motionApi.removeCharacter(job.id, slot)))}><X size={14} /></Button>}</div>)}</div>
          <label className={styles.field}>Replacement direction<textarea rows={5} value={prompt} maxLength={6000} onChange={e => setPrompt(e.target.value)} disabled={active} /></label>
          <label className={styles.field}>Scene details<textarea rows={2} value={scene} maxLength={2000} placeholder="Lighting, room, colors or background details" onChange={e => setScene(e.target.value)} disabled={active} /></label>
          {!status?.cloud_ready && <p className={styles.notice}><Link href="/admin/integrations">Configure fal in Provider Integrations</Link></p>}
          <label className={styles.checkbox}><input type="checkbox" checked={charges} disabled={active} onChange={e => setCharges(e.target.checked)} />Approve provider charges and upload these inputs to fal</label>
          <Button disabled={active || !charges || !status?.cloud_ready || !job?.characters.includes(1)} onClick={() => run(() => render("draft"))}><Clapperboard size={16} /> {drafts.length ? "Generate another draft" : "Generate 480p draft"}</Button>
          {!!drafts.length && <Button variant="outline" disabled={active} onClick={() => move(3)}>Review and export <ArrowRight size={16} /></Button>}
        </>}
        {stage === 3 && <>
          <h2>Approve the final cut</h2>
          <label className={styles.field}>Selected draft<select value={draft?.id || ""} disabled={active} onChange={e => { setSelectedDraft(e.target.value); setDraftWatched(false); setCharges(false); }}>{drafts.map((item, i) => <option key={item.id} value={item.id}>Draft {i + 1} &middot; {new Date(item.created_at).toLocaleTimeString()}</option>)}</select></label>
          <dl className={styles.details}><div><dt>Final resolution</dt><dd>1080p</dd></div><div><dt>Source task</dt><dd>{draft?.draft_id ? "Original draft preserved" : "Draft ID unavailable"}</dd></div><div><dt>Valid until</dt><dd>{draft?.expires_at ? new Date(draft.expires_at).toLocaleString() : "Unavailable"}</dd></div></dl>
          {expired && <p className={styles.notice}>This draft expired. Return to Draft to generate another.</p>}
          {!job?.final_file && <><label className={styles.checkbox}><input type="checkbox" checked={draftWatched} disabled={!draftWatched} onChange={e => setDraftWatched(e.target.checked)} />Reviewed the full draft</label><label className={styles.checkbox}><input type="checkbox" checked={charges} disabled={active} onChange={e => setCharges(e.target.checked)} />Approve provider charges for the 1080p render</label><Button disabled={active || !draftWatched || !charges || !draft?.draft_id || expired || !status?.cloud_ready} onClick={() => run(() => render("final"))}><CheckCircle2 size={16} /> Approve and render 1080p</Button></>}
          {job?.final_file && <a className={styles.download} href={motionApi.file(job.id, job.final_file)} download><Download size={17} /> Download final video</a>}
          {draft?.file && job && <a className={styles.secondaryDownload} href={motionApi.file(job.id, draft.file)} download><Download size={15} /> Download selected draft</a>}
        </>}
      </section>
      <section className={styles.preview} aria-label="Video preview">
        <div className={styles.previewHeader}><strong>{stage === 0 ? "Preview" : stage === 1 ? "Prepared source" : stage === 2 ? draft ? "Draft preview" : "Source reference" : job?.final_file ? "Final video" : "Selected draft"}</strong>{job && <span className={styles.status}>{job.status}</span>}</div>
        <div className={styles.player}>
          {fileUrl ? <video key={fileUrl} src={fileUrl} controls playsInline preload="metadata" onEnded={() => { if (stage === 1) setWatched(true); if (stage === 3) setDraftWatched(true); }} /> : <div className={styles.playerEmpty}><Film size={40} /><span>{active ? "Preparing your next preview" : "No clip selected"}</span>{active && <Loader2 size={22} className="animate-spin" />}</div>}
        </div>
        <div className={styles.previewFooter}><span><Volume2 size={15} /> {job?.media.has_audio ? "Original soundtrack" : job ? "Silent source" : "Source audio preserved"}</span>{job && <Button size="icon" variant="ghost" title="Refresh project" aria-label="Refresh project" disabled={busy} onClick={() => run(async () => accept(await motionApi.refresh(job.id)))}><RefreshCw size={16} /></Button>}</div>
        {job && job.operations.length > 0 && <div className={styles.runs}><h3>Render history</h3>{job.operations.slice().reverse().map((op, i) => <div key={op.id} className={styles.run}><span>{op.kind === "draft" ? "480p draft" : "1080p final"}</span><span>{op.status}</span>{op.file ? <a aria-label={`Download ${op.kind} ${i + 1}`} title="Download video" href={motionApi.file(job.id, op.file)} download><Download size={15} /></a> : <span />}{op.error && <small>{op.error}</small>}</div>)}</div>}
      </section>
    </div></StudioReveal>}
  </div>;
}
