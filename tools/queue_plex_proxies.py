"""Create verified editing copies of imported videos on the Plex B580."""
import json, subprocess, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEST = Path.home() / 'Downloads/Sovereign/Videos/Editing Proxies'
STATE = ROOT / 'work/plex-proxies.json'
HOST = 'Plex@192.168.2.170'
OPTIONS = ['-i',str(Path.home()/'.ssh/sovereign_plex_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8']
def run(args, timeout=1800):
    return subprocess.run(args,check=True,capture_output=True,timeout=timeout)
def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]).stdout)
def main():
    DEST.mkdir(parents=True,exist_ok=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    for source in sorted((ROOT/'backend/storage/imports').glob('*/video.*')):
        key=source.parent.name
        if state.get(key,{}).get('status')=='completed': continue
        original=probe(source)
        job=uuid.uuid4().hex
        remote='C:/Users/Plex/SovereignWorker/jobs/'+job
        state[key]={'status':'uploading','job_id':job,'source':str(source)}
        STATE.write_text(json.dumps(state,indent=2))
        run(['ssh',*OPTIONS,HOST,'powershell -NoProfile -Command "New-Item -ItemType Directory -Force '+remote+' | Out-Null"'])
        run(['scp',*OPTIONS,str(source),HOST+':'+remote+'/source.mp4'])
        while True:
            state[key]['status']='encoding'; STATE.write_text(json.dumps(state,indent=2))
            result=subprocess.run(['ssh',*OPTIONS,HOST,'powershell -NoProfile -File C:/Users/Plex/SovereignWorker/proxy-worker.ps1 -JobId '+job],capture_output=True,timeout=1800)
            if result.returncode==75:
                state[key]['status']='waiting_for_plex'; STATE.write_text(json.dumps(state,indent=2)); time.sleep(30); continue
            if result.returncode:
                state[key]['status']='failed'; state[key]['error']=result.stderr.decode(errors='replace')[-1500:]; STATE.write_text(json.dumps(state,indent=2)); raise RuntimeError(state[key]['error'])
            break
        out=DEST/(key+'-editing.mp4'); temp=out.with_suffix('.partial.mp4')
        run(['scp',*OPTIONS,HOST+':'+remote+'/result.mp4',str(temp)])
        actual=probe(temp)
        if abs(float(original['format']['duration'])-float(actual['format']['duration']))>0.5: raise ValueError('Duration mismatch')
        run(['ffmpeg','-v','error','-xerror','-i',str(temp),'-f','null','-'])
        temp.replace(out)
        state[key].update(status='completed',output=str(out),bytes=out.stat().st_size)
        STATE.write_text(json.dumps(state,indent=2))
        print('Completed',key,flush=True)
    print('All imported video editing copies completed',flush=True)
if __name__=='__main__': main()
