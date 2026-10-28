
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('VERSION HEXADDR [N]')
import re,sys,struct
v=sys.argv[1]; start=int(sys.argv[2],16); n=int(sys.argv[3]) if len(sys.argv)>3 else 400
try:
    raw=(DATA_DIR / f'v{v}.raw').read_bytes()
    lines=(DATA_DIR / f'v{v}.dis').read_text().splitlines()
except OSError as exc:
    raise SystemExit(f'show: {exc}') from exc
if not raw:
    raise SystemExit(f'show: empty raw image: {DATA_DIR / f"v{v}.raw"}')
if n <= 0:
    raise SystemExit('show: instruction count must be positive')
on=False; c=0
for l in lines:
    m=re.match(r'\s*([0-9a-f]+):\s+(\S+(?: \S+)?)\s+\t(\S+)\s*(.*)',l)
    if not m: continue
    a=int(m[1],16)
    if a==start: on=True
    elif on and m[3]=='push' and 'lr' in m[4]: break
    if not on: continue
    ops=re.sub(r'\s*<_binary[^>]*>','',m[4])
    mm=re.search(r'\[pc, #0x[0-9a-f]+\]\s+@ 0x([0-9a-f]+)',ops)
    if mm:
        la=int(mm[1],16)
        if la+4<=len(raw): ops=ops.split('[pc')[0]+f'=0x{struct.unpack("<I",raw[la:la+4])[0]:08x}'
    print(f'{a:6x}: {m[3]:7} {ops}'); c+=1
    if c>=n: break

if not c:
    raise SystemExit(f'show: no decoded body at start address {start:#x} in {DATA_DIR / f"v{v}.dis"}')
