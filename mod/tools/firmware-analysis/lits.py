
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('VERSION...')
import re,sys,struct,collections
def lits(v):
    raw=open(DATA_DIR / f'v{v}.raw','rb').read(); vals=collections.Counter()
    for l in open(DATA_DIR / f'v{v}.dis'):
        m=re.search(r'ldr\s+r\d, \[pc, #0x[0-9a-f]+\]\s+@ 0x([0-9a-f]+)',l)
        if m:
            a=int(m[1],16)
            if a+4<=len(raw): vals[struct.unpack('<I',raw[a:a+4])[0]]+=1
    return vals
V=sys.argv[1:]
prev=None
for v in V:
    c=lits(v)
    if prev:
        add=sorted(set(c)-set(prev)); rem=sorted(set(prev)-set(c))
        f=lambda x:[hex(i) for i in x if not (0x20000000<=i<0x20004000)]
        print(f'## {pv}->{v}  non-RAM literals added:',f(add)); print('   removed:',f(rem))
    prev=c;pv=v
