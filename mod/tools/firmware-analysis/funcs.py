
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

if '--help' in _sys.argv or '-h' in _sys.argv:
    print('Usage: funcs.py A.dis B.dis')
    raise SystemExit(0)
import re,sys,hashlib,collections,difflib
def load(path):
    ins=[]
    for l in open(path):
        m=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{4}(?: [0-9a-f]{4})?)\s+\t(\S+)\s*(.*)',l)
        if m: ins.append((int(m[1],16),m[2],m[3],m[4].split('@')[0].strip()))
    return ins
def norm(mn,ops):
    if mn.startswith('b') and mn not in('bics','bic'): return mn
    if 'pc' in ops and mn=='ldr': return 'ldr '+ops.split(',')[0]+',[pc]'
    return mn+' '+ops
def split(ins):
    # function starts at push {...lr}
    funcs=[];cur=None
    for a,h,mn,ops in ins:
        if mn=='push' and 'lr' in ops:
            cur=[a,[]];funcs.append(cur)
        if cur: cur[1].append((a,mn,ops))
    out={}
    for start,body in funcs:
        # trim at last pop pc / bx lr region: keep up to 400 instrs; normalized
        sig=tuple(norm(mn,ops) for a,mn,ops in body)
        out[start]=sig
    return out
a=split(load(sys.argv[1])); b=split(load(sys.argv[2]))
ha=collections.defaultdict(list); hb=collections.defaultdict(list)
for k,v in a.items(): ha[v].append(k)
for k,v in b.items(): hb[v].append(k)
same=set(ha)&set(hb)
ua=[k for k,v in a.items() if v not in same]; ub=[k for k,v in b.items() if v not in same]
print(f'funcs A={len(a)} B={len(b)} identical(norm)={sum(len(hb[s]) for s in same)} changed/removed A={len(ua)} new/changed B={len(ub)}')
# pair unmatched by best similarity
used=set()
for ka in ua:
    best=None
    for kb in ub:
        if kb in used: continue
        r=difflib.SequenceMatcher(None,a[ka],b[kb],autojunk=False).quick_ratio()
        if r>0.6 and (best is None or r>best[0]): best=(r,kb)
    if best:
        r=difflib.SequenceMatcher(None,a[ka],b[best[1]],autojunk=False).ratio()
        used.add(best[1]); print(f'  CHANGED  A:{ka:#06x}({len(a[ka])}) -> B:{best[1]:#06x}({len(b[best[1]])}) sim={r:.2f}')
    else: print(f'  REMOVED  A:{ka:#06x}({len(a[ka])})')
for kb in ub:
    if kb not in used: print(f'  NEW      B:{kb:#06x}({len(b[kb])})')
