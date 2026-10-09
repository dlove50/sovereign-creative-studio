"use client";
import { useState } from "react";
import { assetUrl } from "@/lib/api";
import type { InteractiveNode } from "@/lib/api/admin";
import { recordFirstAnswer } from "@/lib/training-score";
export function TrainingPlayer({nodes,startId}:{nodes:InteractiveNode[];startId:string|null}){
 const [current,setCurrent]=useState(startId);const [ended,setEnded]=useState(false);const [broken,setBroken]=useState(false);
 const [choice,setChoice]=useState<InteractiveNode["choices"][number]|null>(null);const [answers,setAnswers]=useState<Record<string,boolean>>({});
 const node=nodes.find(n=>n.id===current);const total=nodes.filter(n=>n.question?.trim()).length;
 function go(id:string){setCurrent(id);setEnded(false);setBroken(false);setChoice(null);}
 function reset(){setAnswers({});go(startId||nodes[0]?.id||"");}
 if(!node)return <p>Add a starting clip or text step to preview.</p>;
 const unlocked=ended||broken||!node.video_url;const finished=unlocked&&!node.choices.length;
 function pick(c:InteractiveNode["choices"][number]){if(node?.question?.trim())setAnswers(a=>recordFirstAnswer(a,node.id,c.is_correct===true));if(c.feedback||node?.question?.trim())setChoice(c);else go(c.next);}
 return <div className="mx-auto max-w-2xl space-y-4"><h2 className="text-xl font-semibold">{node.title||"Training step"}</h2>
  {node.body&&<p className="whitespace-pre-wrap">{node.body}</p>}
  {node.video_url&&!broken&&<video key={node.id} src={assetUrl(node.video_url)!} controls onEnded={()=>setEnded(true)} onError={()=>setBroken(true)} className="max-h-[420px] w-full rounded-xl bg-black"/>}
  {broken&&<p role="alert">This video could not play. You can still read the question and continue below.</p>}
  {unlocked&&<section className="space-y-3 rounded-xl border border-border p-5">
   {finished?<><h3 className="text-lg font-semibold">You reached the end</h3>{total>0&&<p>{Object.values(answers).filter(Boolean).length} correct on first attempt · {Object.keys(answers).length} answered · {total} questions in this training. Branches may skip questions.</p>}</>:<h3 className="text-lg font-semibold">{node.question||"What happens next?"}</h3>}
   {choice?<div className="space-y-3" aria-live="polite"><p className="font-semibold">{node.question?(choice.is_correct?"Correct":"Not correct yet"):"Your choice"}</p>{choice.feedback&&<p>{choice.feedback}</p>}<button onClick={()=>go(choice.next)} className="rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground">Continue</button></div>:node.choices.map((c,i)=><button key={i} onClick={()=>pick(c)} className="block w-full rounded-lg border border-border bg-background px-4 py-3 text-left text-foreground hover:bg-raised focus-visible:ring-2 focus-visible:ring-primary">{c.label}</button>)}
  </section>}
  <p className="text-sm text-muted-foreground">Preview session only. Answers are not saved or reported to a learning system.</p><button onClick={reset} className="rounded-lg border border-border px-4 py-2">Start over</button>
 </div>;
}
