import asyncio,json,time,sys,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'backend'))
from app.video_generators import get_video_generator
import httpx
P=R/'work/h3-ltx-comparison.json'
cases=[('presenter','image_to_video','A professional presenter turns slightly toward the camera, smiles naturally and gives one small open-handed gesture. Stable face, natural fingers, steady camera.'),('product','text_to_video','A glass perfume bottle on a dark stone pedestal. The camera makes a slow smooth arc around the bottle. Soft studio reflections, realistic glass, no text.'),('motion','text_to_video','A red toy car rolls smoothly from left to right across a wooden table and stops beside a blue ceramic cup. One continuous fixed camera shot, realistic lighting.')]
async def main():
 state=json.loads(P.read_text()) if P.exists() else {}
 def save():P.write_text(json.dumps(state,indent=2))
 for name,mode,prompt in cases:
  for provider in ['local_h3','local_ltx']:
   key=name+'-'+provider
   if key in state:
    if state[key]['status']=='completed':continue
    raise RuntimeError('Inspect existing job before retry: '+key)
   with httpx.Client(trust_env=False) as c:
    q=c.get('http://127.0.0.1:8001/queue').json()
    if q['queue_running'] or q['queue_pending']:raise RuntimeError('GPU busy; not submitting')
   g=get_video_generator(provider); submit=g._submit
   state[key]={'status':'preparing','prompt':prompt,'mode':mode,'duration_requested':3,'quality':'default H3 turbo / LTX image_to_video_best or best_local','resolution_note':'Configured practical local settings differ; compare output quality and time, not an equal-compute benchmark'};save()
   async def tracked(client,workflow):
    state[key]['status']='submission-unknown';save()
    pid=await submit(client,workflow);state[key].update(status='rendering',prompt_id=pid);save();print(key,pid,flush=True);return pid
   g._submit=tracked
   start=time.time()
   try:
    result=await g.generate(video_id='comparison-'+key,source_image_url='/storage/39115d45a84440739453a94888dfc23a.png',prompt=prompt,motion_preset='slow zoom',duration_seconds=3,mode=mode,quality_preset=None if provider=='local_h3' else ('image_to_video_best' if mode=='image_to_video' else 'best_local'))
    path=R/'backend'/result.result_url.lstrip('/')
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-f','null','-'],check=True,capture_output=True)
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
    state[key].update(status='completed',seconds=round(time.time()-start,2),output=str(path),metadata=info,visual_review='pending');save()
   except Exception as e:
    state[key].update(status='failed',error=str(e));save();raise
asyncio.run(main())
