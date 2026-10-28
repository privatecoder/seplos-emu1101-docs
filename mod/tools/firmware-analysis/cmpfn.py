
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))

from _paths import analysis_arguments
DATA_DIR = analysis_arguments('V1 ADDR1 V2 ADDR2 [SHIFT] [DIFF]')
import re,sys,difflib,subprocess
def norm(v,start,shift):
    result=subprocess.run([sys.executable,'-I','-B',str(_Path(__file__).with_name('show.py')),'--data-dir',str(DATA_DIR),v,hex(start),'600'],capture_output=True,text=True)
    if result.returncode:
        raise SystemExit(f'cmpfn: cannot decode v{v}@{start:#x}: {result.stderr.strip() or "show.py failed"}')
    out=result.stdout.splitlines()
    if not out:
        raise SystemExit(f'cmpfn: no decoded body for v{v}@{start:#x}')
    res=[]
    for l in out:
        a,ins=l.split(':',1); ins=ins.strip()
        ins=re.sub(r'\s*@ imm = #-?0x[0-9a-f]+','',ins)
        if re.match(r'b(l|eq|ne|hi|lo|hs|ls|gt|lt|ge|le|mi|pl|cc|cs)?\s',ins):
            if ins.startswith('bl '): ins='bl FN'
            else: ins=re.sub(r'0x([0-9a-f]+)',lambda m: f'L{int(m.group(1),16)-start:+#x}',ins)
        def fix(m):
            x=int(m.group(1),16)
            if 0x200000c0<=x<0x20002000: x+=shift
            return f'=0x{x:08x}'
        ins=re.sub(r'=0x([0-9a-f]{8})',fix,ins)
        res.append(ins)
    return res
v1,a1,v2,a2=sys.argv[1],int(sys.argv[2],16),sys.argv[3],int(sys.argv[4],16)
sh=int(sys.argv[5]) if len(sys.argv)>5 else 0
x=norm(v1,a1,sh); y=norm(v2,a2,0)
d=list(difflib.unified_diff(x,y,lineterm='',n=1))
print(f'{v1}@{a1:#x} ({len(x)}) vs {v2}@{a2:#x} ({len(y)}): {"IDENTICAL" if not d else str(len(d))+" difflines"}')
if len(sys.argv)>6:
    for l in d[2:]: print(l)
