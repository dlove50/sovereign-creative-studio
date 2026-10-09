"""Resumable Linux talking-preview batch. Persist prompt IDs before polling."""
import sys,json,time,subprocess
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import avatar_comfyui as talk
from app.services.avatar_presets import PRESETS
STATE=ROOT/'work/hover-previews.json'
def main():
 state=json.loads(STATE.read_text()) if STATE.exists() else {}
 catalog=json.loads((ROOT/'frontend/src/lib/public-avatars.generated.json').read_text())
 wf_path=ROOT/'backend/workflows/avatar_wan_infinite_talk.json'
 wf=talk._sanitize(json.loads(wf_path.read_text()),wf_path)
 outdir=ROOT/'frontend/public/sovereign-ui/public-avatars/previews';outdir.mkdir(exist_ok=True)
 with httpx.Client(base_url='http://127.0.0.1:18001',timeout=90,trust_env=False) as client:
  for slug,row in catalog.items():
   e=state.setdefault(slug,{})
   if e.get('status')=='completed':continue
   if e.get('status') in ['failed','submission-unknown']:raise RuntimeError('Inspect unresolved '+slug)
   if not e.get('prompt_id'):
    q=client.get('/queue').json()
    while q['queue_running'] or q['queue_pending']:
     time.sleep(10);q=client.get('/queue').json()
    def upload(path,field):
     with path.open('rb') as f:
      r=client.post('/upload/image',files={'image':(path.name,f)},data={'type':'input'});r.raise_for_status();return r.json()['name']
    image=upload(ROOT/'frontend/public'/row['cover'].lstrip('/'),'image')
    audio=upload(ROOT/'work/avatar-preview-short.wav','audio')
    patched=talk._patch(wf,image,audio,'A friendly presenter speaking naturally, subtle head movement, consistent face',PRESETS['balanced'],length=61)
    e['status']='submission-unknown';STATE.write_text(json.dumps(state,indent=2))
    r=client.post('/prompt',json={'prompt':patched});r.raise_for_status()
    e.update(status='rendering',prompt_id=r.json()['prompt_id']);STATE.write_text(json.dumps(state,indent=2));print('Submitted',slug,e['prompt_id'],flush=True)
   while True:
    try:
     r=client.get('/history/'+e['prompt_id']);r.raise_for_status();h=r.json().get(e['prompt_id'])
    except httpx.TransportError:
     time.sleep(15);continue
    if h and h.get('status',{}).get('status_str')=='error':
     e['status']='failed';STATE.write_text(json.dumps(state,indent=2));raise RuntimeError('Workflow failed: '+slug)
    if h and h.get('status',{}).get('completed'):
     video=talk._find_video(h['outputs'])
     if not video:raise RuntimeError('No output video')
     r=client.get('/view',params={k:video.get(k,'') for k in ['filename','subfolder','type']});r.raise_for_status()
     out=outdir/(slug+'.mp4');out.write_bytes(r.content)
     subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(out),'-f','null','-'],check=True)
     e.update(status='completed',url='/sovereign-ui/public-avatars/previews/'+out.name);STATE.write_text(json.dumps(state,indent=2))
     (outdir/'catalog.json').write_text(json.dumps({k:v['url'] for k,v in state.items() if v.get('status')=='completed'}))
     print('Completed',slug,flush=True);break
    time.sleep(10)
if __name__=='__main__':main()
