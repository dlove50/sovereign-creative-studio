"use client";
import {useEffect, useRef, useState} from "react";
import {performancesApi, type Performance, type Performer, type JointEdit} from "@/lib/api/performances";
import {Button} from "@/components/ui/button";
const joints = ["head", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"];
const links = [[0,1],[1,2],[2,3],[3,4],[1,5],[5,6],[6,7],[1,8],[8,9],[9,10],[1,11],[11,12],[12,13]];
export function ReferenceMotionEditor({id, performer: p, disabled, onUpdate}: {id:string; performer:Performer; disabled:boolean; onUpdate:(p:Performance)=>void}) {
  const [time,setTime]=useState(0),[joint,setJoint]=useState("left_wrist"),[dx,setDx]=useState(0),[dy,setDy]=useState(0);
  const [error,setError]=useState(""),[working,setWorking]=useState(false),[pose,setPose]=useState<Awaited<ReturnType<typeof performancesApi.referencePose>>|null>(null);
  const file=useRef<HTMLInputElement>(null);
  async function run(action:()=>Promise<Performance>) {setWorking(true);setError("");try{onUpdate(await action());setPose(null);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setWorking(false);}}
  useEffect(()=>{
    if(p.reference_pending?.status!=="processing")return;
    const timer=setInterval(()=>void performancesApi.get(id).then(onUpdate).catch(()=>{}),2000);
    return()=>clearInterval(timer);
  },[id,p.reference_pending?.status,onUpdate]);
  async function preview(){setError("");try{setPose(await performancesApi.referencePose(id,p.id,time));}catch(e){setError(String(e));}}
  function save(){
    const edits:JointEdit[]=structuredClone(p.reference?.edits??[]);let track=edits.find(x=>x.joint===joint);
    if(!track){track={joint,keyframes:[]};edits.push(track);}
    track.keyframes=track.keyframes.filter(k=>Math.abs(k.time-time)>.0001);
    track.keyframes.push({time,dx:dx/100,dy:dy/100});track.keyframes.sort((a,b)=>a.time-b.time);
    void run(()=>performancesApi.referenceEdits(id,p.id,edits));
  }
  const blocked=disabled||working||p.reference_pending?.status==="processing";
  return <details className="text-xs text-muted-foreground"><summary className="cursor-pointer py-1">Reference motion & joint tracks</summary>
    <div className="space-y-2 pt-2">
      <p>Upload one clearly visible performer covering the whole song. Body motion follows this video; facial articulation keeps {p.name}’s own vocal guide.</p>
      <input ref={file} type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" className="hidden" onChange={e=>{const f=e.target.files?.[0];if(f)void run(()=>performancesApi.uploadReference(id,p.id,f));e.target.value="";}}/>
      <Button size="sm" variant="outline" disabled={blocked} onClick={()=>file.current?.click()}>Upload motion reference</Button>
      {p.reference_pending?.status==="processing"?<p role="status">Measuring body and hands on CPU…</p>:null}
      {p.reference_pending?.error?<p role="alert" className="text-red-400">{p.reference_pending.error}</p>:null}
      {p.reference?<>
        <p>Reference ready · {p.reference.duration.toFixed(2)}s · {p.reference.edits.reduce((n,t)=>n+t.keyframes.length,0)} keyframes</p>
        <details><summary className="cursor-pointer">Saved joint keyframes</summary><ul className="max-h-40 space-y-1 overflow-auto pt-1">{p.reference.edits.flatMap(track=>track.keyframes.map(key=><li key={`${track.joint}-${key.time}`} className="flex flex-wrap items-center gap-2"><button type="button" className="text-left underline" disabled={blocked} onClick={()=>{setJoint(track.joint);setTime(key.time);setDx(key.dx*100);setDy(key.dy*100);}}>{track.joint.replaceAll("_"," ")} · {key.time.toFixed(2)}s · {(key.dx*100).toFixed(0)}%, {(key.dy*100).toFixed(0)}%</button><button type="button" className="text-red-400 underline" disabled={blocked} aria-label={`Remove ${track.joint} keyframe at ${key.time} seconds`} onClick={()=>void run(()=>performancesApi.referenceEdits(id,p.id,p.reference!.edits.map(t=>t.joint===track.joint?{...t,keyframes:t.keyframes.filter(k=>k.time!==key.time)}:t).filter(t=>t.keyframes.length>0)))}>Remove</button></li>))}</ul></details>
        <div className="grid grid-cols-2 gap-2">
          <label>Time (seconds)<input aria-label={`${p.name} reference time`} className="w-full rounded border bg-background p-1" type="number" min={0} max={Math.max(0,p.reference.duration-.04)} step={.04} value={time} onChange={e=>setTime(+e.target.value)}/></label>
          <label>Joint<select aria-label={`${p.name} reference joint`} className="w-full rounded border bg-background p-1" value={joint} onChange={e=>setJoint(e.target.value)}>{joints.map(j=><option key={j} value={j}>{j.replaceAll("_"," ")}</option>)}</select></label>
          <label>Horizontal offset (%)<input aria-label={`${p.name} joint horizontal offset`} className="w-full rounded border bg-background p-1" type="number" min={-25} max={25} step={1} value={dx} onChange={e=>setDx(+e.target.value)}/></label>
          <label>Vertical offset (%)<input aria-label={`${p.name} joint vertical offset`} className="w-full rounded border bg-background p-1" type="number" min={-25} max={25} step={1} value={dy} onChange={e=>setDy(+e.target.value)}/></label>
        </div>
        <div className="flex flex-wrap gap-2"><Button size="sm" disabled={blocked} onClick={save}>Save joint keyframe</Button><Button size="sm" variant="outline" disabled={blocked} onClick={()=>void preview()}>Preview measured pose</Button><Button size="sm" variant="outline" disabled={blocked} onClick={()=>void run(()=>performancesApi.referenceEdits(id,p.id,[]))}>Clear keyframes</Button><Button size="sm" variant="outline" disabled={blocked} onClick={()=>void run(()=>performancesApi.detachReference(id,p.id))}>Detach reference</Button></div>
        {pose?<svg role="img" aria-label={`${p.name} edited reference pose`} viewBox={`0 0 ${pose.width} ${pose.height}`} className="w-full rounded bg-slate-950">{links.map(([a,b])=>pose.frame.scores[a]>.3&&pose.frame.scores[b]>.3?<line key={`${a}-${b}`} x1={pose.frame.keypoints[a][0]} y1={pose.frame.keypoints[a][1]} x2={pose.frame.keypoints[b][0]} y2={pose.frame.keypoints[b][1]} stroke="#c084fc" strokeWidth={4}/>:null)}{pose.frame.keypoints.map((k,i)=>(i<24||i>=92)&&pose.frame.scores[i]>.3?<circle key={i} cx={k[0]} cy={k[1]} r={3} fill="#5eead4"/>:null)}</svg>:null}
        <p>Offsets interpolate between keyframes; add zero-offset keys where movement should return. Wrist edits move the finger chain. Rendered motion is generative and must be reviewed.</p>
      </>:null}
      {error?<p role="alert" className="text-red-400">{error}</p>:null}
    </div></details>;
}
