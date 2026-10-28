"""Mandatory transport/action regressions; actual OEM RTC with modeled I2C."""
from .machine import Machine,ascii_frame,frame
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7


def validate_power_rtc(original,patched,facts):
 from .selftest import ascii_payload
 checks=[];d=facts['power_rtc'];r=facts['ram'];f=facts['functions']
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('power-rtc-'+name+': '+str(exc)) from exc
  checks.append({'name':'power-rtc-'+name,'passed':True})
 def equal(a,b):assert a==b,(a,b)
 def board(address=1,enabled=True):
  m=Machine(patched,facts);m.defaults(address)
  # Compare original power actions with extended-off disabled.
  group=m.num(r['group0'])&~0x18
  m.put(r['group0'],bytes([group|(8 if enabled else 0)]))
  return m
 def request(m,cmd,data=b''):
  adr=m.num(r['address']);return ascii_payload(m.transact(ascii_frame(adr,cmd,data),True),adr)
 def date(y,mo,day,h=0,mi=0,s=0):return y.to_bytes(2,'big')+bytes([mo,day,h,mi,s])
 def seed(m,values=bytes([26,10,18,14,30,59])):
  m.put(d['rtc']+4,values);equal(m.run(d['rtc_write']),1);m.rtc_transfers.clear()

 for adr in (0,1,11,15,21):
  for value in (0x10,0x1f):
   def power(adr=adr,value=value):
    m=board(adr);stock=Machine(original,facts);stock.defaults(adr)
    for b in (m,stock):
     b.put(d['system_status'],b'\x82');b.put(d['control_flags'],b'\x03')
    raw=ascii_frame(adr,0x45,bytes([0,4,value]));stock.put(d['uart0_rx'],raw)
    stock.run(d['power_handler'])
    # Canaries cover the entire UART0 receive/transmit region during UART1 work.
    start=d['uart0_rx']-0x200;sample=bytes((j*31+70)&255 for j in range(0x400))
    # Exclude UART1 overlap on older layouts: prove disjoint buffer intervals.
    assert start+0x400<r['state'] or start>r['tx_length']+20
    m.put(start,sample)
    regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7)
    for j,reg in enumerate(regs):m.uc.reg_write(reg,0x12340000+j)
    sp=m.uc.reg_read(UC_ARM_REG_SP)
    equal(request(m,0x45,bytes([0,4,value])),(0,b''))
    equal(m.num(d['system_status']),stock.num(d['system_status']))
    equal(m.num(d['control_flags']),stock.num(d['control_flags']))
    equal(m.read(start,len(sample)),sample);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
    for j,reg in enumerate(regs):equal(m.uc.reg_read(reg),0x12340000+j)
    assert d['power_action'] in m.executed and d['power_handler'] not in m.executed
    equal(m.saves,[]);equal(m.flash_ops,[])
   check(f'OEM-action-unicast-{adr}-{value:02x}-ABI-UART0-canaries',power)

 def gate():
  for cmd,data in ((0x45,b'\0\4\x10'),(0x45,b'\0\4\x1f'),(0x45,b'\0\6\0'),(0x4e,date(2026,10,18))):
   m=board(enabled=False);before=m.read(d['rtc']+4,6)
   equal(request(m,cmd,data),(5,b''));equal(m.read(d['rtc']+4,6),before)
   assert d['power_action'] not in m.executed and d['reset'] not in m.executed
   equal(m.rtc_transfers,[]);equal(m.saves,[])
 check('power-permission-zero-gates-actions-and-RTC-set',gate)

 def protected():
  for enabled in (False,True):
   m=board(enabled=enabled);before=m.payload();p=bytearray(before);p[150]^=8;p[130]=110
   equal(m.transact(frame(1,0xa1,p),True),frame(1,0xe3));equal(m.payload(),before);equal(m.saves,[])
   # Original display write is the recovery path and persists the flag.
   m.put(r['lcd_meta']+18,p);m.run(f['lcd_write']);equal(m.num(r['lcd_meta']+9),0xa1)
   m.put(r['group0'],b'\0'*8);m.run(f['loader']);equal(m.payload(),p)
 check('permission-protected-atomic-and-OEM-LCD-persistent-recovery',protected)

 for adr in (0,1,11,21):
  def reset(adr=adr):
   m=board(adr);m.pause=d['reset'];m.output.clear();m.feed(ascii_frame(adr,0x45,b'\0\6\0'))
   site=facts['hooks']['hook_dispatch'];m.execute(site,site+4)
   from unicorn.arm_const import UC_ARM_REG_PC
   equal(m.uc.reg_read(UC_ARM_REG_PC),d['reset']);equal(bytes(m.output),b'')
   equal(m.flash_ops,[]);equal(m.saves,[])
  check(f'local-original-watchdog-reset-no-ACK-{adr}',reset)

 for value in (b'',b'\0\3\x10',b'\0\5\0',b'\0\6\x01',b'\x01\x04\x10',b'\0\4\x00',b'\0\4\x10\0'):
  def invalid_power(value=value):
   m=board();before=m.read(d['system_status']);equal(request(m,0x45,value),(5,b''))
   equal(m.read(d['system_status']),before)
   assert d['power_action'] not in m.executed and d['reset'] not in m.executed
  check('reject-dangerous-or-malformed-power-'+value.hex(),invalid_power)

 for values in ((2000,2,29,23,59,59),(2001,3,1,0,0,0),(2024,2,29,12,34,56),(2099,12,31,23,59,59)):
  def clock(values=values):
   m=board();raw=date(*values);equal(request(m,0x4e,raw),(0,b''))
   assert d['rtc_write'] in m.executed and m.rtc_transfers[-1]['read'] is False
   equal(request(m,0x4d),(0,raw));assert d['rtc_read'] in m.executed
   equal(m.saves,[]);equal(m.flash_ops,[])
  check('actual-RTC-BCD-roundtrip-'+str(values),clock)

 invalid_dates=((1999,12,31),(2100,1,1),(2023,2,29),(2000,2,30),(2026,0,1),(2026,13,1),
                (2026,1,0),(2026,1,32),(2026,4,31),(2026,1,1,24,0,0),
                (2026,1,1,0,60,0),(2026,1,1,0,0,60))
 for values in invalid_dates:
  def invalid_date(values=values):
   m=board();seed(m);before=m.read(d['rtc']+4,6)
   equal(request(m,0x4e,date(*values)),(5,b''));equal(m.read(d['rtc']+4,6),before);equal(m.rtc_transfers,[])
  check('calendar-reject-before-commit-'+str(values),invalid_date)

 def rtc_gate_independent():
  m=board(enabled=False);seed(m);equal(request(m,0x4d),(0,date(2026,10,18,14,30,59)))
  equal(request(m,0x4d,b'\0'),(5,b''))
 check('RTC-read-ungated-with-strict-empty-INFO',rtc_gate_independent)
 for cmd,data in ((0x4d,b''),(0x4e,date(2026,10,18))):
  def fail(cmd=cmd,data=data):
   m=board();m.rtc_fail=True;equal(request(m,cmd,data),(8,b''))
  check(f'RTC-I2C-failure-RTN08-{cmd:02x}',fail)

 for foreign in (0,2,21,22,255):
  def silence(foreign=foreign):
   m=board();before=m.read(d['system_status']);seed(m)
   for cmd,data in ((0x45,b'\0\4\x1f'),(0x45,b'\0\6\0'),(0x4d,b''),(0x4e,date(2026,10,18))):
    equal(m.transact(ascii_frame(foreign,cmd,data),True),b'')
   equal(m.read(d['system_status']),before);equal(m.rtc_transfers,[])
  check(f'foreign-and-FF-address-silent-{foreign}',silence)

 for adr,offset,character in ((1,3,'G'),(0,4,'Z')):
  for cmd,data in ((0x45,b'\0\4\x1f'),(0x4e,date(2026,10,18)),(0x4d,b''),(0x64,b'\3')):
   def invalid_address(adr=adr,offset=offset,character=character,cmd=cmd,data=data):
    m=board(adr);seed(m);before=m.read(d['system_status'])
    raw=bytearray(ascii_frame(adr,cmd,data));raw[offset]=ord(character)
    equal(m.transact(raw,True),b'');equal(m.read(d['system_status']),before);equal(m.rtc_transfers,[])
    assert f['parser'] not in m.executed
   check(f'raw-nonhex-ADR-before-OEM-normalization-{adr}-{cmd:02x}',invalid_address)

 def malformed():
  m=board();seed(m)
  def rechecksum(body):return b'~'+body+f'{(-sum(body))&65535:04X}'.encode()+b'\r'
  req=ascii_frame(1,0x45,b'\0\4\x1f')
  bad_checksum=req[:-5]+b'0000\r'
  # OEM parser responds with RTN02 to a bad checksum; no action may execute.
  equal(ascii_payload(m.transact(bad_checksum,True),1),(2,b''))
  for offset,byte in ((1,ord('3')),(5,ord('5')),(9,ord('0')),(13,ord('G'))):
   body=bytearray(req[1:-5]);body[offset-1]=byte
   out=m.transact(rechecksum(body),True)
   if out:equal(ascii_payload(out,1),(3 if offset==9 else 5,b''))
  equal(m.rtc_transfers,[]);assert d['power_action'] not in m.executed
  equal(request(m,0x45,b'\0\4\x10'),(0,b''))
 check('bad-checksum-CID-version-length-hex-recovery',malformed)
 return checks
