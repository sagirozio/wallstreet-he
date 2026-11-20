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


def flat_base(c):
    """Flat base: 25-80 sessions in a tight band (<=15%), after a 30%+ advance, price near the top of the band."""
    c=[x for x in c if x is not None]; n=len(c)
    if n<150: return None
    best=None
    for L in range(25,81,5):
        seg=c[n-L:]; hi=max(seg); lo=min(seg); rng=1-lo/hi
        if rng>0.10: continue
        if c[-1]<hi*0.95 or c[-1]<lo+(hi-lo)*0.5: continue          # near the top of the band
        mid=(hi+lo)/2; cr=sum(1 for x,y in zip(seg,seg[1:]) if (x-mid)*(y-mid)<0)
        if cr<4 or abs(c[-1]-seg[0])>0.35*(hi-lo): continue           # sideways, not a drift from the bottom to the top of the band
        pre=c[max(0,n-L-120):n-L]
        if not pre or hi<min(pre)*1.3: continue                    # prior advance of 30%+
        if max(pre)>hi*1.15: continue                              # base sits near the prior high, not after a collapse
        if best is None or L>best[0]: best=(L,round(rng*100,1))
    return [best[1],best[0]] if best else None


def double_bottom(c):
    """Double bottom (W): two lows within ~5% of each other, 15+ sessions apart, a middle peak 10%+ above them.
    Returns [depth %, left peak, first low, middle peak, second low], the last four as sessions back from the newest close."""
    c=[x for x in c if x is not None]; n=len(c)
    if n<150: return None
    best=None
    for j2 in range(n-30,n-5):
        if c[j2]!=min(c[max(0,j2-5):j2+6]): continue                # local low
        for gap in range(15,70):
            j1=j2-gap
            if j1<30: break
            if c[j1]!=min(c[max(0,j1-5):j1+6]): continue
            lo=min(c[j1],c[j2])
            if abs(c[j2]/c[j1]-1)>0.05: continue
            seg=c[j1:j2+1]; mid=max(seg); m=j1+seg.index(mid)
            if mid<lo*1.10 or mid>lo*1.35: continue
            a=max(0,j1-60); pre=c[a:j1+1]; p0=max(pre); i0=a+pre.index(p0); dep=1-lo/p0
            if not(0.15<=dep<=0.40): continue
            if c[-1]<lo*1.08 or c[-1]>mid*1.03 or c[-1]<lo+(mid-lo)*0.5: continue   # recovering, not far above the middle peak
            sc=abs(c[j2]/c[j1]-1)+abs(dep-0.25)
            if best is None or sc<best[0]: best=(sc,[round(dep*100,1),n-1-i0,n-1-j1,n-1-m,n-1-j2])
    return best[1] if best else None
