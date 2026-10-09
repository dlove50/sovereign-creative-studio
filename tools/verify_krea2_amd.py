"""One resumable AMD Krea2 acceptance image, no settings changes."""
import json,time,subprocess
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'work/krea2-amd-acceptance.json'
def save(s):
 t=STATE.with_suffix('.tmp');t.write_text(json.dumps(s,indent=2));t.replace(STATE)
def main():
 s=json.loads(STATE.read_text()) if STATE.exists() else {}
 if s.get('status')=='completed':print('Already completed');return
 if s.get('status') in ('failed','submission-unknown'):raise RuntimeError('Inspect unresolved prior submission')
 with httpx.Client(base_url='http://127.0.0.1:8001',timeout=90,trust_env=False) as c:
  if not s.get('prompt_id'):
   q=c.get('/queue').json()
   if q['queue_running'] or q['queue_pending']:raise RuntimeError('AMD busy; no submission')
   g=json.loads((ROOT/'backend/workflows/text_to_image_krea2_turbo.json').read_text())
   prompt='Realistic editorial vacation photograph of two adults, a 30-year-old woman wearing a blue bikini and a 30-year-old man wearing green swim shorts, standing together on a sunny tropical beach. Full body, natural relaxed poses, friendly smiles, clear ocean and pale sand, realistic anatomy and skin texture, natural midday sunlight, high-quality travel photography, nonsexual.'
   g['4']['inputs']['text']=prompt;g['7']['inputs']['seed']=1042026
   g['9']['inputs']['filename_prefix']='sovereign_krea2_amd_acceptance'
   s.update(status='submission-unknown',workflow=g,prompt=prompt);save(s)
   r=c.post('/prompt',json={'prompt':g});r.raise_for_status();s.update(status='rendering',prompt_id=r.json()['prompt_id']);save(s);print('Submitted',s['prompt_id'],flush=True)
  while True:
   r=c.get('/history/'+s['prompt_id']);r.raise_for_status();h=r.json().get(s['prompt_id'])
   if h and h.get('status',{}).get('status_str')=='error':s.update(status='failed',error=h['status']);save(s);raise RuntimeError('Krea failed; inspect state')
   if h and h.get('status',{}).get('completed'):
    img=next(v for o in h['outputs'].values() for v in o.get('images',[]) if v.get('type')=='output')
    r=c.get('/view',params={k:img.get(k,'') for k in ('filename','subfolder','type')});r.raise_for_status();out=ROOT/'work/krea2-amd-beachwear.png';out.write_bytes(r.content)
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(out),'-f','null','-'],check=True)
    s.update(status='completed',output=str(out),decode_verified=True,visual_review='pending');save(s);print('Completed',out,flush=True);return
   time.sleep(10)
if __name__=='__main__':main()
