
# Resolve shared tool paths independently of the working directory and Python -I.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(next(p for p in _Path(__file__).resolve().parents if (p / '_paths.py').is_file())))
from _paths import PROJECT_ROOT, TOOLS_ROOT, PATCHER_ROOT, LOCAL_ROOT
import subprocess,sys,time
from pathlib import Path
QUERY = Path(__file__).resolve().with_name('seplos_query.py')
import argparse
_parser=argparse.ArgumentParser(description='Read-only UART0 telemetry monitor')
_parser.add_argument('seconds',type=float)
_parser.add_argument('--port',required=True)
_args=_parser.parse_args()
P=_args.port
def q(c,i=''):
    o=subprocess.run([sys.executable,'-I',str(QUERY),P,'19200','00',c]+([i] if i else []),capture_output=True,text=True).stdout
    return o.split('RX ',1)[1].strip() if 'RX ~' in o else None
t0=time.time(); ok=0
while time.time()-t0<_args.seconds:
    r=q('42','00')
    ts=time.strftime('%T')
    if r:
        info=bytes.fromhex(r[13:-4]); u=lambda o:int.from_bytes(info[o:o+2],'big')
        # 16 cells: port voltage at INFO byte offset 65 (ASCII 130)
        print(ts,'awake  Port %.2f V  Pack %.2f V'%(u(65)/100,u(50)/100),flush=True); ok+=1
    else:
        print(ts,'keine Antwort',flush=True)
    time.sleep(10)
