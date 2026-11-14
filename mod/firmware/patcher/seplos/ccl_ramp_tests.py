"""Mandatory Full1.6.7 native ramp, mirrored persistence and addressed wire tests."""
from .machine import Machine,PowerLoss,ascii_frame,frame
from .marker_uart0_tests import uart0_exchange
from .selftest import ascii_payload
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
 UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
 UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_PRIMASK)

REQUIRED=tuple('ccl-ramp-'+n for n in (
 'native-all-factors-clamp-ascent-and-ABI','native-overrides-and-ordinary-target',
 'addressed-read-write-all-ports','strict-values-length-permission-and-address',
 'mirrored-persistence-legacy-invalid-and-disagreement','parameter-and-Off-write-preservation',
 'failed-write-rollback-and-reboot','power-cut-every-flash-boundary','capability-and-default'))

def validate_ccl_ramp(original,patched,facts,build):
 rows=[];r=facts['ram'];d=facts['cutoff'];c=facts['ccl_ramp'];e=build['entries']
 def board(adr=0):
  m=Machine(patched,facts);m.defaults(adr);return m
 def query(m,data,port=1,address=None,raw=None):
  a=m.num(r['address']) if address is None else address
  packet=raw or ascii_frame(a,0x64,data)
  out=m.transact(packet,True) if port else uart0_exchange(m,packet)
  return ascii_payload(out,a) if out else None
 def response(value):return (0,bytes([1,value,1,1,20]))
 def reboot(m):
  n=Machine(patched,facts);n.put(d['nv_primary'],m.read(d['nv_primary'],8192));n.defaults(m.num(r['address']));return n
 def step(m):return query(m,b'\7')[1][1]
 def arithmetic():
  m=board();keep=(UC_ARM_REG_R4,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12)
  for reg in keep:m.uc.reg_write(reg,0x12345678+reg)
  sp=m.uc.reg_read(UC_ARM_REG_SP)
  for factor in range(1,21):
   m.put(c['ram'],bytes([factor]))
   for n in (0,1,12,16,255):
    base=n*10;down=base*factor
    for target in (0,1,100,32768,65535):
     for delta in set((0,1,base-1,base,base+1,down-1,down,down+1,65535-target)):
      for current in (target+delta,target-delta):
       if not 0<=current<=65535:continue
       m.put(d['aggregate']+36,current.to_bytes(2,'little'))
       m.uc.reg_write(UC_ARM_REG_R0,target);m.uc.reg_write(UC_ARM_REG_R2,base);m.uc.reg_write(UC_ARM_REG_R5,d['aggregate'])
       m.execute(c['site']-22,c['site']+14,count=100)
       expected=min(target,current+base) if current<target else max(target,current-down)
       assert m.num(d['aggregate']+36,2)==expected,(factor,n,current,target)
       assert m.uc.reg_read(UC_ARM_REG_SP)==sp
       assert all(m.uc.reg_read(reg)==0x12345678+reg for reg in keep)
  # Corrupt cache is treated as the default rather than zero/frozen descent.
  for invalid in (0,21,255):
   m.put(c['ram'],bytes([invalid]));m.put(d['aggregate']+36,(1000).to_bytes(2,'little'))
   m.uc.reg_write(UC_ARM_REG_R0,100);m.uc.reg_write(UC_ARM_REG_R1,1000);m.uc.reg_write(UC_ARM_REG_R2,120)
   m.execute(c['site'],c['site']+14,count=100)
   assert m.num(d['aggregate']+36,2)==880
 def overrides():
  for factor in (1,10,20):
   for mode in ('ordinary','blocked','voltage','heating'):
    m=board();a=d['aggregate'];m.put(c['ram'],bytes([factor]))
    for off,v in ((0,12),(1,12),(3,0),(4,12),(6,12 if mode=='blocked' else 0)):m.put(a+off,bytes([v]))
    m.put(r['words']+100,(14000).to_bytes(2,'little'));m.put(r['words']+104,((-14000)&65535).to_bytes(2,'little'))
    m.put(r['group0']+7,b'\x80');m.put(0x200000f7,bytes([0 if mode=='voltage' else 4]))
    m.put(r['group0']+3,bytes([64 if mode=='heating' else 0]));m.put(a+36,(100 if mode=='heating' else 15600).to_bytes(2,'little'))
    m.run(d['ccl'])
    expected={'ordinary':15600-120*factor,'blocked':0,'voltage':0,'heating':1200}[mode]
    assert m.num(a+36,2)==expected,(mode,factor,m.num(a+36,2),expected)
 def wire():
  for port in (0,1):
   for adr in range(22):
    m=board(adr)
    assert query(m,b'\7',port)==response(1)
    assert query(m,b'\10\x14',port)==response(20)
    assert query(reboot(m),b'\7',port)==response(20)
 def strict():
  for port in (0,1):
   m=board(1)
   for data in (b'\7\0',b'\10',b'\10\0',b'\10\x15',b'\10\xff',b'\10\1\0'):
    before=len(m.nv_ops);assert query(m,data,port)==(5,b''),(port,data)
    assert len(m.nv_ops)==before and step(m)==1
   for adr in (0,2,255):
    before=len(m.nv_ops);assert query(m,b'\10\x0a',port,adr) is None
    assert len(m.nv_ops)==before
   packet=ascii_frame(1,0x64,b'\10\x0a')
   for at,replacement in ((1,b'21'),(5,b'47'),(9,b'0004'),(15,b'GG')):
    body=bytearray(packet[1:-5]);body[at-1:at+1]=replacement
    bad=b'~'+body+f'{(-sum(body))&65535:04X}'.encode()+b'\r'
    before=len(m.nv_ops);assert query(m,b'',port,raw=bad)!=response(10)
    assert len(m.nv_ops)==before and step(m)==1
   before=len(m.nv_ops);bad_result=query(m,b'',port,raw=packet[:-5]+b'0000\r')
   assert bad_result is None or bad_result[0]!=0,bad_result
   assert len(m.nv_ops)==before and step(m)==1
   m.put(r['group0'],bytes([m.num(r['group0'])&~1]))
   assert query(m,b'\10\x0a',port)==((4,b'') if port else response(10))
 def mirrors():
  m=board();assert query(m,b'\10\x0a')==response(10)
  assert step(reboot(m))==10
  original_pages=m.read(d['nv_primary'],8192)
  for trailer in (b'\xff'*3,b'\0'*3,b'\xe7\0\xff',b'\xe7\x15\xea',b'\xe7\x0a\0',b'\xe7\x05\xfa'):
   m.put(d['nv_primary'],original_pages);m.put(d['nv_primary']+173,trailer)
   assert step(reboot(m))==1,trailer
  m.put(d['nv_primary'],original_pages);m.put(d['nv_primary']+5,b'\xff')
  assert step(reboot(m))==1
  # Read-only diagnostics do not reload or overwrite the active cache.
  m.put(c['ram'],b'\x0a');query(m,b'\4');assert step(m)==10
 def preservation():
  m=board(1);assert query(m,b'\10\x0a')==response(10)
  p=m.payload();assert m.transact(frame(1,0xa1,p),True)==frame(1,0xa1)
  assert step(reboot(m))==10
  m.put(r['group0'],bytes([m.num(r['group0'])|0x18]))
  for action in (0x1f,0x10):
   out=m.transact(ascii_frame(1,0x45,bytes([0,4,action])),True)
   assert ascii_payload(out,1)==(0,b'')
   assert step(reboot(m))==10
 def failures():
  for fail in range(1,5):
   m=board();assert query(m,b'\10\5')==response(5)
   m.nv_step=0;m.nv_fail_at={fail}
   assert query(m,b'\10\x0a')==(8,b''),fail
   assert step(m)==5
   assert step(reboot(m))==1
   m.nv_fail_at=set();m.run(e['hook_cut_serializer_0']);assert step(reboot(m))==5
 def powercuts():
  for cut in range(1,5):
   m=board();assert query(m,b'\10\5')==response(5)
   m.nv_step=0;m.nv_cut_after=cut
   try:query(m,b'\10\x0a')
   except PowerLoss:pass
   else:raise AssertionError('missing cut')
   assert step(reboot(m))==(10 if cut==4 else 1)
 def capability():
  m=board();info=query(m,b'\3')[1]
  assert info[7:10]==bytes([1,6,7]) and info[19:]==b'\0\x1f'
  assert query(m,b'\7')==response(1)
 for name,fn in zip(REQUIRED,(arithmetic,overrides,wire,strict,mirrors,preservation,failures,powercuts,capability)):
  try:fn()
  except Exception as exc:raise AssertionError(name+': '+str(exc)) from exc
  rows.append(dict(name=name,passed=True))
 return rows
