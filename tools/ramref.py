import re,sys,struct
v=sys.argv[1]; targets=[int(x,16) for x in sys.argv[2:]]
raw=open(f'v{v}.raw','rb').read()
regs={}; fn=0
for l in open(f'v{v}.dis'):
    m=re.match(r'\s*([0-9a-f]+):\s+(\S+(?: \S+)?)\s+\t(\S+)\s*(.*)',l)
    if not m: continue
    a=int(m[1],16); op=m[3]; ops=m[4]
    if op=='push' and 'lr' in ops: regs={}; fn=a
    mm=re.match(r'(r\d+), \[pc, #0x[0-9a-f]+\]\s+@ 0x([0-9a-f]+)',ops)
    if op=='ldr' and mm:
        la=int(mm[2],16)
        if la+4<=len(raw): regs[mm[1]]=struct.unpack("<I",raw[la:la+4])[0]
        continue
    mm=re.match(r'(r\d+), (r\d+), #0x([0-9a-f]+)$',ops)
    if op in('adds','subs') and mm and mm[2] in regs:
        regs[mm[1]]=regs[mm[2]]+(1 if op=='adds' else -1)*int(mm[3],16); continue
    mm=re.match(r'(r\d+), #0x([0-9a-f]+)$',ops)
    if op in('adds','subs') and mm and mm[1] in regs:
        regs[mm[1]]+=(1 if op=='adds' else -1)*int(mm[2],16); continue
    mm=re.match(r'(r\d+), (r\d+)$',ops)
    if op=='mov' and mm:
        if mm[2] in regs: regs[mm[1]]=regs[mm[2]]
        else: regs.pop(mm[1],None)
        continue
    mm=re.match(r'(r\d+), \[(r\d+)(?:, #0x([0-9a-f]+))?\]',ops)
    if op.startswith(('ldr','str')) and mm and mm[2] in regs:
        ea=regs[mm[2]]+int(mm[3] or '0',16)
        if ea in targets: print(f'{a:6x} fn {fn:5x}: {op} {ops}  -> {ea:#x}')
        if op.startswith('ldr'): regs.pop(mm[1],None)
        continue
    mm=re.match(r'(r\d+)',ops)
    if mm and op not in('cmp','tst','str','strb','strh','b','bl','bne','beq') and not op.startswith('b'): regs.pop(mm[1],None)
    if op=='bl': [regs.pop(r,None) for r in ('r0','r1','r2','r3')]
