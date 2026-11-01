"""Mandatory native wire-path checks for addressed remote diagnostics.

Only EEPROM/I2C and flash hardware are synthetic. Request parsing, cursor,
serialization, classification, CRC, encoding and UART1 IRQ execute real Thumb.
"""
import copy
from .machine import Machine,ascii_frame
from .marker_uart0_tests import uart0_exchange
from .selftest import ascii_payload
from .service_tests import crc,soc_record
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
 UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
 UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_PRIMASK)

REQUIRED=tuple('remote_diagnostics-'+n for n in (
 'MNT05-capabilities-and-old-64-04','all-22-addresses-both-ports-no-enable-bits',
 'active-calibration-signed-BE-snapshot','stored-calibration-both-pages-raw-LE',
 'calibration-classes-and-native-CRC-independent','SOC-mirror-classes-choice-and-raw',
 'SOC-native-acceptance-independent-of-shape','live-energy-full-width-and-capacity',
 'foreign-FF-and-invalid-local-silent','malformed-header-length-checksum-hex-recovery',
 'history-empty-oldest-next-shared-cursor','history-500-wrap-and-last-flag',
 'history-read-failure-cursor-rollback','history-wire-212-checksum-and-read-ABI',
 'read-only-no-calibration-repair-save-or-RTC','ABI-SP-PRIMASK-and-port-canaries',
 'bounded-RAM-snapshots-unmasked-hardware','history-IRQ-coexistence',
 'no-new-hooks-or-RAM-and-prefix-allowlist','altered-role-and-source-refused'))


def history_record(index):return bytes([24])+bytes((index+i)&255 for i in range(1,94))


class RemoteMachine(Machine):
 """A bounded synthetic 500-record EEPROM attached at the proven I2C role."""
 def __init__(self,image,facts):
  super().__init__(image,facts)
  self.remote=facts['remote_diagnostics'];self.history_reads=[];self.fail_history=False
  self.masked_run=0;self.max_masked_run=0;self.snapshot_observation=False
  self.raw_reads=[];self.history_irq_data=None;self.extra_callback=None;self.callback=self._remote_callback
 def _remote_callback(self,m,pc):
  d=self.remote
  if pc==d['history_transfer'] and self.history_irq_data is not None:
   self.inject=self.history_irq_data;self.history_irq_data=None;self.uc.emu_stop();return True
  if self.snapshot_observation:
   if self.uc.reg_read(UC_ARM_REG_PRIMASK):
    self.masked_run+=1;self.max_masked_run=max(self.max_masked_run,self.masked_run)
   else:self.masked_run=0
  if pc==d['history_transfer'] and self.num(d['history_control'])==0xa4:
   assert self.uc.reg_read(UC_ARM_REG_R0)==1,'EEPROM write mode'
   assert self.num(d['history_control']+0x8c)==94,'EEPROM length'
   offset=self.num(d['history_control']+2,2)
   assert offset%128==0 and offset//128<500,'EEPROM record stride/range'
   if self.snapshot_observation:assert not self.uc.reg_read(UC_ARM_REG_PRIMASK),'masked EEPROM read'
   self.history_reads.append((offset//128,94,1))
   if not self.fail_history:self.put(d['history_data'],history_record(offset//128))
   self.ret(0 if self.fail_history else 1);return True
  storage=self.facts.get('storage_diagnostics',self.facts.get('cutoff'))
  if storage and pc==storage['flash_read']:
   if self.snapshot_observation:assert not self.uc.reg_read(UC_ARM_REG_PRIMASK),'masked flash read'
   self.raw_reads.append((self.uc.reg_read(UC_ARM_REG_R0),self.uc.reg_read(UC_ARM_REG_R1),self.uc.reg_read(UC_ARM_REG_R2)))
  return bool(self.extra_callback and self.extra_callback(m,pc))


def calibration_record():
 record=bytearray([0xa0,51,0x1c])+bytearray((i*7+3)&255 for i in range(48))
 return bytes(record)+crc(record)


def seed_board(image,facts,adr=1):
 m=RemoteMachine(image,facts);m.defaults(adr);m.run(m.f['serializer'])
 d=m.remote;r=m.r
 record=m.read(r['iap_buffer'],171)
 store=facts.get('storage_diagnostics',facts.get('cutoff'))
 for a in (store['nv_primary'],store['nv_backup']):m.put(a,record+crc(record)+b'\xff'*83)
 for a in (d['cal_primary'],d['cal_backup']):m.put(a,calibration_record()+b'\xff'*203)
 for a in (store['soc_primary'] if 'soc_primary' in store else facts['service']['soc_primary'],store['soc_backup'] if 'soc_backup' in store else facts['service']['soc_backup']):m.put(a,soc_record()+b'\xff'*232)
 m.put(d['event'],b'\xff');m.put(d['cell_count'],b'\x10')
 for i in range(16):m.put(d['cell_gains']+12*i,(40000+i*123).to_bytes(2,'little'))
 for role,value in (('voltage0',12400),('voltage1',38750),('p58',28000),('p59',26000)):m.put(d[role],value.to_bytes(2,'little'))
 for role,values in (('current_a',(-2147483000,-12345678,-456789,61000,62000)),('current_b',(123456789,98765432,123456,62000,61000))):
  a=d[role]
  for off,value in zip((0,4,8,12,14),values):m.put(a+off,value.to_bytes(4 if off<12 else 2,'little',signed=off<12))
 for off,value,n in ((12,24000,2),(14,29000,2),(16,827,2),(0x58,0x12345678,4),(0x5c,0xfedcba98,4)):m.put(d['measure']+off,value.to_bytes(n,'little'))
 m.saves.clear();m.nv_ops.clear();m.flash_ops.clear();m.executed.clear();m.raw_reads.clear()
 return m


def query(m,port='C',info=b'\5',target=None,command=0x64,raw=None,wire=False):
 adr=m.num(m.r['address']);packet=raw if raw is not None else ascii_frame(adr if target is None else target,command,info)
 out=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
 return out if wire else ascii_payload(out,adr) if out else None


def validate_remote(original,patched,facts,build):
 rows=[];r=facts['ram'];f=facts['functions'];d=facts['remote_diagnostics'];storage=facts.get('storage_diagnostics',facts.get('cutoff'))
 socbase=storage.get('soc_primary',facts.get('service',{}).get('soc_primary'))
 def equal(a,b):assert a==b,(a,b)
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('remote_diagnostics-'+name+': '+str(exc)) from exc
  rows.append(dict(name='remote_diagnostics-'+name,passed=True))
 def board(adr=1):return seed_board(patched,facts,adr)
 def no_write(m):
  equal(m.saves,[]);equal(m.nv_ops,[]);equal(m.flash_ops,[]);equal(m.rtc_transfers,[])
  for a in (f['iap_read'],f['iap_write'],f['iap_erase'],f['iap_program'],f['capacity_save'],d['cal_save'],d['cal_load'],d['soc_load'],d['history_oem']):assert a not in m.executed,hex(a)
 def contracts():
  equal((build['info_format'],build['info_bytes']),(5,21))
  for port in ('R','C'):
   m=board();rtn,data=query(m,port,b'\3');equal((rtn,len(data),data[:4],data[19:]),(0,21,b'MNT\5',b'\0\x0f'))
   equal(query(m,port,b'\4'),(0,bytes([1,1,1,1,1,1,1,255,255,0]) if build['patch_version'].startswith('1.5') else bytes([1,1,1,1,1,1,1,0,0,6])))
 check('MNT05-capabilities-and-old-64-04',contracts)
 def addresses():
  for adr in range(22):
   for port in ('R','C'):
    m=board(adr);m.put(r['group0'],b'\0')
    for info,n in ((b'\5',72),(b'\5\0',72),(b'\5\1',58),(b'\5\2',58),(b'\6',68)):
     result=query(m,port,info);assert result is not None,(adr,port,info);equal((result[0],len(result[1])),(0,n))
    if port=='C':
     m.put(d['history_count'],b'\1\0');equal(query(m,port,b'\0\0',command=0x4b)[0],0);equal(m.history_reads,[(0,94,1)])
    no_write(m)
 check('all-22-addresses-both-ports-no-enable-bits',addresses)
 def active():
  for port in ('R','C'):
   m=board();expected=b'\1\0\x1c\x10'
   expected+=b''.join(m.read(d['cell_gains']+i*12,2)[::-1] for i in range(16))
   for a,n in ((d['voltage0'],2),(d['voltage1'],2),(d['current_a']+12,2),(d['current_b']+12,2),(d['current_a']+4,4),(d['current_b']+4,4),(d['current_a']+14,2),(d['current_b']+14,2),(d['current_a'],4),(d['current_b'],4),(d['current_a']+8,4),(d['current_b']+8,4)):expected+=m.read(a,n)[::-1]
   equal(query(m,port),(0,expected));equal(query(m,port,b'\5\0'),(0,expected));no_write(m)
 check('active-calibration-signed-BE-snapshot',active)
 def stored():
  for port in ('R','C'):
   m=board()
   for page,a in ((1,d['cal_primary']),(2,d['cal_backup'])):
    record=bytearray(calibration_record());record[45:47]=(54321).to_bytes(2,'little');record[51:]=crc(record[:51]);m.put(a,record)
    equal(query(m,port,bytes([5,page])),(0,bytes([1,page,1,1,51])+bytes(record)))
   equal(m.num(d['current_b']+12,2),62000);no_write(m)
 check('stored-calibration-both-pages-raw-LE',stored)
 def calclasses():
  for port in ('R','C'):
   for page,a in ((1,d['cal_primary']),(2,d['cal_backup'])):
    for kind in (0,1,2):
     m=board()
     if kind==0:m.put(a,b'\xff'*256)
     if kind==2:m.put(a+51,b'\0\0')
     data=query(m,port,bytes([5,page]))[1];equal(data[2],kind);equal(data[3],int(kind==1));no_write(m)
    for length in (2,20,52,250,251):
     m=board();record=bytearray((i*3)&255 for i in range(256));record[0]=0x99;record[1]=length
     if length<=250:record[length:length+2]=crc(record[:length])
     m.put(a,record);data=query(m,port,bytes([5,page]))[1]
     equal(data[2:5],bytes([2,int(length<=250),length]));equal(data[5:],bytes(record[:53]));no_write(m)
 check('calibration-classes-and-native-CRC-independent',calclasses)
 def socclasses():
  for port in ('R','C'):
   for primary in range(3):
    for backup in range(3):
     m=board()
     for a,kind in ((socbase,primary),(socbase+4096,backup)):
      if kind==0:m.put(a,b'\xff'*256)
      if kind==2:m.put(a+20,b'\0\0')
     data=query(m,port,b'\6')[1]
     equal(data[:6],bytes([1,primary,backup,int(primary==backup==1),int(primary==1)+2*int(backup==1),1 if primary==1 else 2 if backup==1 else 0]))
     equal(data[24:46],m.read(socbase,22));equal(data[46:],m.read(socbase+4096,22));no_write(m)
   m=board();m.put(socbase+4096,soc_record(11000));equal(query(m,port,b'\6')[1][3],2)
 check('SOC-mirror-classes-choice-and-raw',socclasses)
 def socshape():
  for port in ('R','C'):
   for length in (2,19,21,250,251):
    m=board();record=bytearray((i*5)&255 for i in range(256));record[0]=0x44;record[1]=length
    if length<=250:record[length:length+2]=crc(record[:length])
    m.put(socbase,record);data=query(m,port,b'\6')[1]
    equal(data[1],2);equal(data[4:6],bytes([3 if length<=250 else 2,1 if length<=250 else 2]));no_write(m)
 check('SOC-native-acceptance-independent-of-shape',socshape)
 def live():
  for port in ('R','C'):
   m=board();data=query(m,port,b'\6')[1]
   equal(data[6:24],b''.join(value.to_bytes(n,'big') for value,n in ((28000,2),(26000,2),(0x12345678,4),(0xfedcba98,4),(24000,2),(29000,2),(827,2))));no_write(m)
   for charged,discharged in ((64999,65000),(65000,65001),(65536,0xffffffff)):
    current=board(0);native=seed_board(original,facts,0)
    for model in (current,native):
     model.put(d['measure']+0x58,charged.to_bytes(4,'little'));model.put(d['measure']+0x5c,discharged.to_bytes(4,'little'))
    old=query(native,port,b'\0',command=0x42);actual=query(current,port,b'\0',command=0x42)
    equal(actual,old);equal(actual[0],0);equal(actual[1][-4:],b''.join((v if v<65000 else 6500).to_bytes(2,'big') for v in (charged,discharged)))
    equal(query(current,port,b'\6')[1][10:18],charged.to_bytes(4,'big')+discharged.to_bytes(4,'big'));no_write(current)
 check('live-energy-full-width-and-capacity',live)
 def silent():
  for port in ('R','C'):
   for local in (0,1,21,22,255):
    for target in (0,1,21,22,255):
     if local==target and local<=21:continue
     for info in (b'\5',b'\5\1',b'\6'):
      m=board(local);equal(query(m,port,info,target),None);no_write(m)
   if port=='C':
    for target in (0,2,255):
     m=board(1);equal(query(m,port,b'\0\0',target,command=0x4b),None);equal(m.history_reads,[])
 check('foreign-FF-and-invalid-local-silent',silent)
 def malformed():
  for port in ('R','C'):
   for info in (b'\5\3',b'\5\xff',b'\5\0\0',b'\6\0',b'\6\1'):
    m=board();out=query(m,port,info);assert out is None or out==(5,b''),out
    equal(query(m,port)[0],0);no_write(m)
   for info in (b'\5',b'\5\1',b'\6'):
    good=ascii_frame(1,0x64,info)
    for offset,value in ((1,b'21'),(5,b'47'),(9,b'0002'),(13,b'G5'),(15,b'G1')):
     if offset>=len(good)-5:continue
     m=board();packet=bytearray(good);packet[offset:offset+len(value)]=value
     packet[-5:-1]=f'{(-sum(packet[1:-5]))&65535:04X}'.encode()
     out=query(m,port,raw=packet);assert out is None or out[0]!=0,(port,packet,out)
     equal(query(m,port)[0],0);no_write(m)
    m=board();out=query(m,port,raw=good[:-5]+b'0000\r');assert out is None or out[0]!=0
    equal(query(m,port)[0],0)
  for info in (b'',b'\0',b'\0\0\0',b'\0'*6,b'\0'*30):
   m=board();m.put(d['history_cursor'],b'\7\0');equal(query(m,info=info,command=0x4b),(5,b''));equal(m.history_reads,[]);equal(m.num(d['history_cursor'],2),7)
  good=ascii_frame(1,0x4b,b'\0\0')
  for offset,value in ((1,b'21'),(5,b'47'),(9,b'0004'),(13,b'G0'),(15,b'0G')):
   m=board();m.put(d['history_cursor'],b'\7\0');m.put(d['history_count'],b'\3\0');packet=bytearray(good);packet[offset:offset+len(value)]=value
   packet[-5:-1]=f'{(-sum(packet[1:-5]))&65535:04X}'.encode()
   out=query(m,command=0x4b,raw=packet);assert out is None or out[0]!=0,(packet,out)
   equal(m.history_reads,[]);equal(m.num(d['history_cursor'],2),7);equal(query(m)[0],0)
  m=board();m.put(d['history_count'],b'\3\0');m.put(d['history_cursor'],b'\7\0');out=query(m,command=0x4b,raw=good[:-5]+b'0000\r')
  assert out is None or out[0]!=0;equal(m.history_reads,[]);equal(m.num(d['history_cursor'],2),7)
 check('malformed-header-length-checksum-hex-recovery',malformed)
 def setring(m,count,start=0,cursor=0):
  for key,value in (('history_count',count),('history_start',start),('history_cursor',cursor)):m.put(d[key],value.to_bytes(2,'little'))
 def history():
  m=board();setring(m,0,0,7);equal(query(m,info=b'\0\0',command=0x4b),(0,b''));equal(m.history_reads,[]);equal(m.num(d['history_cursor'],2),7)
  setring(m,3)
  for mode,index,last in ((0,0,0),(1,1,0),(255,2,1),(1,0,0)):
   rtn,data=query(m,info=bytes([0xab,mode]),command=0x4b);equal((rtn,data[:4],data[4:]),(0,bytes([1,last])+b'\7\xe8',history_record(index)[1:]))
  # UART0 and UART1 really use the same original cursor.
  equal(query(m,'R',b'\0\1',command=0x4b)[0],0);equal(m.num(d['history_cursor'],2),1)
  equal(query(m,info=b'\0\1',command=0x4b)[1][1],1);equal(m.num(d['history_cursor'],2),2)
 check('history-empty-oldest-next-shared-cursor',history)
 def wrap():
  m=board();setring(m,500,499)
  for mode,index,last in ((0,499,0),(1,0,0)):
   data=query(m,info=bytes([0,mode]),command=0x4b)[1];equal(data[1],last);equal(m.history_reads[-1][0],index)
  m.put(d['history_cursor'],(498).to_bytes(2,'little'));equal(query(m,info=b'\0\1',command=0x4b)[1][1],1);equal(m.history_reads[-1][0],498)
 check('history-500-wrap-and-last-flag',wrap)
 def failed():
  m=board();setring(m,3);equal(query(m,info=b'\0\0',command=0x4b)[0],0)
  m.fail_history=True;equal(query(m,info=b'\0\1',command=0x4b),(8,b''));equal(m.num(d['history_cursor'],2),0)
  m.fail_history=False;equal(query(m,info=b'\0\1',command=0x4b)[0],0);equal(m.history_reads[-1][0],1)
  setring(m,3,0,2);m.fail_history=True;equal(query(m,info=b'\0\0',command=0x4b),(8,b''));equal(m.num(d['history_cursor'],2),2)
 check('history-read-failure-cursor-rollback',failed)
 def wire():
  m=board();setring(m,3);raw=query(m,info=b'\0\0',command=0x4b,wire=True)
  equal((len(raw),raw[9:13]),(212,b'20C2'));equal(int(raw[-5:-1],16),(-sum(raw[1:-5]))&65535);equal(m.history_reads,[(0,94,1)]);no_write(m)
 check('history-wire-212-checksum-and-read-ABI',wire)
 def readonly():
  for port in ('R','C'):
   m=board();before=m.read(0x23000,0xa000);ram=m.read(d['cell_gains'],16*12);event=m.num(d['event']);params=m.payload()
   for info in (b'\5',b'\5\1',b'\5\2',b'\6'):equal(query(m,port,info)[0],0)
   equal(m.read(0x23000,0xa000),before);equal(m.read(d['cell_gains'],16*12),ram);equal(m.num(d['event']),event);equal(m.payload(),params);no_write(m)
 check('read-only-no-calibration-repair-save-or-RTC',readonly)
 def abi():
  regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  for port in ('R','C'):
   for mask in (0,1):
    for info,command in ((b'\5',0x64),(b'\5\1',0x64),(b'\6',0x64),(b'\0\0',0x4b)):
     if port=='R' and command==0x4b:continue
     m=board();setring(m,3);sp=m.uc.reg_read(UC_ARM_REG_SP)
     for i,reg in enumerate(regs):m.uc.reg_write(reg,0x12345600+i)
     m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
     regions=[(r['lcd_meta']-0xc0,0x1ba)]
     other=facts['marker_uart0'];regions.append((other['uart0_state'],other['uart0_rx']-other['uart0_state']) if port=='C' else (r['state'],r['iap_buffer']-r['state']))
     for a,n in regions:m.put(a,bytes((i*29+17)&255 for i in range(n)))
     before=[m.read(a,n) for a,n in regions]
     if port=='C':
      # Check the handler boundary: unchanged native UART1 sender uses CPSIE.
      m.feed(ascii_frame(1,command,info));m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
      equal(m.run(build['entries']['hook_uart1']),0)
     else:equal(query(m,port,info,command=command)[0],0)
     equal([m.read(a,n) for a,n in regions],before);equal(m.uc.reg_read(UC_ARM_REG_SP),sp);equal(m.uc.reg_read(UC_ARM_REG_PRIMASK),mask)
     for i,reg in enumerate(regs):equal(m.uc.reg_read(reg),0x12345600+i)
     no_write(m)
 check('ABI-SP-PRIMASK-and-port-canaries',abi)
 def bounded():
  for port in ('R','C'):
   for info in (b'\5',b'\6'):
    m=board();m.snapshot_observation=True;equal(query(m,port,info)[0],0)
    assert 0<m.max_masked_run<1200,m.max_masked_run;equal(m.uc.reg_read(UC_ARM_REG_PRIMASK),0);no_write(m)
 check('bounded-RAM-snapshots-unmasked-hardware',bounded)
 def coexist():
  for fail in (False,True):
   m=board();setring(m,3);m.history_irq_data=ascii_frame(1,0x51);m.fail_history=fail
   result=query(m,info=b'\0\0',command=0x4b);equal(result[0],8 if fail else 0);assert m.interrupted
   equal(len(result[1]),0 if fail else 97);equal(m.history_reads,[(0,94,1)]);equal(query(m)[0],0);no_write(m)
 check('history-IRQ-coexistence',coexist)
 def boundaries():
  expected=5 if build['patch_version'].startswith('1.5') else 21;equal(len(build['hooks']),expected)
  equal(build['ram_bytes'],0 if expected==5 else 4)
  allowed={a for site in build['hooks'].values() for a in range(site,site+4)}
  if expected==21:allowed.update(range(facts['cutoff']['zero_size_offset'],facts['cutoff']['zero_size_offset']+4))
  if build['hard_stop'].get('changed'):allowed.add(build['hard_stop']['offset'])
  assert all(i in allowed or a==b for i,(a,b) in enumerate(zip(original.app,patched.app)))
 check('no-new-hooks-or-RAM-and-prefix-allowlist',boundaries)
 def refused():
  from .remote_diagnostics import discover_remote,source_remote
  for role,off in (('cal_save',0x14),('history_read',0xe),('history_select',0x34),('soc_save',0x16)):
   app=bytearray(original.app);app[d[role]+off]^=1;bad=original.with_app(app)
   try:discover_remote(bad,copy.deepcopy(facts))
   except ValueError:pass
   else:raise AssertionError('altered remote role accepted: '+role)
  from .thumb import encode_bl
  for a in (d['soc_save']+0x60,d['soc_load']+4):
   app=bytearray(original.app);app[a:a+4]=encode_bl(a,d['cal_save'])
   try:discover_remote(original.with_app(app),copy.deepcopy(facts))
   except ValueError:pass
   else:raise AssertionError('wrong SOC IAP callee accepted')
  for role in ('learned','words','iap_buffer'):
   bad=copy.deepcopy(facts);bad['ram'][role]+=4
   try:discover_remote(original,bad)
   except ValueError:pass
   else:raise AssertionError('altered RAM role accepted: '+role)
  try:source_remote('unknown source')
  except ValueError:pass
  else:raise AssertionError('unknown remote source accepted')
 check('altered-role-and-source-refused',refused)
 equal({row['name'] for row in rows},set(REQUIRED))
 return rows
