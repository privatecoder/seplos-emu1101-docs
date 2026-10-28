
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('VERSION HEXVALUE...')
import re,sys,struct
v=sys.argv[1]; targets=[int(x,16) for x in sys.argv[2:]]
raw=open(DATA_DIR / f'v{v}.raw','rb').read()
fn=0
for l in open(DATA_DIR / f'v{v}.dis'):
    m=re.match(r'\s*([0-9a-f]+):\s+\S+\s+(?:\S+\s+)?\t(\S+)\s*(.*)',l)
    if not m: continue
    a=int(m[1],16)
    if m[2]=='push' and 'lr' in m[3]: fn=a
    mm=re.search(r'ldr\s+r\d, \[pc, #0x[0-9a-f]+\]\s+@ 0x([0-9a-f]+)',l)
    if mm:
        la=int(mm[1],16)
        if la+4>len(raw): continue
        val=struct.unpack('<I',raw[la:la+4])[0]
        for t in targets:
            if val==t: print(f'{t:#x} referenced at {a:#x} in func {fn:#x}')
