"""Prototype: retain coloured hands missed by human segmentation on a KNOWN flat backdrop.
Only for native background-conditioned reference output, never arbitrary scenes.
Union with the human alpha preserves dark clothing; measured character envelope
bounds the colour fallback. Original accepted exports are not changed.
"""
import subprocess,sys,json
from pathlib import Path
import cv2,numpy as np
source,alpha,mask,target=map(Path,sys.argv[1:]);cv2.setNumThreads(2)
cap=cv2.VideoCapture(str(source));masks=cv2.VideoCapture(str(mask));width=int(cap.get(3));height=int(cap.get(4));fps=cap.get(5)
reader=subprocess.Popen(['ffmpeg','-v','error','-i',str(alpha),'-f','rawvideo','-pix_fmt','rgba','-'],stdout=subprocess.PIPE)
writer=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgba','-s',f'{width}x{height}','-r',str(fps),'-i','-','-an','-c:v','ffv1','-threads','2','-pix_fmt','bgra',str(target)],stdin=subprocess.PIPE)
count=0;added=[]
try:
 while True:
  ok,raw=cap.read()
  if not ok:break
  ok,m=masks.read();assert ok
  data=reader.stdout.read(width*height*4);assert len(data)==width*height*4
  rgba=np.frombuffer(data,np.uint8).reshape(height,width,4).copy();rgb=cv2.cvtColor(raw,cv2.COLOR_BGR2RGB).astype(float)
  border=np.concatenate([rgb[:8].reshape(-1,3),rgb[:,:8].reshape(-1,3),rgb[:,-8:].reshape(-1,3)])
  bg=np.median(border,axis=0);dist=np.linalg.norm(rgb-bg,axis=2)
  envelope=cv2.resize(m[:,:,0],(width,height)).astype(float)/255
  fallback=np.clip((dist-8)/12,0,1)*255*envelope;union=np.maximum(rgba[:,:,3],fallback).astype('uint8')
  newly_covered=(union>128)&(rgba[:,:,3]<128);added.append(int(newly_covered.sum()))
  rgba[newly_covered,:3]=rgb[newly_covered].astype('uint8');rgba[:,:,3]=union
  writer.stdin.write(rgba.tobytes());count+=1
 writer.stdin.close();assert reader.wait()==0 and writer.wait()==0
finally:
 cap.release();masks.release()
 for proc in [reader,writer]:
  if proc.poll() is None:proc.kill();proc.wait()
print(json.dumps({'frames':count,'newly_covered_pixels_per_frame':added,'scope':'Known flat background and measured envelope ONLY; inspect actual output.'}))
