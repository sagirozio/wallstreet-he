"""Generate light-theme overrides from the site's dark CSS (run once; output pasted into template.html)."""
import re, colorsys, sys
src=open('/home/claude/wallstreet-he/template.html',encoding='utf-8').read()
i=src.index('<style>',src.index('html.lponly')); j=src.index('</style>',i); css=src[i+7:j]
css=re.sub(r'/\*.*?\*/','',css,flags=re.S)
COL=re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)')
def parse(c):
    c=c.strip().lower()
    if c.startswith('#'):
        h=c[1:]
        if len(h) in (3,4): h=''.join(x*2 for x in h)
        r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16); a=int(h[6:8],16)/255 if len(h)==8 else 1
        return r,g,b,a
    n=[float(x) for x in re.findall(r'[\d.]+',c)]
    return int(n[0]),int(n[1]),int(n[2]),(n[3] if len(n)>3 else 1)
def fmt(r,g,b,a):
    r,g,b=[max(0,min(255,int(round(x)))) for x in (r,g,b)]
    return f'#{r:02x}{g:02x}{b:02x}' if a>=.999 else f'rgba({r},{g},{b},{round(a,3)})'
BGP=('background','background-color','box-shadow','fill','stop-color')
def conv(c,prop):
    r,g,b,a=parse(c); h,l,s=colorsys.rgb_to_hls(r/255,g/255,b/255)
    if a<1 and min(r,g,b)>235: return fmt(0,0,0,min(.9,a*1.25))          # white veil on dark -> dark veil on light
    if a<1 and max(r,g,b)<30:
        if prop.startswith('background') and a>.6: return fmt(255,255,255,a)   # near-opaque dark panel -> light panel
        return fmt(15,23,42,a*(.35 if 'shadow' in prop else .3))   # black shadow/scrim -> soft
    bgish=prop.startswith('background') or prop in ('fill','stop-color')
    if s<.22 or (l<.2 and bgish):                                           # neutrals: flip lightness
        if bgish: nl=1-l*.55 if l<.5 else l*.0+.12     # dark panels -> near white; white bg (rare) -> dark
        elif prop.startswith('border') or prop in ('outline','outline-color','stroke'): nl=.86-max(0,l-.12)*.35 if l<.5 else .35
        else: nl=max(.12,1-l-.06) if l>.35 else .55   # text: light grey -> dark grey
        ns=s*.5 if s<.22 else min(s,.35)
        rr,gg,bb=colorsys.hls_to_rgb(h,nl,ns); return fmt(rr*255,gg*255,bb*255,a)
    # saturated colours
    if bgish and l<.32:                                                       # dark tinted panel -> light tint
        rr,gg,bb=colorsys.hls_to_rgb(h,.95,min(.6,s)); return fmt(rr*255,gg*255,bb*255,a)
    if a<1: return fmt(r,g,b,a)                                               # tints keep
    if l>.55 and not bgish:                                                   # bright text/border on dark -> deeper shade
        rr,gg,bb=colorsys.hls_to_rgb(h,max(.34,1.02-l),min(1,s)); return fmt(rr*255,gg*255,bb*255,a)
    return None
out=[]
def walk(block, wrap=None):
    pos=0
    while True:
        m=re.search(r'([^{}]+)\{',block[pos:])
        if not m: break
        sel=m.group(1).strip(); st=pos+m.end()
        if sel.startswith('@'):
            depth=1;k=st
            while depth: 
                if block[k]=='{':depth+=1
                elif block[k]=='}':depth-=1
                k+=1
            if sel.startswith('@media') or sel.startswith('@supports'): walk(block[st:k-1], sel)
            pos=k; continue
        k=block.index('}',st); body=block[st:k]; pos=k+1
        if sel.startswith(':root') or 'html.boot' in sel: continue
        decls=[]
        bgs=[d.split(':',1)[1] for d in body.split(';') if ':' in d and d.split(':',1)[0].strip().startswith('background')]
        onfill=any(('var(--accent' in v or 'var(--green' in v or 'var(--red' in v or 'var(--amber' in v) and '-bg' not in v for v in bgs) or any(
            (lambda c:(lambda r,g,b,a:a>.9 and colorsys.rgb_to_hls(r/255,g/255,b/255)[2]>.3 and colorsys.rgb_to_hls(r/255,g/255,b/255)[1] >.35)(*parse(c)))(m.group(0)) for v in bgs for m in COL.finditer(v))
        for d in body.split(';'):
            if ':' not in d: continue
            p,v=d.split(':',1); p=p.strip().lower(); v=v.strip()
            if 'var(' in v and not COL.search(v): continue
            if not COL.search(v) or p.startswith('--'): continue
            ch=False
            if p=='color' and onfill: continue   # text on a coloured button keeps its colour
            def rep(mm):
                nonlocal ch
                n=conv(mm.group(0),p)
                if n and n!=mm.group(0).lower(): ch=True; return n
                return mm.group(0)
            nv=COL.sub(rep,v)
            if ch: decls.append(f'{p}:{nv}')
        if decls:
            sels=','.join(('html.light '+x.strip()) if not x.strip().startswith('html') else x.strip().replace('html','html.light',1) for x in sel.split(','))
            rule=sels+'{'+';'.join(decls)+'}'
            out.append((wrap,rule))
walk(css)
from itertools import groupby
res=[]
for w,grp in groupby(out,key=lambda x:x[0]):
    rules=''.join(r for _,r in grp)
    res.append(f'{w}{{{rules}}}' if w else rules)
# literal svg colours used in markup/JS
lit=set(re.findall(r'(fill|stroke|stop-color)="(#[0-9a-fA-F]{3,6})"',src))
lit|=set((a,b) for b in re.findall(r"'(#[0-9a-fA-F]{6})'",src) for a in ('fill','stroke'))
svg=[]
for p,c in sorted(lit):
    n=conv(c,'fill' if p!='stroke' else 'stroke')
    if n and n!=c.lower(): svg.append(f'html.light [{p}="{c}"]{{{p}:{n}}}')
sys.stdout.write(''.join(res)+''.join(svg))
print('\n/* rules:',len(out),'svg:',len(svg),'*/',file=sys.stderr)
