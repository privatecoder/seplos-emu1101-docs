"""Mandatory actual-Thumb proof of the separate positive-control MAINT1.6."""
from .machine import Machine,ascii_frame,frame

REQUIRED=(
 'positive-info-capability-and-version',
 'positive-bit3-zero-denies','positive-bit3-one-allows',
 'positive-bit4-zero-UART0','positive-bit4-one-UART0',
 'positive-bit4-zero-UART1','positive-bit4-one-UART1',
 'positive-FF-enables-both-features',
 'positive-active-bit4-zero-without-latch','positive-active-bit4-one-without-latch',
 'positive-mode-disable-does-not-release-latch',
 'positive-parameter-roundtrip-no-migration',
)


def validate_positive(original,patched,facts,report):
 from .selftest import ascii_payload
 r=facts['ram'];d=facts['cutoff'];e=d['entries'];checks=[]
 def equal(a,b):assert a==b,(a,b)
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError(name+': '+str(exc)) from exc
  checks.append(dict(name=name,passed=True))
 def board(bit3=True,bit4=True,address=1):
  m=Machine(patched,facts);m.defaults(address)
  group=(m.num(r['group0'])&~0x18)|(8 if bit3 else 0)|(16 if bit4 else 0)
  m.put(r['group0'],bytes([group]));return m
 def request(m,cmd,data=b''):
  adr=m.num(r['address']);return ascii_payload(m.transact(ascii_frame(adr,cmd,data),True),adr)
 def power(m,value):return request(m,0x45,bytes([0,4,value]))
 def u0(m,value,broadcast=False):
  adr=255 if broadcast else m.num(r['address'])
  m.put(d['uart0_rx'],ascii_frame(adr,0x45,bytes([0,4,value])))
  m.put(d['uart0_state'],b'\3');m.put(d['uart0_rtn'],b'\0')
  m.run(e['hook_cut_uart0_power']);return m.num(d['uart0_rtn'])
 def latch(m):return m.num(d['ram'])
 def reboot(m):
  n=Machine(patched,facts);n.put(0x25000,m.read(0x25000,8192));n.defaults(m.num(r['address']));return n

 def info():
  assert report.get('positive_flags') is True and report['image_flags']&14==14
  m=board();rtn,data=request(m,0x64,b'\3')
  equal((rtn,len(data),data[:4],data[7:9],data[-1]),(0,report['info_bytes'],b'MNT'+bytes([report['info_format']]),b'\1\6',report['image_flags']))
 check(REQUIRED[0],info)
 for enabled in (False,True):
  def bit3(enabled=enabled):
   for cmd,data in ((0x45,b'\0\4\x10'),(0x45,b'\0\4\x1f'),(0x4e,bytes.fromhex('07EA0A15010203'))):
    m=board(enabled,False);equal(request(m,cmd,data),(0 if enabled else 5,b''))
  check('positive-bit3-one-allows' if enabled else 'positive-bit3-zero-denies',bit3)
 for route in ('UART0','UART1'):
  for enabled in (False,True):
   def bit4(route=route,enabled=enabled):
    for adr in (0,1,11,15):
     m=board(True,enabled,adr)
     equal(u0(m,31) if route=='UART0' else power(m,31),0 if route=='UART0' else (0,b''))
     equal(latch(m),int(enabled));equal(bool(m.nv_ops),enabled)
     if enabled:
      equal(m.num(d['onoff'])&0x17,0);equal(latch(reboot(m)),1)
   check('positive-bit4-'+('one' if enabled else 'zero')+'-'+route,bit4)
 def defaults():
  m=Machine(patched,facts);m.defaults(1);equal(m.num(r['group0']),255)
  equal(power(m,31),(0,b''));equal(latch(m),1);equal(latch(reboot(m)),1)
 check('positive-FF-enables-both-features',defaults)
 for enabled in (False,True):
  def active(enabled=enabled):
   m=board(True,enabled);equal(u0(m,31,True),0);equal(latch(m),0);equal(m.nv_ops,[])
   m.put(d['onoff'],b'\x03');m.put(0x50002000,((1<<12)|(1<<13)).to_bytes(4,'little'))
   m.run(e['hook_cut_enforce'])
   equal(m.num(d['onoff'])&0x17,0 if enabled else 3)
   equal(m.num(0x50002000,4)&((1<<12)|(1<<13)),0 if enabled else (1<<12)|(1<<13))
  check('positive-active-bit4-'+('one' if enabled else 'zero')+'-without-latch',active)
 def disable_mode():
  m=board();equal(power(m,31),(0,b''));p=bytearray(m.payload());p[150]&=~16
  equal(m.transact(frame(1,0xa1,p),True),frame(1,0xa1));equal(latch(m),1)
  n=reboot(m);equal(latch(n),1);assert not n.num(r['group0'])&16
  equal(power(n,16),(0,b''));equal(latch(reboot(n)),0)
 check('positive-mode-disable-does-not-release-latch',disable_mode)
 def no_migration():
  for group in (0xe7,0xef,0xf7,0xff):
   m=board();m.put(r['group0'],bytes([group]));m.run(e['hook_cut_serializer_0'])
   equal(reboot(m).num(r['group0']),group)
 check('positive-parameter-roundtrip-no-migration',no_migration)
 equal({c['name'] for c in checks},set(REQUIRED))
 return checks
