import re,sys,struct
v=sys.argv[1]; start=int(sys.argv[2],16); n=int(sys.argv[3]) if len(sys.argv)>3 else 400
raw=open(f'v{v}.raw','rb').read(); on=False; c=0
for l in open(f'v{v}.dis'):
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
