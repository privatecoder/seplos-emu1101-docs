import sys,re
v=sys.argv[1]; raw=open(f'v{v}.raw','rb').read()
dis={}
for l in open(f'v{v}.dis'):
    m=re.match(r'\s*([0-9a-f]+):\s+\S+(?: \S+)?\s+\t(\S+)\s*(.*)',l)
    if m: dis[int(m[1],16)]=(m[2],re.sub(r'\s*<_bin[^>]*>|@.*','',m[3]))
def tgt(a):
    # describe what happens at a: first bl or few instrs
    out=[]
    for k in range(8):
        x=dis.get(a+2*k)
        if x: out.append(f'{x[0]} {x[1]}')
        if x and x[0] in('bl','b'): break
    return '; '.join(out)
for spec in sys.argv[2:]:
    blat,base=[int(x,16) for x in spec.split(':')]
    lr=blat+4  # after bl (4 bytes)
    n=raw[lr]; print(f'-- switch at {blat:#x}: n={n} base={base:#x}')
    for i in range(n+1):
        off=raw[lr+1+i]; t=(lr+1)+off*2-1
        lab=f'{base+i:#04x}' if i<n else 'default'
        print(f'   {lab}: -> {t:#x}: {tgt(t)}')
