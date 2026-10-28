"""Mandatory executable-code regressions for every emitted image.

The original image supplies the independent LCD/ASCII/default/validator oracle.
Only UART FIFO/status and IAP hardware are modeled. Every run is bounded.
"""
import binascii
import hashlib
import random
from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP
from .machine import Machine,frame,ascii_frame,UART


def ascii_payload(response,address=0):
 assert response.startswith(f'~20{address:02X}46'.encode()) and response.endswith(b'\r'),response
 assert int(response[-5:-1],16)==(-sum(response[1:-5]))&65535,'ASCII checksum'
 length=int(response[9:13],16);n=length&0xfff
 assert (-(n+(n>>4)+(n>>8)))&15==length>>12,'ASCII LEN checksum'
 assert len(response)==18+n,'ASCII length'
 return int(response[7:9],16),bytes.fromhex(response[13:-5].decode())


def modbus_frame(body):
 crc=0xffff
 for byte in body:
  crc^=byte
  for _ in range(8):crc=(crc>>1)^(0xa001 if crc&1 else 0)
 return body+crc.to_bytes(2,'little')


def validate(original,patched,facts,build):
 if not __debug__:raise RuntimeError('optimized Python disables assertions; refused')
 passed=[];r=facts['ram'];f=facts['functions']
 def check(name,func):
  try:func()
  except Exception as exc:raise AssertionError(name+': '+str(exc)) from exc
  passed.append({'name':name,'passed':True})
 def board(address=0,stock=False):
  m=Machine(original if stock else patched,facts);m.defaults(address);return m
 def tx(m,data):return m.transact(data,True)
 def equal(a,b):assert a==b,(a,b)
 def query(m,cmd,data=b''):return tx(m,frame(m.num(r['address']),cmd,data))
 def maintenance(m,data):return ascii_payload(tx(m,ascii_frame(0,0x64,data)))
 def lcd_write(m,payload):
  m.put(r['lcd_meta']+18,payload);m.run(f['lcd_write']);return m.num(r['lcd_meta']+9)

 # Immutable OEM bytes, version and canonical complete-app hash are checked too.
 def integrity():
  allowed={a for site in build.get('hooks',facts['hooks']).values() for a in range(site,site+4)}
  if build.get('cutoff'):allowed.update(range(facts['cutoff']['zero_size_offset'],facts['cutoff']['zero_size_offset']+4))
  if build.get('hard_stop',{}).get('changed'):allowed.add(build['hard_stop']['offset'])
  assert all(x==y or a in allowed for a,(x,y) in enumerate(zip(original.app,patched.app)))
  assert len(patched.app)>len(original.app)
  if build.get('configurable_hard_stop'):
   from .thumb import encode_bl
   h=facts['configurable_hardstop'];entry=h['entries']['hook_configurable_hard_stop']
   assert patched.app[h['site']:h['site']+4]==encode_bl(h['site'],entry),'configurable mask hook/code mismatch'
   assert build['image_flags']&128 and bool(build['image_flags']&1)==build['hard_stop_default'],'Hard-Stop image default mismatch'
  else:
   mask=patched.app[build['hard_stop']['offset']]
   assert mask in (0x71,0x73) and int(mask==0x73)==(build['image_flags']&1),'MNT03 Hard-Stop flag/code mismatch'
  assert build['image_flags']&2,'MNT03 Power/RTC capability missing'
  data=bytearray(patched.app);off=build['build_id_offset'];build_id=data[off:off+8];data[off:off+8]=b'UPID0000'
  assert hashlib.sha256(data).digest()[:8]==build_id
 check('guarded-hooks-startup-and-canonical-build-ID' if (build.get('cutoff') or build.get('uart0_marker')) else 'four-hooks-only-and-canonical-build-ID',integrity)

 for address in range(22):
  def addressing(address=address):
   m=board(address);m.put(r['slaves'],b'\x0b');m.put(r['group0']+7,b'\0')
   response=query(m,0x47)
   equal(response,frame(address,0x47,m.payload()+m.read(r['name'],10)))
   equal(m.num(r['slaves']),11)
   assert False in m.direction and m.direction[-1] and not m.num(r['state'])
   assert f['uart1_send'] in m.executed and f['tx_irq'] in m.executed
  check(f'addressed-47-and-stock-RS485-sender-{address:02d}',addressing)
 for command,key in ((0xa2,'string1'),(0xa4,'string2')):
  def identity(command=command,key=key):
   m=board(1);sample=bytes([0,0x55,0xaa,0xff])+bytes(range(26));m.put(r[key],sample)
   equal(query(m,command),frame(1,command,sample));equal(query(m,command,b'\0'),frame(1,0x87))
   assert not m.saves
  check(f'raw-30-byte-identity-{command:02x}',identity)
 for foreign in (0,2,21,22,255):
  def silent(foreign=foreign):
   m=board(1);before=m.payload()
   equal(tx(m,frame(foreign,0xa1,before)),b'');equal(m.payload(),before);equal(m.saves,[])
   assert query(m,0x47)
  check(f'foreign-address-no-write-{foreign}',silent)

 def valid_write():
  m=board(1);p=bytearray(m.payload());p[130]=110
  expected=board(1,True);equal(lcd_write(expected,p),0xa1)
  equal(query(m,0xa1,p),frame(1,0xa1));equal(m.payload(),expected.payload());equal(m.saves,expected.saves)
  assert f['validator'] in m.executed and f['serializer'] in m.executed
  saved=m.payload();m.put(r['words'],bytes(120));m.put(r['small'],bytes(27));m.put(r['group0'],bytes(8));m.run(f['loader']);equal(m.payload(),saved)
 check('A1-real-validator-serializer-OEM-LCD-and-persistent-roundtrip',valid_write)

 def validation_reject():
  m=board(1);before=m.payload();p=bytearray(before);p[1:3]=b'\0\0';p[150]^=0x80
  equal(query(m,0xa1,p),frame(1,0xe2));equal(m.payload(),before);equal(m.saves,[])
 check('A1-invalid-parameter-atomic-no-switch-commit',validation_reject)
 for cmd,data,error in ((0x47,b'x',0x87),(0xa1,b'',0x87),(0xa1,bytes(158),0xe3),(0xa3,b'',0x81),(0xa5,b'',0x81),(0x00,b'',0x81)):
  check(f'command-contract-{cmd:02x}-{len(data)}',lambda cmd=cmd,data=data,error=error:equal(query(board(1),cmd,data),frame(1,error)))
 for index in (0,121,149):
  def marker(index=index):
   m=board(1);p=bytearray(m.payload());p[index]^=1
   equal(query(m,0xa1,p),frame(1,0x83));equal(m.saves,[])
  check(f'A1-invalid-block-marker-{index}',marker)

 def permissions():
  m=board(1);p=bytearray(m.payload());p[150]&=~1
  equal(query(m,0xa1,p),frame(1,0xa1));p[150]|=1
  equal(query(m,0xa1,p),frame(1,0xe3));equal(query(m,0xa1,b''),frame(1,0xe3))
  for cmd in (0x47,0xa2,0xa4):assert query(m,cmd)
  equal(lcd_write(m,p),0xa1);equal(query(m,0xa1,p),frame(1,0xa1))
  m.run(f['loader']);assert m.num(r['group0'])&1
 check('write-self-disable-reject-reenable-OEM-LCD-recovery',permissions)
 for initial in (0xff,0xfb):
  def protected(initial=initial):
   m=board(1);m.put(r['group0'],bytes([initial]));before=m.payload();p=bytearray(before);p[150]^=4
   equal(query(m,0xa1,p),frame(1,0xe3));equal(m.payload(),before);equal(m.saves,[])
  check(f'maintenance-permission-immutable-via-UART1-{initial:02x}',protected)

 for difference in (999,1000,-999,-1000):
  def capacity(difference=difference):
   m=board(1);nominal=m.num(r['words']+116,2);before=nominal+difference;m.put(r['learned'],before.to_bytes(2,'little'))
   equal(query(m,0xa1,m.payload()),frame(1,0xa1));changed=abs(difference)>=1000
   equal([b for b,d in m.saves],[0,6] if changed else [0]);equal(m.num(r['learned'],2),nominal if changed else before)
   if changed:equal(m.num(r['coulomb_max'],4),nominal*3600)
  check(f'capacity-OEM-boundary-{difference}',capacity)

 good=frame(1,0xa1,board(1).payload())
 invalid=[good[:4]+b'x'+good[5:],good[:-1]+b'\0',good[:3]+b'\0'+good[4:],good[:-2],b'\x55\x01',good[:-3]+b'\0\0\xaa']
 for index,bad in enumerate(invalid):
  def framing(bad=bad):
   m=board(1);before=m.payload();equal(tx(m,bad),b'');equal(m.payload(),before);equal(m.saves,[])
   assert query(m,0x47)
  check(f'bad-CRC-framing-truncation-recovery-{index}',framing)
 def overflow():
  m=board(1);m.put(r['tx'],b'Z'*175);before=m.payload();bad=b'\x55'+b'x'*(r['rx_limit']+10)+frame(1,0xa1,before)
  equal(tx(m,bad),b'');equal(m.payload(),before);equal(m.saves,[]);equal(m.read(r['tx'],175),b'Z'*175)
  assert query(m,0x47)
 check('RX-overflow-drop-until-timeout-no-TX-buffer-corruption',overflow)
 def ownership():
  m=board(1);p=m.payload();m.feed(frame(1,0x47));m.feed(frame(1,0xa1,p));m.dispatch(True)
  equal(m.drain(),frame(1,0x47,p+m.read(r['name'],10)));equal(m.saves,[])
 check('ready-frame-ownership-against-competing-write',ownership)
 def interrupt():
  m=board(1);p=bytearray(m.payload());p[130]=110;other=bytearray(p);other[130]=111
  m.interrupt_data=frame(1,0xa1,other);equal(query(m,0xa1,p),frame(1,0xa1))
  assert m.interrupted;equal(m.payload(),p);equal([b for b,d in m.saves],[0])
 check('real-IRQ-during-actual-validator-write-processing',interrupt)
 def fragmentation():
  rng=random.Random(181);m=board(1);req=frame(1,0x47);index=0
  while index<len(req):
   n=rng.randint(1,3);m.feed(req[index:index+n],False);index+=n
  m.timeout=True
  if m.queue:m.run(f['irq'])
  m.dispatch(True);equal(m.drain(),frame(1,0x47,m.payload()+m.read(r['name'],10)))
 check('RX-fragmentation-and-final-timeout',fragmentation)
 def canaries():
  m=board(1);base=r['lcd_meta']-0xc0;sample=bytes((i*31)&255 for i in range(0x1ba));m.put(base,sample)
  name=m.read(r['name'],10);query(m,0x47);query(m,0xa4);query(m,0xa1,m.payload())
  equal(m.read(base,len(sample)),sample);equal(m.read(r['name'],10),name)
 check('UART2-buffer-and-device-name-canaries',canaries)
 def abi():
  m=board(1);regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  values=[0x12345600+n for n in range(len(regs))]
  for reg,v in zip(regs,values):m.uc.reg_write(reg,v)
  sp=m.uc.reg_read(UC_ARM_REG_SP);query(m,0x47)
  equal([m.uc.reg_read(reg) for reg in regs],values);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
 check('call-and-IRQ-callee-register-stack-ABI',abi)
 for cmd in (0x42,0x44,0x51):
  def baseline(cmd=cmd):
   stock=board(stock=True);m=board();request=ascii_frame(0,cmd)
   expected=stock.transact(request);assert expected
   equal(tx(m,request),expected)
  check(f'unchanged-OEM-UART1-ASCII-{cmd:02x}',baseline)

 def modbus_regression():
  original_board=board(stock=True);m=board()
  request=modbus_frame(bytes.fromhex('01030000000C'))
  expected=original_board.transact(request);assert expected
  equal(tx(m,request),expected)
  equal(query(m,0x47),frame(0,0x47,m.payload()+m.read(r['name'],10)))
  equal(tx(m,request),expected)
 check('stock-Modbus-gate-frame-CRC-and-interleaved-binary-service',modbus_regression)

 def info_status():
  m=board();expected=b'MNT'+bytes([build['info_format']])+bytes(facts['oracle']['base_version'])+bytes([build['base_revision'],*map(int,build['patch_version'].split('.'))])+bytes.fromhex(build['build_id'])+bytes([build['image_flags']])
  for marker,slaves in ((0xffffffff,11),(0,0),(0x12345678,7)):
   m.put(0x23000,marker.to_bytes(4,'little'));m.put(r['slaves'],bytes([slaves]))
   equal(maintenance(m,b'\x03'),(0,expected));equal(maintenance(m,b'\x02'),(0,marker.to_bytes(4,'little')+bytes([slaves])))
  equal(m.flash_ops,[]);equal(m.saves,[])
 check('64-03-immutable-MNT'+str(build['info_format']).zfill(2)+'-versus-64-02-complete-state',info_status)
 for address in range(22):
  def addressed_info(address=address):
   m=board(address);m.put(r['group0'],b'\0');m.put(r['slaves'],b'\x0b')
   expected=b'MNT'+bytes([build['info_format']])+bytes(facts['oracle']['base_version'])+bytes([build['base_revision'],*map(int,build['patch_version'].split('.'))])+bytes.fromhex(build['build_id'])+bytes([build['image_flags']])
   before=m.payload()
   for marker in (0xffffffff,0,0x12345678):
    m.put(0x23000,marker.to_bytes(4,'little'))
    response=tx(m,ascii_frame(address,0x64,b'\x03'))
    equal(ascii_payload(response,address),(0,expected));equal(response[9:13],b'8026' if build['info_format']==4 else b'A024')
    equal(m.payload(),before);equal(m.read(0x23000,4),marker.to_bytes(4,'little'));equal(m.num(r['slaves']),11)
   equal(m.flash_ops,[]);equal(m.saves,[])
   equal(query(m,0x47),frame(address,0x47,before+m.read(r['name'],10)))
  check(f'64-03-addressed-pack-{address:02d}-read-only-without-permissions',addressed_info)
 def actions():
  m=board();m.put(r['slaves'],b'\x0b')
  for action in (1,1,0,0):
   rtn,payload=maintenance(m,bytes([action,0xc3,0x5a]));equal(rtn,0)
   equal(payload,(bytes(4) if action else b'\xff'*4)+b'\x0b')
  equal(m.flash_ops,[('program',0x23000,1),('erase',0x23000)])
 check('maintenance-start-stop-idempotent-original-IAP-ABI',actions)
 def start_lock():
  m=board();m.put(r['group0'],bytes([m.num(r['group0'])&~4]));equal(maintenance(m,b'\x01\xc3\x5a'),(5,b''));equal(m.flash_ops,[])
  m.put(0x23000,bytes(4));equal(maintenance(m,b'\x00\xc3\x5a')[0],0);equal(m.read(0x23000,4),b'\xff'*4)
 check('maintenance-start-permission-and-unconditional-exit',start_lock)
 def auto_lock():
  m=board();m.put(r['group0']+7,bytes([m.num(r['group0']+7)|0x20]));equal(maintenance(m,b'\x01\xc3\x5a'),(5,b''));equal(m.flash_ops,[])
 check('maintenance-start-denied-while-automatic-addressing',auto_lock)
 def unknown_marker():
  m=board();m.put(0x23000,b'xV4\x12')
  for action in (0,1):equal(maintenance(m,bytes([action,0xc3,0x5a])),(5,b''))
  equal(m.flash_ops,[])
 check('unknown-marker-never-erased-or-programmed',unknown_marker)
 def iap_failure():
  m=board();m.iap_fail=True;equal(maintenance(m,b'\x01\xc3\x5a'),(5,b''));equal(m.read(0x23000,4),b'\xff'*4)
  m.put(0x23000,bytes(4));equal(maintenance(m,b'\x00\xc3\x5a'),(5,b''));equal(m.read(0x23000,4),bytes(4))
 check('IAP-failure-readback-rejects-false-ACK',iap_failure)
 for address,target in ((0,1),(0,255),(1,0),(1,255)):
  def master_only(address=address,target=target):
   m=board(address);equal(tx(m,ascii_frame(target,0x64,b'\x03')),b'');equal(m.flash_ops,[])
  check(f'64-03-foreign-or-broadcast-silent-{address}-{target}',master_only)
 for address in (1,11,21):
  def slave_maintenance(address=address):
   m=board(address);before=m.payload()
   for marker in (0xffffffff,0,0x12345678):
    m.put(0x23000,marker.to_bytes(4,'little'))
    for target in (address,0,255):
     for data in (b'\x02',b'\x01\xc3\x5a',b'\x00\xc3\x5a'):
      equal(tx(m,ascii_frame(target,0x64,data)),b'')
    equal(m.read(0x23000,4),marker.to_bytes(4,'little'));equal(m.payload(),before)
   equal(m.flash_ops,[]);equal(m.saves,[])
  check(f'slave-{address}-64-status-start-stop-always-silent-without-IAP',slave_maintenance)
 def malformed_slave_info():
  m=board(11);before=m.payload();request=ascii_frame(11,0x64,b'\x03')
  invalid=[request[:-5]+b'0000\r',ascii_frame(11,0x64,b'\x03\0')]
  for offset,value in ((1,b'21'),(5,b'47')):
   body=bytearray(request[1:-5]);body[offset-1:offset+1]=value
   invalid.append(b'~'+body+f'{(-sum(body))&0xffff:04X}'.encode()+b'\r')
  for data in invalid:assert not tx(m,data).startswith(b'~200B4600')
  equal(m.payload(),before);equal(m.flash_ops,[]);equal(m.saves,[])
  equal(ascii_payload(tx(m,request),11)[0],0)
 check('slave-info-rejects-malformed-CRC-length-VER-CID-and-recovers',malformed_slave_info)
 for payload in (b'',b'\x05' if build.get('extended_diagnostics') else b'\x04',b'\x01\xc3\0',b'\x00\xc3\0',b'\x03\0'):
  check('maintenance-invalid-contract-'+payload.hex(),lambda payload=payload:equal(maintenance(board(),payload),(5,b'')))
 def tick():
  m=board();m.put(0x23000,bytes(4));m.put(r['slaves'],b'\x0b');m.run(build['entries']['hook_dip']);equal(m.num(r['slaves']),0)
  # Auto mode preserves effective slaves despite marker.
  m.put(r['group0']+7,bytes([m.num(r['group0']+7)|0x20]));m.put(r['slaves'],b'\x0b');m.run(build['entries']['hook_dip']);equal(m.num(r['slaves']),11)
 check('real-DIP-hook-marker-override-and-auto-exception',tick)
 def shared_bus():
  machines=[board(i) for i in range(12)];p=bytearray(machines[7].payload());p[130]=110
  answers=[tx(m,frame(7,0xa1,p)) for m in machines]
  equal(answers,[frame(7,0xa1) if i==7 else b'' for i in range(12)])
  equal([len(m.saves) for m in machines],[1 if i==7 else 0 for i in range(12)])
 check('twelve-modeled-packs-exactly-one-target-writes',shared_bus)
 def shared_info_bus():
  machines=[board(i) for i in range(12)]
  for target in range(12):
   answers=[tx(m,ascii_frame(target,0x64,b'\x03')) for m in machines]
   equal([i for i,response in enumerate(answers) if response],[target])
   equal(ascii_payload(answers[target],target)[0],0)
  for m in machines:equal(m.flash_ops,[]);equal(m.saves,[])
 check('twelve-modeled-packs-exactly-one-64-03-info-responder',shared_info_bus)
 from .power_rtc_tests import validate_power_rtc
 passed.extend(validate_power_rtc(original,patched,facts))
 if build.get('cutoff'):
  from .cutoff_tests import validate_cutoff
  passed.extend(validate_cutoff(original,patched,facts,build))
 if build.get('positive_flags') and build.get('cutoff'):
  from .permissions_tests import validate_positive
  passed.extend(validate_positive(original,patched,facts,build))
 assert len(passed)>=60,'incomplete test suite'
 if build.get('uart0_marker'):
  from .marker_uart0_tests import validate_uart0_marker
  passed.extend(validate_uart0_marker(original,patched,facts,build))
 if build.get('service'):
  from .service_tests import validate_service
  passed.extend(validate_service(original,patched,facts,build))
 if build.get('storage_diagnostics'):
  from .storage_diagnostics_tests import validate_diagnostics
  passed.extend(validate_diagnostics(original,patched,facts,build))
 if build.get('configurable_hard_stop'):
  from .configurable_hardstop_tests import validate_configurable
  passed.extend(validate_configurable(original,patched,facts,build))
 return passed
