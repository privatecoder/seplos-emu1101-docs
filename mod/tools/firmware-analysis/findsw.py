
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('VERSION HEXBASE...')
import sys,re,subprocess
v=sys.argv[1]; pats=sys.argv[2:]
L=[l for l in open(DATA_DIR / f'v{v}.dis')]
P=[]
for i,l in enumerate(L):
    for p in pats:
        if re.search(rf'subs\s+r\d, #{p}$',l.rstrip()):
            for j in range(i+1,i+5):
                m=re.match(r'\s*([0-9a-f]+):.*\tbl\s+0x([0-9a-f]+)',L[j])
                if m: P.append(f'{m[1]}:{p[2:]}'); break
print(' '.join(P))
