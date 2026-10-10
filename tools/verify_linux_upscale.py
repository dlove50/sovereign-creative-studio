"""One resumable, audio-preserving Linux upscale validation using installed models."""
import json
import subprocess
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'work/linux-upscale-verification.json'

def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2)); temp.replace(STATE)

def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state.get('status') == 'completed':
        print('Already completed'); return
    if state.get('status') in ('submission-unknown', 'failed', 'validation_failed'):
        raise RuntimeError('Inspect existing unresolved job before retry')
    with httpx.Client(base_url='http://127.0.0.1:18001', timeout=90, trust_env=False) as client:
        if not state.get('prompt_id'):
            queue = client.get('/queue').json()
            if queue['queue_running'] or queue['queue_pending']:
                print('Linux queue occupied; no submission'); return
            source = ROOT/'frontend/public/sovereign-ui/public-avatars/previews/nadia.mp4'
            with source.open('rb') as stream:
                r = client.post('/upload/image', files={'image': (source.name, stream)}, data={'type': 'input'})
                r.raise_for_status(); uploaded = r.json()['name']
            graph = json.loads((ROOT/'backend/workflows/video_upscale_ltx.json').read_text())
            graph['1'] = {'class_type': 'VAELoader', 'inputs': {'vae_name': 'ltx-2.3-full-vae.safetensors'}}
            graph['2']['inputs']['file'] = uploaded
            graph['4']['inputs']['vae'] = ['1', 0]
            graph['5']['inputs']['model_name'] = 'ltx-2.3-spatial-upscaler-x2-1.1.safetensors'
            graph['6']['inputs']['vae'] = ['1', 0]
            graph['7']['inputs']['vae'] = ['1', 0]
            # LTX VAE needs 8n+1 frames. Pad 61 to 65 before encoding,
            # then remove the four padding frames after decoding.
            graph['10'] = {'class_type':'ImageFromBatch','inputs':{'image':['3',0],'batch_index':-1,'length':1}}
            graph['11'] = {'class_type':'RepeatImageBatch','inputs':{'image':['10',0],'amount':4}}
            graph['12'] = {'class_type':'ImageBatch','inputs':{'image1':['3',0],'image2':['11',0]}}
            graph['4']['inputs']['pixels'] = ['12',0]
            graph['13'] = {'class_type':'ImageFromBatch','inputs':{'image':['7',0],'batch_index':0,'length':61}}
            graph['8']['inputs']['images'] = ['13',0]
            graph['8']['inputs']['audio'] = ['3', 1]
            graph['9']['inputs']['filename_prefix'] = 'sovereign_linux_upscale_verification'
            state.update(status='submission-unknown', source=str(source), workflow=graph)
            save(state)
            r = client.post('/prompt', json={'prompt': graph}); r.raise_for_status()
            state.update(status='rendering', prompt_id=r.json()['prompt_id']); save(state)
            print('Submitted', state['prompt_id'], flush=True)
        while True:
            r = client.get('/history/'+state['prompt_id']); r.raise_for_status()
            history = r.json().get(state['prompt_id'])
            if history and history.get('status', {}).get('status_str') == 'error':
                state.update(status='failed', error=history['status']); save(state)
                raise RuntimeError('Upscale failed; inspect persisted node error')
            if history and history.get('status', {}).get('completed'):
                videos = [v for output in history['outputs'].values() for key in ('videos','images','gifs') for v in output.get(key, []) if v.get('type') == 'output' and v['filename'].endswith('.mp4')]
                if not videos: raise RuntimeError('No output video')
                video = videos[0]
                r = client.get('/view', params={k:video.get(k,'') for k in ('filename','subfolder','type')});r.raise_for_status()
                output = ROOT/'work/linux-upscale-verified.mp4'; output.write_bytes(r.content)
                subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(output),'-f','null','-'], check=True)
                probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
                v = next(s for s in probe['streams'] if s['codec_type']=='video')
                problems = []
                if v['width']!=768 or v['height']!=768: problems.append('Unexpected upscale dimensions')
                if not any(s['codec_type']=='audio' for s in probe['streams']): problems.append('Audio missing')
                if int(v.get('nb_frames',0))!=61: problems.append('Frame count changed')
                if abs(float(probe['format']['duration'])-2.44)>0.04: problems.append('Duration changed')
                if problems:
                    state.update(status='validation_failed',output=str(output),probe=probe,validation_errors=problems);save(state)
                    raise RuntimeError('; '.join(problems))
                state.update(status='completed',output=str(output),probe=probe,decode_verified=True,visual_review='pending');save(state)
                print('Verified output',output,flush=True);return
            time.sleep(10)

if __name__=='__main__':main()
