"""Run one recoverable B580 extension assembly acceptance job; yield to Plex."""
import json, subprocess, time, uuid, hashlib, array, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'work/plex-extension-acceptance.json'
HOST='Plex@192.168.2.170'
OPTIONS=['-i',str(Path.home()/'.ssh/sovereign_plex_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
def run(args,timeout=1800):
    return subprocess.run(args,check=True,capture_output=True,timeout=timeout)
def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]).stdout)
def main():
    sources=[ROOT/'backend/storage/videos/workflow-repair-input.mp4',ROOT/'backend/storage/videos/repair-video_extension.mp4']
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sources]
    state=json.loads(STATE.read_text()) if STATE.exists() else {'job_id':uuid.uuid4().hex,'status':'prepared','sources':[str(p) for p in sources],'sha256':hashes}
    if state['sha256']!=hashes: raise RuntimeError('Inputs changed: review existing job first')
    if state['status']=='completed': print('Already completed',state['output']); return
    def save(status,**kwargs):
        if status=='completed': state.pop('error',None)
        state.update(status=status,**kwargs); STATE.parent.mkdir(exist_ok=True); STATE.write_text(json.dumps(state,indent=2)); print(status,flush=True)
    save('staging')
    job=state['job_id']; remote='C:/Users/Plex/SovereignWorker/jobs/'+job
    probes=[probe(p) for p in sources]; video=next(s for s in probes[0]['streams'] if s['codec_type']=='video')
    request={'width':video['width'],'height':video['height'],'fps':video['avg_frame_rate'],'clips':[{'duration':float(p['format']['duration']),'has_audio':any(s['codec_type']=='audio' for s in p['streams'])} for p in probes]}
    request_path=ROOT/'work'/('plex-extension-'+job+'.json'); request_path.write_text(json.dumps(request))
    run(['ssh',*OPTIONS,HOST,'powershell -NoProfile -Command "New-Item -ItemType Directory -Force '+remote+' | Out-Null"'])
    run(['scp',*OPTIONS,str(ROOT/'tools/plex_extension_worker.ps1'),HOST+':C:/Users/Plex/SovereignWorker/extension-worker.ps1'])
    run(['scp',*OPTIONS,str(request_path),HOST+':'+remote+'/request.json'])
    for i,p in enumerate(sources): run(['scp',*OPTIONS,str(p),HOST+':'+remote+f'/clip-{i}.mp4'])
    while True:
        save('submitted',remote=remote)
        result=subprocess.run(['ssh',*OPTIONS,HOST,'powershell -NoProfile -File C:/Users/Plex/SovereignWorker/extension-worker.ps1 -JobId '+job],capture_output=True,timeout=1800)
        if result.returncode==75:
            save('waiting_for_plex_or_worker'); time.sleep(30); continue
        if result.returncode:
            save('failed',error=result.stderr.decode(errors='replace')[-2000:]); raise RuntimeError(state['error'])
        break
    dest=Path.home()/'Downloads/Sovereign/Videos/Verification'; dest.mkdir(parents=True,exist_ok=True)
    output=dest/('plex-extension-'+job+'.mp4')
    run(['scp',*OPTIONS,HOST+':'+remote+'/result.mp4',str(output)])
    log=ROOT/'work'/('plex-extension-'+job+'.log'); run(['scp',*OPTIONS,HOST+':'+remote+'/encode.log',str(log)])
    if 'Intel(R) Arc(TM) B580' not in log.read_text(errors='replace'): raise RuntimeError('Missing B580 evidence')
    actual=probe(output); expected=sum(p['duration'] for p in request['clips'])
    if abs(float(actual['format']['duration'])-expected)>.12: raise RuntimeError('Duration mismatch')
    if not any(s['codec_type']=='audio' for s in actual['streams']): raise RuntimeError('Missing audio')
    run(['ffmpeg','-v','error','-xerror','-i',str(output),'-f','null','-'])
    def audio_samples(path):
        samples=array.array('f'); samples.frombytes(run(['ffmpeg','-v','error','-i',str(path),'-t',str(request['clips'][0]['duration']),'-vn','-ac','1','-ar','16000','-f','f32le','-']).stdout); return samples
    source_audio=audio_samples(sources[0]); output_audio=audio_samples(output)
    n=min(len(source_audio),len(output_audio)); a=source_audio[:n]; b=output_audio[:n]
    denominator=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    correlation=sum(x*y for x,y in zip(a,b))/denominator if denominator else 0
    if correlation<.95: raise RuntimeError('Source audio correlation failed: '+str(correlation))
    save('completed',output=str(output),duration=float(actual['format']['duration']),expected_duration=expected,full_decode=True,source_audio_correlation=correlation,b580_log=str(log),note='Assembly acceptance only; generated motion continuity not certified')
    manifest=Path.home()/'Downloads/Sovereign/Manifests/plex-extension-acceptance.json'; manifest.parent.mkdir(parents=True,exist_ok=True); manifest.write_text(json.dumps(state,indent=2))
if __name__=='__main__': main()
