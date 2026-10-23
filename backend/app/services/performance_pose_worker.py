"""Isolated CPU-only measured pose preparation for reference motion.
Run from .venv-pose. Facial articulation is always a separate own-vocal guide.
"""
from __future__ import annotations
import os,json,sys,subprocess,math
from pathlib import Path
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import cv2,numpy as np,onnxruntime as ort
cv2.setNumThreads(2)
_original_session=ort.InferenceSession

def _cpu(*args,**kwargs):
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    kwargs.update(sess_options=opts,providers=['CPUExecutionProvider'])
    return _original_session(*args,**kwargs)
ort.InferenceSession=_cpu
from rtmlib import Wholebody,draw_skeleton
FPS=25;WIDTH=640;HEIGHT=368
GROUPS={'head':[0,14,15,16,17],'left_shoulder':[5],'right_shoulder':[2],
        'left_elbow':[6],'right_elbow':[3],'left_wrist':[7,*range(92,113)],'right_wrist':[4,*range(113,134)]}

def model():
    return Wholebody(mode='lightweight',to_openpose=True,backend='onnxruntime',device='cpu')

def one(detector,image):
    kp,sc=detector(image)
    if len(kp)!=1 or np.median(sc[0,:18])<.3:
        raise ValueError('Reference must show exactly one clearly visible performer.')
    return kp[0],sc[0]

def fit(image):
    h,w=image.shape[:2];scale=min(WIDTH/w,HEIGHT/h);nw,nh=round(w*scale),round(h*scale)
    canvas=np.zeros((HEIGHT,WIDTH,3),np.uint8);x=(WIDTH-nw)//2;y=(HEIGHT-nh)//2
    canvas[y:y+nh,x:x+nw]=cv2.resize(image,(nw,nh));return canvas

def encode(path):
    result=path.with_suffix('.mp4')
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-c:v','libx264','-threads','2','-crf','15','-pix_fmt','yuv420p',str(result)],check=True)
    path.unlink();return result

def extract(source,destination):
    det=model();cap=cv2.VideoCapture(str(source));rate=cap.get(cv2.CAP_PROP_FPS);count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(rate) or rate<=0 or not 0<count/rate<=900:
        raise ValueError('Reference must be a readable video up to15minutes.')
    rows=[];index=-1;frame=None
    try:
        for out_index in range(round(count/rate*FPS)):
            wanted=min(count-1,round(out_index/FPS*rate))
            while index<wanted:
                ok,frame=cap.read()
                if not ok:raise ValueError('Reference video is incomplete.')
                index+=1
            kp,sc=one(det,fit(frame));rows.append({'frame':out_index,'time':out_index/FPS,'keypoints':kp.tolist(),'scores':sc.tolist()})
    finally:cap.release()
    if len(rows)<13:raise ValueError('Reference must be at least half a second.')
    destination.write_text(json.dumps({'fps':FPS,'width':WIDTH,'height':HEIGHT,'frames':rows},separators=(',',':')))

def guide(tracks_path,edits_path,own_video,out):
    from performance_reference import apply_edits
    tracks=json.loads(tracks_path.read_text());tracks=apply_edits(tracks,json.loads(edits_path.read_text()))
    det=model();cap=cv2.VideoCapture(str(own_video));count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if len(tracks['frames'])<count:raise ValueError('Reference video is shorter than this performance. Upload a reference covering the whole timeline.')
    out.mkdir(exist_ok=True);writers={n:cv2.VideoWriter(str(out/(n+'.avi')),cv2.VideoWriter_fourcc(*'MJPG'),FPS,size) for n,size in [('pose',(WIDTH,HEIGHT)),('face',(256,256)),('background',(WIDTH,HEIGHT)),('mask',(WIDTH,HEIGHT))]}
    try:
        for i in range(count):
            ok,image=cap.read()
            if not ok:raise ValueError('Own vocal guide is incomplete.')
            kp,sc=one(det,image);face=kp[24:92][sc[24:92]>.3]
            if len(face)<10:raise ValueError('Own vocal face is not clear enough for transfer.')
            low,high=face.min(0),face.max(0);center=(low+high)/2;side=max(high-low)*1.6
            h,w=image.shape[:2];x0,y0=np.maximum(0,np.round(center-side/2)).astype(int);x1,y1=np.minimum([w,h],np.round(center+side/2)).astype(int)
            if x1<=x0 or y1<=y0:raise ValueError('Empty own-vocal facial crop.')
            writers['face'].write(cv2.resize(image[y0:y1,x0:x1],(256,256)))
            row=tracks['frames'][i];k=np.array(row['keypoints']);s=np.array([row['scores']]);s[:,24:92]=0
            writers['pose'].write(draw_skeleton(np.zeros((HEIGHT,WIDTH,3),np.uint8),k[None],s,openpose_skeleton=True,kpt_thr=.3))
            k=k.astype('int32');mask=np.zeros((HEIGHT,WIDTH),np.uint8);cv2.fillConvexPoly(mask,cv2.convexHull(k[[2,5,11,8]]),255)
            for a,b in [(1,0),(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(8,9),(9,10),(11,12),(12,13)]:cv2.line(mask,tuple(k[a]),tuple(k[b]),255,50)
            cv2.circle(mask,tuple(k[0]),85,255,-1)
            for wrist in [4,7]:cv2.circle(mask,tuple(k[wrist]),38,255,-1)
            mask=cv2.dilate(mask,np.ones((41,41),np.uint8));writers['mask'].write(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR))
            background=np.empty((HEIGHT,WIDTH,3),np.uint8);background[:]=[30,14,18];writers['background'].write(background)
    finally:
        cap.release()
        for writer in writers.values():writer.release()
    for name in writers:encode(out/(name+'.avi'))

if __name__=='__main__':
    if sys.argv[1]=='extract':extract(Path(sys.argv[2]),Path(sys.argv[3]))
    elif sys.argv[1]=='guide':guide(*map(Path,sys.argv[2:]))
    else:raise ValueError('Unknown pose worker operation.')
