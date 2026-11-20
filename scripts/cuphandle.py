"""Cup-with-handle shape detector on daily closes. Describes price shape only (no signal, no buy point)."""
def detect(c):
    c=[x for x in c if x is not None]; n=len(c)
    if n<120: return None
    best=None
    for h in range(5,26):                       # handle length (trading days)
        k=n-1-h                                  # right rim index
        if k<60: continue
        for L in range(40,200,5):                # cup length
            i=k-L
            if i<0: break
            seg=c[i:k+1]; p1=max(seg[:max(3,L//6)]); 
            if seg.index(p1)>L//6: continue      # left peak must be near the cup start
            lo=min(seg); j=i+seg.index(lo); depth=1-lo/p1
            if not(0.12<=depth<=0.35): continue
            if not(0.25<=(j-i)/L<=0.75): continue   # bottom roughly mid-cup
            if c[k]<p1*0.95 or c[k]>p1*1.03: continue   # right rim near left peak
            if p1<max(c[max(0,i-60):k+1]): continue        # left peak is a real high
            if p1<min(c[max(0,i-120):i+1])*1.3: continue    # prior advance of 30%+
            thr=lo+(p1-lo)/3
            if sum(1 for x in seg if x<=thr)/len(seg)<0.25: continue   # rounded, not a V
            hs=c[k:]; hh=max(hs); hl=min(hs[1:]) if len(hs)>1 else hs[0]
            hd=1-hl/hh
            if not(0.01<=hd<=min(0.12,depth/3)): continue
            if hl<lo+(p1-lo)*0.5: continue          # handle stays in upper half of the cup
            if c[-1]<hl or c[-1]>hh*1.01: continue    # still inside the handle
            sc=abs(depth-0.22)+hd+abs((j-i)/L-0.5)
            if best is None or sc<best[0]:
                best=(sc,{'depth':round(depth*100,1),'cup_days':L,'handle_days':h,'handle_pct':round(hd*100,1),'rim':round(hh,2),'low':round(lo,2),'i':i,'j':j,'k':k})
    return best[1] if best else None
