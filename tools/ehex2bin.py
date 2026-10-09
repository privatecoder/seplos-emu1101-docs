import sys,os,struct
out=sys.argv[1]
for p in sys.argv[2:]:
    recs=open(p).read().split()
    hdr=bytearray(); img={}; ext=0; entry=None
    for i,l in enumerate(recs):
        b=bytes.fromhex(l[1:]); n=b[0]; a=(b[1]<<8)|b[2]; t=b[3]; d=b[4:4+n]
        if i<15: hdr+=d; continue
        if t==0:
            for k,x in enumerate(d): img[ext+a+k]=x
        elif t==4: ext=struct.unpack('>H',d)[0]<<16
        elif t==5: entry=struct.unpack('>I',d)[0]
    mx=max(img)+1; mn=min(img)
    bin_=bytes(img.get(k,0xFF) for k in range(mx))
    name=os.path.basename(p).replace('.ehex','')
    open(os.path.join(out,name+'.bin'),'wb').write(bin_)
    sp,rst=struct.unpack('<II',bin_[:8])
    print(name, 'hdr=',bytes(hdr[:48]).decode(), 'pad55=',all(x==0x55 for x in hdr[48:]),len(hdr),
          'range',hex(mn),hex(mx),'SP',hex(sp),'Reset',hex(rst),'entry',hex(entry) if entry else None,
          'w20',bin_[0x20:0x2c].hex(), 'tail',bin_[-24:].hex())
