from pathlib import Path
from PIL import Image
import numpy as np,base64
REPO=Path(__file__).resolve().parents[1]
p=REPO/'docs/assets/moped-source.png';im=Image.open(p).convert('RGBA')
rows=[(0,230,[0,212,380,567,781,1014,1267,1545,1810,2048]),(230,470,[0,303,520,803,1108,1427,1729,2048]),(470,682,[0,287,550,777,1014,1211,1380,1604,2048])]
poses=[]
for row,(top,bottom,cuts) in enumerate(rows):
 for i in range(len(cuts)-1):
  a=np.asarray(im.crop((cuts[i],top,cuts[i+1],bottom)))[:,:,3];ys,xs=np.where(a>120);x0=int(xs.min());y0=int(ys.min());x1=int(xs.max())+1;y1=int(ys.max())+1
  anchor=float(np.median(np.where(a[y0:y0+30]>150)[1]))-x0 if row==0 else (x1-x0)/2
  target=(280 if row==0 else 240)-anchor
  poses.append((cuts[i]+x0,top+y0,x1-x0,y1-y0,round(target)-(cuts[i]+x0),230-(y1-y0)-(top+y0)))
svg=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="11520" height="240" viewBox="0 0 11520 240">','<!-- 9 driving frames followed by 15 one-shot crash/recovery frames. Original supplied pixels. -->','<defs><image id="sheet" width="2048" height="682" xlink:href="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()+'"/>']
for i,(x,y,w,h,dx,dy) in enumerate(poses):svg.append(f'<clipPath id="pose-{i}" clipPathUnits="userSpaceOnUse"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath>')
svg.append('</defs>')
for i,(x,y,w,h,dx,dy) in enumerate(poses):svg.append(f'<svg x="{i*480}" y="0" width="480" height="240" viewBox="0 0 480 240" overflow="hidden"><g transform="translate({dx} {dy})"><use xlink:href="#sheet" clip-path="url(#pose-{i})"/></g></svg>')
svg.append('</svg>');(REPO/'app/static/loading-runner.svg').write_text('\n'.join(svg))
times=[180,140,140,170,170,350,450,450,240,240,240,240,240,220,550];total=sum(times);elapsed=0;keyframes=[]
for i,duration in enumerate(times):
 keyframes.append(f'{elapsed/total*100:.4f}%{{background-position:-{(9+i)*120}px 0}}');elapsed+=duration
keyframes.append('100%{background-position:-2760px 0}')
css=REPO/'app/static/simple-ui.css';s=css.read_text();s=s.replace('width:80px;height:72px','width:120px;height:60px').replace('/2080px 72px','/2880px 60px').replace('.99s steps(22,end)','1.26s steps(9,end)').replace('to{background-position:-1760px 0}','to{background-position:-1080px 0}').replace('.6s steps(3,end) forwards','4.02s steps(1,end) forwards')
import re
s=re.sub(r'@keyframes bibo-runner-finish\{from\{[^}]*\}to\{[^}]*\}\}', '@keyframes bibo-runner-finish{'+''.join(keyframes)+'}',s);css.write_text(s)
print('Moped loader: 24 frames; driving 1260ms, completion 4020ms')
