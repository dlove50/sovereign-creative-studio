"use client";
import { confirmDialog } from "@/components/ui/confirm-host";
import { useEffect, useState } from "react";
import Link from "next/link";
import { request } from "@/lib/api/core";
import { CinematicProduction } from "./cinematic-production";

type Shot = { id:string; duration_seconds:number; location_id:string; character_ids:string[]; description:string; camera:string; dialogue:{character_id:string;text:string}[]; narration:string; transition:string; image_prompt:string; video_prompt:string };
type Plan = { title:string; synopsis:string; characters:{id:string;name:string;description:string}[]; locations:{id:string;name:string;description:string}[]; shots:Shot[]; model:string };
type SavedPlan = { id:string; prompt:string; seconds:number; plan:Plan; revision:number; created_at:string; updated_at:string };
const field = "w-full rounded-lg border border-border bg-background px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
const button = "inline-flex items-center justify-center rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50";
function supportedDuration(seconds:number) { return [3,5,8,10].reduce((best,n)=>Math.abs(n-seconds)<Math.abs(best-seconds)?n:best,3); }

export function CinematicPlanner() {
 const [brief,setBrief]=useState(""); const [seconds,setSeconds]=useState(30);
 const [plan,setPlan]=useState<Plan|null>(null); const [busy,setBusy]=useState(false);
 const [error,setError]=useState(""); const [notice,setNotice]=useState("");
 const [saved,setSaved]=useState<SavedPlan[]>([]); const [record,setRecord]=useState<SavedPlan|null>(null);
 const [dirty,setDirty]=useState(false); const [saving,setSaving]=useState(false); const [selected,setSelected]=useState("");
 async function refresh(){try{setSaved(await request<SavedPlan[]>("/api/video-agent/plans"));}catch(e){setError(e instanceof Error?e.message:"Saved plans could not be loaded.");}}
 useEffect(()=>{void refresh();},[]);
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
 async function discard(){return !dirty||await confirmDialog("Discard the unsaved changes to this plan?");}
 async function load(){if(!selected||!await discard())return;setSaving(true);setError("");try{const r=await request<SavedPlan>(`/api/video-agent/plans/${selected}`);setRecord(r);setPlan(r.plan);setBrief(r.prompt);setSeconds(r.seconds);setDirty(false);setNotice("Saved plan loaded.");}catch(e){setError(e instanceof Error?e.message:"Could not load plan.");}finally{setSaving(false);}}
 async function savePlan(){if(!plan)return;setSaving(true);setError("");try{const r=await request<SavedPlan>(record?`/api/video-agent/plans/${record.id}`:"/api/video-agent/plans",{method:record?"PUT":"POST",body:JSON.stringify({prompt:brief,seconds:plan.shots.reduce((n,s)=>n+s.duration_seconds,0),plan,...(record?{revision:record.revision}:{})})});setRecord(r);setDirty(false);setSelected(r.id);setNotice("Plan and edited prompts saved to your account.");await refresh();}catch(e){setError(`${e instanceof Error?e.message:"Could not save plan."} Your edits remain here; download a copy before loading another version.`);}finally{setSaving(false);}}
 async function generate(e:React.FormEvent) { e.preventDefault();if(!await discard())return;setBusy(true);setError("");setNotice("");try {setPlan(await request<Plan>("/api/video-agent/plan",{method:"POST",body:JSON.stringify({prompt:brief,seconds})}));setRecord(null);setDirty(true);setSelected("");}catch(e){setError(e instanceof Error?e.message:"Planning failed. Try again.");}finally{setBusy(false);} }
 function edit(id:string,key:"image_prompt"|"video_prompt",value:string) {setDirty(true);setPlan(p=>p?{...p,shots:p.shots.map(s=>s.id===id?{...s,[key]:value}:s)}:p);}
 function download() {if(!plan)return;const url=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="sovereign-cinematic-plan.json";a.click();URL.revokeObjectURL(url);}
 async function copy() {try{await navigator.clipboard.writeText(JSON.stringify(plan,null,2));setNotice("Plan copied.");}catch{setError("Clipboard access unavailable. Use Download plan instead.");}}
 return <main className="mx-auto max-w-6xl space-y-8 p-5 md:p-8">
  <header><Link href="/video-agent" onClick={e=>{if(dirty){e.preventDefault();void discard().then(ok=>{if(ok)window.location.assign("/video-agent");});}}} className="text-sm text-primary underline underline-offset-4">Back to Video Agent</Link><h1 className="mt-4 text-3xl font-semibold text-foreground">Cinematic planner</h1><p className="mt-2 max-w-3xl text-foreground">Turn a story into characters, locations, dialogue and a shot plan. Review each prompt before opening it in Video Generator.</p></header>
  <section className="flex flex-wrap items-end gap-3" aria-label="Saved plans"><label className="min-w-48 flex-1 font-medium">Saved plans<select value={selected} onChange={e=>setSelected(e.target.value)} className={`${field} mt-2`}><option value="">Choose a saved plan</option>{saved.map(r=><option key={r.id} value={r.id}>{r.plan.title}</option>)}</select></label><button className={button} disabled={!selected||busy||saving} onClick={load}>Load plan</button><button className={button} disabled={busy||saving} onClick={refresh}>Refresh</button></section>
  <form onSubmit={generate} className="space-y-4 border-b border-border pb-7">
   <label className="block font-medium">Your story<textarea required minLength={3} maxLength={8000} rows={4} value={brief} disabled={busy||saving} onChange={e=>{setBrief(e.target.value);if(plan)setDirty(true);}} className={`${field} mt-2`} placeholder="Describe the characters, setting, action and mood…" /></label>
   <div className="flex flex-wrap items-end gap-4"><label className="font-medium">Total duration (seconds)<input type="number" min={10} max={180} required value={seconds} disabled={busy||saving} onChange={e=>setSeconds(Number(e.target.value))} className={`${field} mt-2 max-w-48`} /></label><button disabled={busy||saving} className={`${button} bg-primary text-primary-foreground`}>{busy?"Planning your scenes…":plan?"Create a new plan":"Create plan"}</button></div>
   <p className="text-sm text-muted-foreground">Planning creates text only. No video is rendered or purchased. Save your reviewed plan to keep it in your account.</p>
  </form>
  {busy&&<p role="status">The local planner is working. This can take several minutes.</p>}{error&&<p role="alert" className="text-destructive">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {plan&&<section className="space-y-7">
   <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-2xl font-semibold">{plan.title}</h2><p className="mt-2 max-w-3xl">{plan.synopsis}</p><p className="mt-2 text-sm text-muted-foreground">{plan.shots.length} shots · {plan.shots.reduce((n,s)=>n+s.duration_seconds,0)} seconds planned · {dirty?"Unsaved changes":"Saved"}</p></div><div className="flex flex-wrap gap-2"><button className={`${button} bg-primary text-primary-foreground`} disabled={saving||busy||!dirty} onClick={savePlan}>{saving?"Saving…":"Save plan"}</button><button className={button} onClick={copy}>Copy plan</button><button className={button} onClick={download}>Download plan</button></div></div>
   <div className="grid gap-6 md:grid-cols-2"><section><h3 className="mb-3 text-lg font-semibold">Characters</h3>{plan.characters.map(c=><p key={c.id} className="mb-3"><strong>{c.name}</strong> — {c.description}</p>)}{!plan.characters.length&&<p>No recurring characters.</p>}</section><section><h3 className="mb-3 text-lg font-semibold">Locations</h3>{plan.locations.map(l=><p key={l.id} className="mb-3"><strong>{l.name}</strong> — {l.description}</p>)}</section></div>
   <h3 className="text-xl font-semibold">Review the shots</h3>
   {plan.shots.map((s,i)=>{const duration=supportedDuration(s.duration_seconds);return <article key={s.id} className="space-y-4 border-t border-border pt-6">
    <h4 className="text-lg font-semibold">Shot {i+1} · {s.duration_seconds}s · {plan.locations.find(l=>l.id===s.location_id)?.name||s.location_id}</h4>
    <p>{s.description}</p><p><strong>Camera:</strong> {s.camera} <strong>Transition:</strong> {s.transition}</p>
    {s.dialogue.map((d,j)=><p key={j}><strong>{plan.characters.find(c=>c.id===d.character_id)?.name||d.character_id}:</strong> {d.text}</p>)}{s.narration&&<p><strong>Narration:</strong> {s.narration}</p>}
    <div className="grid gap-4 lg:grid-cols-2"><label className="font-medium">Image prompt<textarea disabled={busy||saving} rows={5} maxLength={4000} className={`${field} mt-2`} value={s.image_prompt} onChange={e=>edit(s.id,"image_prompt",e.target.value)} /></label><label className="font-medium">Video prompt<textarea disabled={busy||saving} rows={5} maxLength={4000} className={`${field} mt-2`} value={s.video_prompt} onChange={e=>edit(s.id,"video_prompt",e.target.value)} /></label></div>
    <div className="flex flex-wrap items-center gap-3"><Link target="_blank" rel="noopener noreferrer" className={button} href={`/create?prompt=${encodeURIComponent(s.image_prompt)}`}>Open shot {i+1} in Image Studio (new tab)</Link><Link target="_blank" rel="noopener noreferrer" className={button} href={`/videos?mode=text_to_video&prompt=${encodeURIComponent(s.video_prompt)}&duration=${duration}`}>Open shot {i+1} in Video Generator (new tab)</Link><span className="text-sm text-muted-foreground">{duration===s.duration_seconds?`${duration}s clip selected.`:`Generator opens at ${duration}s; this shot is planned for ${s.duration_seconds}s. Split longer shots or extend them separately.`} Review settings before generating.</span></div>
   </article>;})}
   {record&&<CinematicProduction key={`${record.id}:${record.revision}`} planId={record.id} revision={record.revision} shots={plan.shots} dirty={dirty}/>}
  </section>}
 </main>;
}
