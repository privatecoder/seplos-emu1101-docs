"""Read-only storage diagnostics and intrinsic positive permissions."""
import copy
from .machine import Machine,ascii_frame
from .marker_uart0_tests import uart0_exchange
from .selftest import ascii_payload
from .service_tests import crc,soc_record
from unicorn.arm_const import (UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_R4,
 UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
 UC_ARM_REG_R10,UC_ARM_REG_R11)

REQUIRED=tuple('storage_diagnostics-'+name for name in (
 'exact-five-OEM-hooks-no-startup-or-NVM-change','version-and-capability-contract',
 'all-addresses-R-C-free-read-only','all-record-classes-no-repair',
 'shape-and-CRC-are-independent','valid-differences-and-unused-padding',
 'reserved-bit5-no-lock-cache-access','foreign-FF-invalid-local-silent',
 'malformed-and-following-recovery','ABI-and-C-R-display-canaries',
 'twelve-packs-exactly-one-response','R-C-reset-no-SOC-save',
 'positive-power-permission','native-parameter-save-unchanged',
 'unknown-source-and-buffer-ABI-refused','reserved-bit4-and-FF-no-power-NVM'))

def validate_diagnostics(original,patched,facts,report):
 r=facts['ram'];f=facts['functions'];d=facts['storage_diagnostics'];p=facts['power_rtc'];rows=[]
 positive=True;prefix='storage_diagnostics-'
 def equal(a,b):assert a==b,(a,b)
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError(prefix+name+': '+str(exc)) from exc
  rows.append(dict(name=prefix+name,passed=True))
 def board(adr=1):
  m=Machine(patched,facts);m.defaults(adr);m.run(f['serializer'])
  record=m.read(r['iap_buffer'],171)
  for a in (d['nv_primary'],d['nv_backup']):m.put(a,record+crc(record)+b'\xff'*83)
  for a in (d['soc_primary'],d['soc_backup']):m.put(a,soc_record()+b'\xff'*232)
  m.saves.clear();m.nv_ops.clear();m.flash_ops.clear();m.executed.clear();return m
 def exchange(m,port='C',info=b'\4',target=None,raw=None):
  adr=m.num(r['address']);packet=raw or ascii_frame(adr if target is None else target,0x64,info)
  answer=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
  return ascii_payload(answer,adr) if answer else None
 def no_write(m):
  equal(m.saves,[]);equal(m.nv_ops,[]);equal(m.flash_ops,[])
  for role in ('iap_read','iap_write','iap_erase','iap_program','capacity_save'):
   assert f[role] not in m.executed,role
 def hooks():
  expected={**facts['hooks'],**facts['marker_uart0']['hooks']}
  equal(report['hooks'],expected);equal(len(expected),5);equal(report['ram_bytes'],0)
  assert not report.get('cutoff') and bool(report.get('positive_flags'))==positive and not report.get('checkpoint_before_reset')
  assert all(not name.startswith(('hook_cut_','hook_service_')) for name in report['entries'])
  allowed={a for site in expected.values() for a in range(site,site+4)}
  if report.get('hard_stop',{}).get('changed'):allowed.add(report['hard_stop']['offset'])
  assert all(a in allowed or x==y for a,(x,y) in enumerate(zip(original.app,patched.app)))
 check('exact-five-OEM-hooks-no-startup-or-NVM-change',hooks)
 def version():
  equal(report['image_flags']&0xfe,0x3a);equal((report['info_format'],report['info_bytes']),(4,19))
  for port in ('R','C'):
   rtn,data=exchange(board(),port,b'\3')
   equal((rtn,data[:4],data[7:10],data[-1]),(0,b'MNT\4',b'\1\5'+bytes([3]),report['image_flags']))
 check('version-and-capability-contract',version)
 def all_addresses():
  for adr in range(22):
   for port in ('R','C'):
    m=board(adr);m.put(r['group0'],b'\0');nvm=m.read(0x23000,0xa000);params=m.payload()
    equal(exchange(m,port),(0,bytes([1,1,1,1,1,1,1,255,255,0])))
    equal(m.read(0x23000,0xa000),nvm);equal(m.payload(),params);no_write(m)
 check('all-addresses-R-C-free-read-only',all_addresses)
 def classes():
  for port in ('R','C'):
   for primary in range(3):
    for backup in range(3):
     m=board()
     for pair,length in (((d['nv_primary'],d['nv_backup']),171),((d['soc_primary'],d['soc_backup']),20)):
      for a,kind in zip(pair,(primary,backup)):
       if kind==0:m.put(a,b'\xff'*256)
       elif kind==2:m.put(a+length,bytes([m.num(a+length)^1]))
     before=m.read(0x25000,0x8000);rtn,data=exchange(m,port)
     equal(rtn,0);equal(data[1:4],bytes([primary,backup,int(primary==backup==1)]));equal(data[4:7],data[1:4])
     equal(m.read(0x25000,0x8000),before);no_write(m)
 check('all-record-classes-no-repair',classes)
 def shapes():
  for a,length,offsets,pos in ((d['nv_primary'],171,(0,1,2,123,151,162),1),(d['soc_primary'],20,(0,1),4)):
   for offset in offsets:
    m=board();record=bytearray(m.read(a,length));record[offset]^=1;m.put(a,record+crc(record))
    equal(exchange(m)[1][pos],2);no_write(m)
 check('shape-and-CRC-are-independent',shapes)
 def differences():
  m=board();record=bytearray(m.read(d['nv_backup'],171));record[163]^=32
  m.put(d['nv_backup'],record+crc(record));m.put(d['soc_backup'],soc_record(11000))
  equal(exchange(m)[1],bytes([1,1,1,2,1,1,2,255,255,0]));no_write(m)
  m=board();m.put(d['nv_backup']+173,b'\0'*83);m.put(d['soc_backup']+22,b'\0'*234)
  equal(exchange(m)[1][3],1);equal(exchange(m)[1][6],1)
  m.put(d['soc_backup'],b'\xff'*255+b'\0');equal(exchange(m)[1][5],2);no_write(m)
 check('valid-differences-and-unused-padding',differences)
 def reserved():
  for value in (0,32,255):
   m=board();m.put(r['group0'],bytes([value]));m.put(facts['sp'],b'\x01\xa6\x01\x5a')
   for a in (d['nv_primary'],d['nv_backup']):
    record=bytearray(m.read(a,171));record[163]=value;m.put(a,record+crc(record))
   cache=m.read(facts['sp'],4);equal(exchange(m)[1][7:],b'\xff\xff\0');equal(m.read(facts['sp'],4),cache)
   no_write(m)
 check('reserved-bit5-no-lock-cache-access',reserved)
 def silent():
  for port in ('R','C'):
   for local in (0,1,21,22,255):
    for target in (0,1,21,22,255):
     if target==local and local<=21:continue
     m=board(local);equal(exchange(m,port,target=target),None);no_write(m)
 check('foreign-FF-invalid-local-silent',silent)
 def malformed():
  for port in ('R','C'):
   for info in (b'',b'\4\0',b'\5'):
    m=board();out=exchange(m,port,info);assert out is None or out[0]!=0
    equal(exchange(m,port)[0],0);no_write(m)
   good=ascii_frame(1,0x64,b'\4')
   for offset,value in ((1,b'21'),(5,b'47'),(9,b'0002'),(13,b'G4')):
    m=board();packet=bytearray(good);packet[offset:offset+len(value)]=value
    packet[-5:-1]=f'{(-sum(packet[1:-5]))&65535:04X}'.encode()
    out=exchange(m,port,raw=packet);assert not out or out[0]!=0
    equal(exchange(m,port)[0],0);no_write(m)
   m=board();out=exchange(m,port,raw=good[:-5]+b'0000\r');assert not out or out[0]!=0
   equal(exchange(m,port)[0],0);no_write(m)
 check('malformed-and-following-recovery',malformed)
 def abi():
  regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  for port in ('R','C'):
   m=board();sp=m.uc.reg_read(UC_ARM_REG_SP)
   for i,reg in enumerate(regs):m.uc.reg_write(reg,0x12345600+i)
   regions=[(r['lcd_meta']-0xc0,0x1ba),(r['state'],r['iap_buffer']-r['state']) if port=='R' else (p['uart0_rx']-0x200,0x400)]
   for a,n in regions:m.put(a,bytes((i*29+17)&255 for i in range(n)))
   before=[m.read(a,n) for a,n in regions];equal(exchange(m,port)[0],0)
   equal([m.read(a,n) for a,n in regions],before);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
   for i,reg in enumerate(regs):equal(m.uc.reg_read(reg),0x12345600+i)
   no_write(m)
 check('ABI-and-C-R-display-canaries',abi)
 def bus():
  for port in ('R','C'):
   for target in (0,7,11):
    boards=[board(i) for i in range(12)]
    equal([i for i,m in enumerate(boards) if exchange(m,port,target=target) is not None],[target])
 check('twelve-packs-exactly-one-response',bus)
 def resets():
  for port in ('R','C'):
   for adr in (0,1,11,21):
    m=board(adr);m.put(r['group0'],bytes([(m.num(r['group0'])&~8)|(8 if positive else 0)]));m.pause=p['reset']
    packet=ascii_frame(adr,0x45,b'\0\6\0');before=m.read(0x25000,0x8000)
    if port=='R':uart0_exchange(m,packet)
    else:
     m.feed(packet);site=facts['hooks']['hook_dispatch'];m.execute(site,site+4)
    equal(m.uc.reg_read(UC_ARM_REG_PC),p['reset']);equal(m.read(0x25000,0x8000),before);no_write(m)
 check('R-C-reset-no-SOC-save',resets)
 def permission():
  for permitted in (False,True):
   m=board();value=m.num(r['group0']);m.put(r['group0'],bytes([value|8 if permitted==positive else value&~8]))
   answer=m.transact(ascii_frame(1,0x45,b'\0\4\x1f'),True)
   equal(ascii_payload(answer,1),(0 if permitted else 5,b''));no_write(m)
 check('positive-power-permission',permission)
 def native_save():
  m=board();m.run(f['serializer']);equal([block for block,_ in m.saves],[0])
  assert f['iap_write'] in m.executed;equal(m.nv_ops,[])
 check('native-parameter-save-unchanged',native_save)
 def refused():
  from .storage_diagnostics import discover_diagnostics,source_diagnostics
  bad=copy.deepcopy(facts);bad['ram']['iap_buffer']+=4
  try:discover_diagnostics(original,bad)
  except ValueError:pass
  else:raise AssertionError('wrong IAP buffer accepted')
  try:source_diagnostics('unknown source')
  except ValueError:pass
  else:raise AssertionError('unknown payload source accepted')
 check('unknown-source-and-buffer-ABI-refused',refused)
 if positive:
  def bit4_reserved():
   for value in (0xff,0xef,0x08,0x18):
    for port in ('R','C'):
     m=board();m.put(r['group0'],bytes([value]));before=m.read(0x23000,0xa000)
     packet=ascii_frame(m.num(r['address']),0x45,b'\0\4\x1f')
     answer=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
     equal(ascii_payload(answer,m.num(r['address'])),(0,b''))
     equal(m.num(r['group0']),value);equal(m.read(0x23000,0xa000),before);no_write(m)
   m=board();equal(m.num(r['group0']),255)
   equal(ascii_payload(m.transact(ascii_frame(1,0x4e,bytes.fromhex('07EA0A18010203')),True),1),(0,b''));no_write(m)
  check('reserved-bit4-and-FF-no-power-NVM',bit4_reserved)
 equal({t['name'] for t in rows},set(REQUIRED))
 return rows
