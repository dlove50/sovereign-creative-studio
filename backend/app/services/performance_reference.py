"""Measured reference pose tracks, immutable preparation and native transfer graph."""
from __future__ import annotations
import bisect,copy,hashlib,json,math,os,subprocess,threading,uuid
from pathlib import Path
GROUPS={'head':[0,14,15,16,17],'left_shoulder':[5],'right_shoulder':[2],
        'left_elbow':[6],'right_elbow':[3],'left_wrist':[7,*range(92,113)],'right_wrist':[4,*range(113,134)]}
_CPU_REFERENCE_LOCK=threading.Lock()
_PREPARING=set()

def pending_status(performer):
    pending=performer.get("reference_pending")
    if pending and pending.get("status")=="processing" and pending.get("id") not in _PREPARING:
        return {**pending,"status":"error","error":"Reference preparation was interrupted. Upload it again; the previous ready reference is retained."}
    return pending
MODEL='wan2.2_animate_14B_int8_convrot.safetensors'
VISION='CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors'

def validate_edits(edits,duration):
    if not isinstance(edits,list) or len(edits)>32:raise ValueError('At most32 joint tracks are supported.')
    seen=set()
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)!={'joint','keyframes'}:raise ValueError('Each edit needs joint and keyframes.')
        joint=edit['joint'];keys=edit['keyframes']
        if joint not in GROUPS or joint in seen:raise ValueError('Unknown or duplicate joint.')
        seen.add(joint)
        if not isinstance(keys,list) or not 1<=len(keys)<=500:raise ValueError('Use1to500 keyframes per joint.')
        previous=-1
        for k in keys:
            if not isinstance(k,dict) or set(k)!={'time','dx','dy'}:raise ValueError('Keyframes need time, dx and dy.')
            if any(isinstance(k[a],bool) or not isinstance(k[a],(int,float)) or not math.isfinite(k[a]) for a in k):raise ValueError('Keyframes must contain finite numbers.')
            if not previous<k['time']<=duration or k['time']<0:raise ValueError('Keyframe times must increase within the reference.')
            if max(abs(k['dx']),abs(k['dy']))>.25:raise ValueError('Offsets must be within a quarter of the frame.')
            previous=k['time']
    return copy.deepcopy(edits)

def apply_edits(tracks,edits):
    edits=validate_edits(edits,tracks['frames'][-1]['time']);result=copy.deepcopy(tracks)
    for edit in edits:
        keys=edit['keyframes'];times=[k['time'] for k in keys]
        for row in result['frames']:
            i=bisect.bisect_right(times,row['time']);a=keys[max(0,i-1)];b=keys[min(len(keys)-1,i)]
            ratio=0 if a['time']==b['time'] else max(0,min(1,(row['time']-a['time'])/(b['time']-a['time'])))
            dx=(a['dx']+(b['dx']-a['dx'])*ratio)*tracks['width'];dy=(a['dy']+(b['dy']-a['dy'])*ratio)*tracks['height']
            for joint in GROUPS[edit['joint']]:row['keypoints'][joint][0]+=dx;row['keypoints'][joint][1]+=dy
    return result

def python():
    from .. import config
    return Path(os.getenv('PERFORMANCE_POSE_PYTHON',str(config.BASE_DIR/'.venv-pose'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))))

def worker(*args):
    with _CPU_REFERENCE_LOCK:
        result=subprocess.run([str(python()),str(Path(__file__).with_name('performance_pose_worker.py')),*map(str,args)],capture_output=True,text=True,timeout=7200)
    if result.returncode:raise ValueError('Reference preparation failed: '+result.stderr[-1200:])

def prepare(project_id,performer_id,source):
    from . import performance_engine as pe
    token=uuid.uuid4().hex[:12];project=pe.get(project_id);p=pe.performer(project,performer_id)
    _PREPARING.add(token)
    p['reference_pending']={'id':token,'status':'processing'};pe.save(project)
    def run():
        tracks=pe.media_dir(project_id)/f'reference-{token}.json'
        try:
            worker('extract',source,tracks);data=json.loads(tracks.read_text())
            project=pe.get(project_id)
            if project is None:return
            p=pe.performer(project,performer_id)
            if p.get('reference_pending',{}).get('id')!=token:return
            p['reference']={'id':token,'status':'ready','source':str(source),'tracks':str(tracks),'duration':len(data['frames'])/data['fps'],'edits':[]}
            p['reference_pending']=None;pe.save(project)
        except Exception as exc:
            project=pe.get(project_id)
            if project is None:return
            p=pe.performer(project,performer_id)
            if p.get('reference_pending',{}).get('id')==token:
                p['reference_pending']={'id':token,'status':'error','error':str(exc)[:1500]};pe.save(project)
        finally:
            _PREPARING.discard(token)
    threading.Thread(target=run,daemon=True,name='reference-'+token).start()
    return project

def transfer_key(base_key,reference):
    digest=hashlib.sha256(json.dumps({'version':1,'base':base_key,'model':MODEL,'steps':8,'size':[640,368],'edits':reference['edits']},sort_keys=True).encode())
    for name in ['source','tracks']:
        with Path(reference[name]).open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
    return digest.hexdigest()

def workflow(*,identity,pose,face,background,mask,audio,seed,length,previous=None):
    """Guides already include the five-frame overlap when previous is supplied."""
    w={}
    def n(k,cls,**inputs):w[str(k)]={'class_type':cls,'inputs':inputs}
    n(1,'UNETLoader',unet_name=MODEL,weight_dtype='default')
    n(2,'LoraLoaderModelOnly',model=['1',0],lora_name='lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors',strength_model=1)
    n(3,'CLIPLoader',clip_name='umt5_xxl_fp8_e4m3fn_scaled.safetensors',type='wan',device='default')
    n(4,'CLIPTextEncode',clip=['3',0],text='One adult performer, consistent reference identity and clothing, following supplied body and hand motion and separate facial performance. Plain uninterrupted dark navy backdrop, continuous smooth dark wall, clean empty background.')
    n(5,'CLIPTextEncode',clip=['3',0],text='low quality, distorted face, extra limbs, text, watermark')
    n(6,'VAELoader',vae_name='wan_2.1_vae.safetensors');n(7,'LoadImage',image=identity)
    n(8,'CLIPVisionLoader',clip_name=VISION);n(9,'CLIPVisionEncode',clip_vision=['8',0],image=['7',0],crop='none')
    for a,b,file in [(10,11,pose),(12,13,face),(21,22,background),(23,24,mask)]:
        n(a,'LoadVideo',file=file);n(b,'GetVideoComponents',video=[str(a),0])
    n(25,'ImageToMask',image=['24',0],channel='red')
    inputs=dict(positive=['4',0],negative=['5',0],vae=['6',0],width=640,height=368,length=length,batch_size=1,
                continue_motion_max_frames=5,video_frame_offset=5 if previous else 0,reference_image=['7',0],
                pose_video=['11',0],face_video=['13',0],clip_vision_output=['9',0],background_video=['22',0],character_mask=['25',0])
    if previous:
        n(26,'LoadVideo',file=previous);n(27,'GetVideoComponents',video=['26',0]);inputs['continue_motion']=['27',0]
    n(14,'WanAnimateToVideo',**inputs)
    n(15,'KSampler',model=['2',0],positive=['14',0],negative=['14',1],latent_image=['14',2],seed=seed,steps=8,cfg=1,sampler_name='euler',scheduler='simple',denoise=1)
    n(16,'TrimVideoLatent',samples=['15',0],trim_amount=['14',3]);n(17,'VAEDecode',samples=['16',0],vae=['6',0])
    images=['17',0]
    if previous:
        n(28,'ImageFromBatch',image=images,batch_index=['14',4],length=length-5);images=['28',0]
    n(18,'LoadAudio',audio=audio);n(19,'CreateVideo',images=images,audio=['18',0],fps=25)
    n(20,'SaveVideo',video=['19',0],filename_prefix='sovereign_reference',format='mp4',codec='h264')
    return w
