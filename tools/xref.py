import re,sys,struct
v=sys.argv[1]; targets=[int(x,16) for x in sys.argv[2:]]
raw=open(f'v{v}.raw','rb').read()
fn=0
for l in open(f'v{v}.dis'):
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
