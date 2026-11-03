"""Render real portal apertures to anonymous Discord-ready PNG attachments."""
from io import BytesIO
import math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from .game import clue_count

WIDTH,HEIGHT=1100,760
FONT_ROOT=Path('/usr/share/fonts/truetype/dejavu')


def font(size,bold=False):
    name='DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    try:return ImageFont.truetype(str(FONT_ROOT/name),size)
    except OSError:return ImageFont.load_default(size=size)


def corners(portal):
    center=portal['position'];right=portal['right'];up=portal['up']
    shape=portal.get('shape','rectangle')
    uv=[(math.cos(t*math.tau/32),math.sin(t*math.tau/32)) for t in range(32)] if shape=='circle' else [(-1,-1),(1,-1),(1,1),(-1,1)]
    return [[center[i]+right[i]*u*portal['width']/2+up[i]*v*portal['height']/2 for i in range(3)] for u,v in uv]


def project(point,mode):
    x,y,z=point
    if mode=='top':return x,-y
    return .82*x-.57*y,.30*x+.43*y-.85*z


def png(state,mode='iso'):
    if mode not in ('iso','top'):raise ValueError('Unknown clue projection')
    image=Image.new('RGB',(WIDTH,HEIGHT),'#0d141d');draw=ImageDraw.Draw(image,'RGBA')
    draw.rounded_rectangle((14,14,WIDTH-15,HEIGHT-15),radius=24,fill='#111d28',outline='#293d49',width=2)
    draw.text((48,37),'◈',font=font(35),fill='#77e8d2')
    draw.text((94,39),'PORTLE',font=font(31,True),fill='#e3f3f0')
    subtitle='DAILY '+state['puzzle']['day'] if state['mode']=='daily' else 'PRACTICE ROUND'
    draw.text((WIDTH-48,48),subtitle,font=font(15),fill='#92a6b4',anchor='ra')
    turn=min(6,len(state['attempts'])+1);count=clue_count(state);finished=state['status']!='playing'
    heading=state['puzzle']['map']['name'] if finished else 'Which arena is this?'
    draw.text((48,101),heading,font=font(28,True),fill='#edf6f4')
    detail=(('Solved' if state['status']=='won' else 'Answer revealed')+' · full portal layout') if finished else f'CLUE {turn} / 6  ·  {count} PORTAL'+('S' if count!=1 else '')+' REVEALED'
    draw.text((49,145),detail,font=font(14),fill='#81d6c5')
    box=(50,190,WIDTH-50,HEIGHT-92)
    for x in range(box[0],box[2],40):draw.line((x,box[1],x,box[3]),fill=(111,167,178,13))
    for y in range(box[1],box[3],40):draw.line((box[0],y,box[2],y),fill=(111,167,178,13))
    portals=state['puzzle']['map']['portals'];all_points=[project(c,mode) for p in portals for c in corners(p)]
    minx=min(p[0] for p in all_points);maxx=max(p[0] for p in all_points);miny=min(p[1] for p in all_points);maxy=max(p[1] for p in all_points)
    scale=min((box[2]-box[0]-90)/max(maxx-minx,1),(box[3]-box[1]-65)/max(maxy-miny,1))
    cx=(minx+maxx)/2;cy=(miny+maxy)/2
    def screen(point):
        x,y=project(point,mode);return ((box[0]+box[2])/2+(x-cx)*scale,(box[1]+box[3])/2+(y-cy)*scale)
    order=state['puzzle']['order'][:count]
    previous=0 if turn==1 or finished else (1,2,4,8,16)[min(turn-2,4)]
    shown=list(enumerate(order));shown.sort(key=lambda entry:sum(portals[entry[1]]['position'][:2]))
    for number,index in shown:
        portal=portals[index];polygon=[screen(c) for c in corners(portal)];color='#e8bc7b' if number>=previous and not finished else '#79e9d2'
        draw.polygon(polygon,fill=(105,226,201,42));draw.line(polygon+[polygon[0]],fill=color,width=3)
        center=screen(portal['position']);draw.ellipse((center[0]-3,center[1]-3,center[0]+3,center[1]+3),fill=color)
        if count<=16:
            draw.rounded_rectangle((center[0]+7,center[1]-12,center[0]+40,center[1]+12),radius=5,fill='#192d38',outline='#36515b')
            draw.text((center[0]+23,center[1]),str(number+1),font=font(12,True),fill='#deeee9',anchor='mm')
    draw.line((48,HEIGHT-70,WIDTH-48,HEIGHT-70),fill='#30404c')
    draw.text((49,HEIGHT-49),'PORTAL PLACEMENTS ONLY  /  '+('TOP VIEW' if mode=='top' else 'ISOMETRIC VIEW'),font=font(12),fill='#879da9')
    draw.text((WIDTH-48,HEIGHT-49),'SAME CLUE · DIFFERENT ANGLE' if mode=='top' else 'A MISS REVEALS MORE',font=font(12),fill='#879da9',anchor='ra')
    output=BytesIO();image.save(output,format='PNG',optimize=True);return output.getvalue()
