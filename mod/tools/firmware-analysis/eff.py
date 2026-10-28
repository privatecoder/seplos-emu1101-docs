
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('VERSION LO HI')
# crude: track reg=literal, adds/subs imm, then report loads/stores [reg,#imm] hitting [lo,hi)
import re,sys,struct
v=sys.argv[1]; lo=int(sys.argv[2],16); hi=int(sys.argv[3],16)
raw=open(DATA_DIR / f'v{v}.raw','rb').read(); regs={}; fn=0
for l in open(DATA_DIR / f'v{v}.dis'):
    m=re.match(r'\s*([0-9a-f]+):\s+\S+(?: \S+)?\s+\t(\S+)\s*(.*)',l)
    if not m: continue
    a=int(m[1],16); op=m[2]; ar=re.sub(r'\s*<_bin[^>]*>','',m[3])
    if op=='push' and 'lr' in ar: fn=a; regs={}
    mm=re.match(r'(r\d), \[pc, #0x[0-9a-f]+\]\s+@ 0x([0-9a-f]+)',ar)
    if op=='ldr' and mm:
        la=int(mm[2],16)
        if la+4<=len(raw): regs[mm[1]]=struct.unpack('<I',raw[la:la+4])[0]
        continue
    mm=re.match(r'(r\d), #0x([0-9a-f]+)$',ar)
    if op in('adds','subs') and mm and mm[1] in regs:
        regs[mm[1]]+= int(mm[2],16)*(1 if op=='adds' else -1); continue
    mm=re.match(r'(r\d), (r\d)$',ar)
    if op=='mov' and mm:
        if mm[2] in regs: regs[mm[1]]=regs[mm[2]]
        else: regs.pop(mm[1],None)
        continue
    mm=re.match(r'(r\d), \[(r\d)(?:, #0x([0-9a-f]+))?\]',ar)
    if mm and op.startswith(('ldr','str')):
        if mm[2] in regs:
            ea=regs[mm[2]]+int(mm[3] or '0',16)
            if lo<=ea<hi: print(f'{a:#x} fn {fn:#x}: {op} {ar}  EA={ea:#x}')
        if op.startswith('ldr'): regs.pop(mm[1],None)
        continue
    d=re.match(r'(r\d)',ar)
    if d and op not in('cmp','tst','str','strh','strb','b','bl','bx','push','pop'): regs.pop(d[1],None)
