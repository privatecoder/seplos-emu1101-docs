"""Full-profile service tests: actual Thumb code, raw NVM peripheral model.

No serial device is opened. Expected records and CRC are independently encoded.
IRQ, partial writes, readback corruption and the native IAP caller context are
checked separately; suite names form part of the CLI publication contract.
"""
from .machine import Machine,ascii_frame,PowerLoss
from .marker_uart0_tests import uart0_exchange
from .selftest import ascii_payload
from unicorn.arm_const import (UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_PRIMASK,
 UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,
 UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)

REQUIRED=tuple('service-'+s for s in (
 'layout-and-two-unique-hooks','diagnostics-all-addresses-R-C-read-only',
 'diagnostics-classes-and-CRC-no-repair','diagnostics-shape-not-just-CRC',
 'diagnostics-mismatch-locks-and-padding','diagnostics-cache-observation-only',
 'diagnostics-foreign-and-FF-silent','diagnostics-malformed-and-recovery',
 'diagnostics-ABI-and-other-port-canaries','twelve-packs-one-diagnostic-response',
 'restart-R-C-native-record-and-no-ACK','restart-failure-each-NVM-step',
 'restart-readback-corruption','restart-power-loss-keeps-a-verified-copy',
 'restart-IRQ-mask-and-failure-ABI','restart-C-permission-and-R-recovery',
 'restart-foreign-and-FF-no-save','automatic-SOC-save-stays-OEM',
 'saved-SOC-native-boot-load','checkpoint-failure-keeps-runtime-checkpoint',
))

def crc(data):
 value=65535
 for byte in data:
  value^=byte
  for _ in range(8):value=(value>>1)^(0xa001 if value&1 else 0)
 return value.to_bytes(2,'little')

def soc_record(remaining=12000):
 data=b'\xa0\x14'+remaining.to_bytes(2,'little')+(28000).to_bytes(2,'little')
 data+=(123456).to_bytes(4,'little')+(654321).to_bytes(4,'little')
 data+=b'\x17\0\x2d\0\x43\0'
 return data+crc(data)+b'\xff\xff'

def validate_service(original,patched,facts,report):
 r=facts['ram'];f=facts['functions'];s=facts['service'];d=facts['cutoff'];p=facts['power_rtc'];rows=[]
 def equal(a,b):assert a==b,(a,b)
 def check(short,fn):
  name='service-'+short
  try:fn()
  except Exception as exc:raise AssertionError(name+': '+str(exc)) from exc
  rows.append(dict(name=name,passed=True))
 def board(adr=1):
  m=Machine(patched,facts);m.defaults(adr)
  m.put(r['group0'],bytes([m.num(r['group0'])|8]))
  m.run(f['serializer']);m.nv_step=0;m.nv_ops.clear();m.saves.clear()
  base=r['learned']-14
  for off,value,width in ((12,12000,2),(14,28000,2),(16,428,2),(0x54,111,2),(0x58,123456,4),(0x5c,654321,4),(0x60,23,2)):
   m.put(base+off,value.to_bytes(width,'little'))
  m.put(r['coulomb_max']+24,b'\x2d\0\x43\0')
  return m
 def exchange(m,port,cmd,info,target=None):
  adr=m.num(r['address']);packet=ascii_frame(adr if target is None else target,cmd,info)
  raw=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
  return ascii_payload(raw,adr) if raw else None
 def diag(m,port='C',target=None):return exchange(m,port,0x64,b'\4',target)
 def reset(m,port='C',target=None,first=0,version=None,primask=None):
  adr=m.num(r['address']);packet=ascii_frame(adr if target is None else target,0x45,bytes([first,6,0]))
  if version is not None:
   packet=bytearray(packet);packet[1:3]=f'{version:02X}'.encode();packet[-5:-1]=f'{(-sum(packet[1:-5]))&65535:04X}'.encode();packet=bytes(packet)
  m.pause=p['reset'];m.output.clear()
  if port=='R':
   if primask is not None:m.uc.reg_write(UC_ARM_REG_PRIMASK,primask)
   raw=uart0_exchange(m,packet)
   m.service_reset_primask=m.uc.reg_read(UC_ARM_REG_PRIMASK)
  else:
   m.feed(packet)
   if primask is not None:m.uc.reg_write(UC_ARM_REG_PRIMASK,primask)
   site=facts['hooks']['hook_dispatch'];m.execute(site,site+4)
   m.service_reset_primask=m.uc.reg_read(UC_ARM_REG_PRIMASK)
   if m.uc.reg_read(UC_ARM_REG_PC)==m.pause:return None
   m.pause=None;raw=m.drain()
  if m.uc.reg_read(UC_ARM_REG_PC)==p['reset']:return None
  return ascii_payload(raw,adr) if raw else None
 def seed_soc(m,remaining=12000):
  for a in (s['soc_primary'],s['soc_backup']):m.put(a,soc_record(remaining))
 def layout():
  assert report['extended_diagnostics'] and report['checkpoint_before_reset']
  configurable=report.get('configurable_hard_stop',False)
  equal(report['patch_version'],'1.6.3')
  equal(report['image_flags']&0xfe,0xfe)
  equal((report['info_format'],report['info_bytes']),(4,19))
  equal(len(report['hooks']),len(set(report['hooks'].values())))
  equal(s['soc_write_site'],s['hooks']['hook_service_soc_iap'])
 check('layout-and-two-unique-hooks',layout)
 def all_addresses():
  for adr in range(22):
   for port in ('R','C'):
    m=board(adr);seed_soc(m);m.put(r['group0'],b'\0')
    before=m.read(d['nv_primary'],0x8000);cache=m.read(d['ram'],4);payload=m.payload()
    equal(diag(m,port),(0,bytes([1,1,1,1,1,1,1,0,0,6])))
    equal(m.read(d['nv_primary'],0x8000),before);equal(m.read(d['ram'],4),cache);equal(m.payload(),payload)
    equal(m.nv_ops,[]);equal(m.saves,[]);assert f['iap_read'] not in m.executed
 check('diagnostics-all-addresses-R-C-read-only',all_addresses)
 def classes():
  for port in ('R','C'):
   for primary in range(3):
    for backup in range(3):
     m=board();seed_soc(m)
     for pair,length in (((d['nv_primary'],d['nv_backup']),171),((s['soc_primary'],s['soc_backup']),20)):
      for a,kind in zip(pair,(primary,backup)):
       if kind==0:m.put(a,b'\xff'*256)
       elif kind==2:m.put(a+length,bytes([m.num(a+length)^1]))
     before=m.read(d['nv_primary'],0x8000)
     rtn,data=diag(m,port);equal(rtn,0)
     equal(data[1:4],bytes([primary,backup,int(primary==backup==1)]))
     equal(data[4:7],data[1:4]);equal(data[7:9],bytes([0 if k==1 else 255 for k in (primary,backup)]))
     equal(m.read(d['nv_primary'],0x8000),before);equal(m.nv_ops,[])
 check('diagnostics-classes-and-CRC-no-repair',classes)
 def shapes():
  for a,length,offsets,pos in ((d['nv_primary'],171,(0,1,2,123,151,162),1),(s['soc_primary'],20,(0,1),4)):
   for off in offsets:
    m=board();seed_soc(m);record=bytearray(m.read(a,length));record[off]^=1
    m.put(a,record+crc(record));equal(diag(m)[1][pos],2);equal(m.nv_ops,[])
 check('diagnostics-shape-not-just-CRC',shapes)
 def mismatch():
  m=board();seed_soc(m)
  m.put(s['soc_backup'],soc_record(11000))
  record=bytearray(m.read(d['nv_backup'],171));record[163]&=~32;m.put(d['nv_backup'],record+crc(record))
  equal(diag(m)[1],bytes([1,1,1,2,1,1,2,0,1,6]))
  m=board();seed_soc(m)
  m.put(d['nv_backup']+173,b'\x12\x34\x56');m.put(s['soc_backup']+22,b'\0'*234)
  equal(diag(m)[1][3],1);equal(diag(m)[1][6],1)
  # A non-FF byte after an otherwise erased record makes it invalid, not erased.
  m.put(s['soc_backup'],b'\xff'*255+b'\0');equal(diag(m)[1][5],2)
 check('diagnostics-mismatch-locks-and-padding',mismatch)
 def cache():
  for latch in (0,1,0xff):
   for consistent in (0,1,2):
    for magic in (0,0xa6):
     m=board();value=bytes([latch,magic,consistent,0x5a]);m.put(d['ram'],value)
     equal(diag(m)[1][9],int(latch!=0)+2*int(consistent==1)+4*int(magic==0xa6));equal(m.read(d['ram'],4),value)
 check('diagnostics-cache-observation-only',cache)
 def foreign():
  for port in ('R','C'):
   for target in (0,2,22,255):
    m=board();equal(diag(m,port,target),None);equal(m.nv_ops,[])
 check('diagnostics-foreign-and-FF-silent',foreign)
 def malformed():
  for port in ('R','C'):
   for info in (b'',b'\4\0'):
    m=board();out=exchange(m,port,0x64,info);assert not out or out[0]!=0
    equal(diag(m,port)[0],0);equal(m.nv_ops,[])
   for offset,value in ((1,b'21'),(5,b'47'),(9,b'0002'),(13,b'G4')):
    m=board();packet=bytearray(ascii_frame(1,0x64,b'\4'));packet[offset:offset+len(value)]=value
    packet[-5:-1]=f'{(-sum(packet[1:-5]))&65535:04X}'.encode()
    raw=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
    assert not raw or ascii_payload(raw,1)[0]!=0
    equal(diag(m,port)[0],0);equal(m.nv_ops,[])
 check('diagnostics-malformed-and-recovery',malformed)
 regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
 def prime_regs(m):
  for i,reg in enumerate(regs):m.uc.reg_write(reg,0x12345600+i)
  return m.uc.reg_read(UC_ARM_REG_SP)
 def verify_regs(m,sp):
  equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
  for i,reg in enumerate(regs):equal(m.uc.reg_read(reg),0x12345600+i)
 def abi():
  for port in ('R','C'):
   m=board();sp=prime_regs(m)
   a,n=(r['state'],r['iap_buffer']-r['state']) if port=='R' else (p['uart0_rx']-0x200,0x400)
   canary=bytes((i*17+29)&255 for i in range(n));m.put(a,canary)
   equal(diag(m,port)[0],0);verify_regs(m,sp);equal(m.read(a,n),canary)
 check('diagnostics-ABI-and-other-port-canaries',abi)
 def bus():
  for port in ('R','C'):
   for target in (0,7,11):
    boards=[board(i) for i in range(12)]
    equal([i for i,m in enumerate(boards) if diag(m,port,target) is not None],[target])
 check('twelve-packs-one-diagnostic-response',bus)
 def successful():
  for port,first,version in (('C',0,None),('R',0,None),('R',1,0x26)):
   for adr in (0,1,11,21):
    m=board(adr);before=m.read(d['nv_primary'],0x2000)
    equal(reset(m,port,first=first,version=version),None);equal(m.uc.reg_read(UC_ARM_REG_PC),p['reset'])
    for a in (s['soc_primary'],s['soc_backup']):equal(m.read(a,22),soc_record()[:22])
    equal(m.num(s['saved_soc'],2),428);equal(len(m.nv_ops),4);equal(m.read(d['nv_primary'],0x2000),before)
 check('restart-R-C-native-record-and-no-ACK',successful)
 def failures():
  for port in ('R','C'):
   for step in (1,2,3,4):
    m=board();seed_soc(m,7500);m.nv_fail_at={step};sp=prime_regs(m)
    equal(reset(m,port),(8,b''));assert p['reset'] not in m.executed;verify_regs(m,sp)
    equal(m.num(s['saved_soc'],2),111)
    if step<=2:equal(m.read(s['soc_backup'],22),soc_record(7500)[:22])
    else:equal(m.read(s['soc_primary'],22),soc_record()[:22])
 check('restart-failure-each-NVM-step',failures)
 def readback():
  for port in ('R','C'):
   for which in ('primary','backup'):
    m=board();seed_soc(m,7500);target=s['soc_'+which]
    def corrupt(board,pc):
     if pc==d['flash_read'] and board.uc.reg_read(UC_ARM_REG_R0)==target:
      dest=board.uc.reg_read(UC_ARM_REG_R1)
      data=bytearray(board.read(target,24));data[5]^=1;board.put(dest,data);board.ret();return True
     return False
    m.callback=corrupt;equal(reset(m,port),(8,b''));assert p['reset'] not in m.executed
 check('restart-readback-corruption',readback)
 def powerloss():
  for step in (1,2,3,4):
   m=board();seed_soc(m,7500);m.nv_cut_after=step
   try:reset(m)
   except PowerLoss:pass
   else:raise AssertionError('power loss was not injected')
   if step<=2:equal(m.read(s['soc_backup'],22),soc_record(7500)[:22])
   else:equal(m.read(s['soc_primary'],22),soc_record()[:22])
  # Interrupted programming, at each word boundary of either SOC copy.
  for target in (s['soc_primary'],s['soc_backup']):
   for words in range(7):
    m=board();seed_soc(m,7500)
    def partial(board,pc):
     if pc==f['iap_program'] and board.uc.reg_read(UC_ARM_REG_R0)==target:
      source=board.uc.reg_read(UC_ARM_REG_R1);board.put(target,board.read(source,4*words))
      raise PowerLoss('word-boundary power loss')
     return False
    m.callback=partial
    try:reset(m)
    except PowerLoss:pass
    else:raise AssertionError('partial program was not injected')
    intact=s['soc_backup'] if target==s['soc_primary'] else s['soc_primary']
    equal(m.read(intact,22),soc_record(7500 if intact==s['soc_backup'] else 12000)[:22])
 check('restart-power-loss-keeps-a-verified-copy',powerloss)
 def irq():
  for port in ('R','C'):
   for mask in (0,1):
    for failed in (False,True):
     m=board()
     if failed:m.nv_fail_at={2}
     sp=prime_regs(m);reset(m,port,primask=mask)
     # TX drain invokes a synthetic IRQ; inspect mask before that exception.
     assert m.service_reset_primask==mask,(port,mask,failed,m.service_reset_primask)
     if failed:verify_regs(m,sp)
 check('restart-IRQ-mask-and-failure-ABI',irq)
 def permissions():
  m=board();m.put(r['group0'],b'\0');equal(reset(m),(5,b''));equal(m.nv_ops,[])
  m.pause=None;equal(reset(m,'R'),None);equal(m.uc.reg_read(UC_ARM_REG_PC),p['reset']);equal(len(m.nv_ops),4)
 check('restart-C-permission-and-R-recovery',permissions)
 def no_broadcast():
  for port in ('R','C'):
   for target in (0,2,255):
    m=board();out=reset(m,port,target);assert out is None or out[0]!=0
    equal(m.nv_ops,[]);assert p['reset'] not in m.executed
  for local in (22,255):
   m=board(local);equal(reset(m,'R',local),None)
   equal(m.nv_ops,[]);assert p['reset'] not in m.executed
 check('restart-foreign-and-FF-no-save',no_broadcast)
 def automatic():
  m=board();m.run(f['capacity_save'])
  equal(m.saves,[(6,m.read(r['iap_buffer'],20))]);equal(m.nv_ops,[])
  equal(m.num(s['saved_soc'],2),428);assert f['iap_write'] in m.executed
 check('automatic-SOC-save-stays-OEM',automatic)
 def boot_load():
  m=board();reset(m)
  n=Machine(patched,facts);n.put(s['soc_primary'],m.read(s['soc_primary'],8192))
  n.defaults(1)
  # Loader is native, and reads IAP block6; the model obtains the flash record.
  n.run(s['soc_load'])
  base=r['learned']-14
  equal(n.num(base+12,2),12000);equal(n.num(base+14,2),28000)
  equal(n.num(base+0x60,2),23)
 check('saved-SOC-native-boot-load',boot_load)
 def checkpoint():
  m=board();seed_soc(m,7500);m.nv_fail_at={2};before=m.read(r['learned']-14,0x64)
  equal(reset(m),(8,b''));equal(m.read(r['learned']-14,0x64),before)
 check('checkpoint-failure-keeps-runtime-checkpoint',checkpoint)
 equal({t['name'] for t in rows},set(REQUIRED))
 return rows
