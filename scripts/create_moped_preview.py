from PIL import Image,ImageDraw
from pathlib import Path
import numpy as np
REPO=Path(__file__).resolve().parents[1]
OUT=REPO.parent/'deliverables'/'moped-preview'
OUT.mkdir(parents=True,exist_ok=True)
im=Image.open(REPO/'docs/assets/moped-source.png').convert('RGBA')
rows=[(0,230,[0,212,380,567,781,1014,1267,1545,1810,2048]),(230,470,[0,303,520,803,1108,1427,1729,2048]),(470,682,[0,287,550,777,1014,1211,1380,1604,2048])]
phases=[]
for row,(top,bottom,cuts) in enumerate(rows):
 for i in range(len(cuts)-1):
  cell=im.crop((cuts[i],top,cuts[i+1],bottom));a=np.asarray(cell)[:,:,3];ys,xs=np.where(a>120);box=(int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1);sprite=cell.crop(box)
  canvas=Image.new('RGB',(600,330),'#0a101b');d=ImageDraw.Draw(canvas)
  d.text((18,16),'Moped-Vorschau: Fahren / Crash / Erholung',fill='#eef2ff')
  if row==0:
   xx=np.where(a[box[1]:box[1]+30]>150)[1];anchor=float(np.median(xx))-box[0]
   x=round(330-anchor)
  else:x=round(300-sprite.width/2)
  canvas.paste(sprite,(x,270-sprite.height),sprite);phases.append(canvas)
# Two driving loops demonstrate the repeating loader; the crash is a single ending.
frames=phases[:9]+phases[:9]+phases[9:]
times=[140]*18+[180,140,140,170,170,350,450]+[450,240,240,240,240,240,220,550]
p=OUT/'Moped-Fahrt-und-Crash.gif';frames[0].save(p,save_all=True,append_images=frames[1:],duration=times,loop=0,optimize=False,disposal=2)
with Image.open(p) as check:assert check.n_frames==len(frames)
sheet=Image.new('RGB',(1200,660),'#0a101b')
for j,i in enumerate((0,10,14,21)):sheet.paste(phases[i],((j%2)*600,(j//2)*330))
sheet.save(OUT/'phasen.png')
print(p)
