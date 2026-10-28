"""Mandatory1.6.3 actual-Thumb mask, parameter, GPIO and priority checks."""
import copy
from .machine import Machine,ascii_frame,frame
from .marker_uart0_tests import uart0_exchange
from .selftest import ascii_payload
from unicorn.arm_const import (UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_APSR,
 UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
 UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
 UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12)

REQUIRED=tuple('configurable_hardstop-'+name for name in (
 'capability-and-21-hook-surface','FF-default-no-migration',
 'all256-group0-times256-event6','mask-ABI-and-NZCV',
 'complete-charge-GPIO-mode-selection','discharge-recovery-and-OVP-priority',
 'temperature-and-other-protections','live-selection-without-flash',
 'explicit-R-C-D-parameter-persistence','C-A1-permission-remains',
 'persistent-pack-lock-wins','imports-preserve-all-four-encodings',
 'diagnostics-unchanged-and-no-writes','addressed-slave-config-and-version',
 'no-new-RAM-and-unknown-native-ABI-refused','MNT-default-not-runtime'))

def validate_configurable(original,patched,facts,report):
 r=facts['ram'];f=facts['functions'];h=facts['configurable_hardstop'];d=facts['cutoff'];p=facts['power_rtc'];base=facts['hard_stop']
 default=report['hard_stop_default'];rows=[]
 def equal(a,b):assert a==b,(a,b)
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('configurable_hardstop-'+name+': '+str(exc)) from exc
  rows.append(dict(name='configurable_hardstop-'+name,passed=True))
 def board(mode=0xc0,adr=1):
  m=Machine(patched,facts);m.defaults(adr)
  m.put(r['group0'],bytes([(m.num(r['group0'])&0x3f)|mode]))
  m.put(p['system_status'],b'\0');m.put(0x20000030,bytes(8));m.put(h['temperature_raw'],b'\0')
  m.put(h['event6'],b'\2');m.put(h['recovery_counter'],b'\0')
  m.saves.clear();m.nv_ops.clear();m.flash_ops.clear();m.executed.clear();return m
 def effective(group):return default if group&128 else bool(group&64)
 def charge(m):
  m.run(h['function']);forbidden=bool(m.num(base['forbidden_flags'])&64)
  equal(bool(m.num(0x50002000,4)&(1<<12)),not forbidden)
  return forbidden
 def setmode(m,mode):m.put(r['group0'],bytes([(m.num(r['group0'])&0x3f)|mode]))
 def reboot(m):
  n=Machine(patched,facts);n.put(d['nv_primary'],m.read(d['nv_primary'],8192));n.defaults(m.num(r['address']));return n
 def no_flash(m):equal(m.saves,[]);equal(m.nv_ops,[]);equal(m.flash_ops,[])
 def surface():
  equal(report['patch_version'],'1.6.3');equal(report['image_flags'],0xfe|int(default))
  assert report['configurable_hard_stop'] and report['hard_stop']['enabled'] is None
  equal(report['hard_stop']['default_enabled'],default);equal(report['ram_bytes'],4)
  equal(len(report['hooks']),21);equal(report['hooks']['hook_configurable_hard_stop'],h['site'])
  equal(h['site'],base['offset']);equal(h['parameter_mask'],0xc0)
  assert len(set(report['hooks'].values()))==21
 check('capability-and-21-hook-surface',surface)
 def FF():
  m=board();equal(m.num(r['group0']),255)
  before=m.payload();equal(charge(m),default);equal(m.payload(),before);no_flash(m)
 check('FF-default-no-migration',FF)
 def exhaustive():
  m=board();start=h['site']
  for group in range(256):
   m.put(r['group0'],bytes([group]));mask=0x73 if effective(group) else 0x71
   for event in range(256):
    m.put(h['event6'],bytes([event]));m.uc.reg_write(UC_ARM_REG_R3,h['event6'])
    target=base['branch_target'] if event&mask else base['fallthrough']
    m.execute(start,target,count=80)
    assert m.uc.reg_read(UC_ARM_REG_PC)==target,(group,event,mask)
    equal(m.uc.reg_read(UC_ARM_REG_R4),mask);equal(m.uc.reg_read(UC_ARM_REG_R3),event)
  no_flash(m)
 check('all256-group0-times256-event6',exhaustive)
 def abi():
  regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
   UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12)
  for mode in (0,0x40,0x80,0xc0):
   for flags in (0,0x20000000,0x10000000,0xf0000000):
    m=board(mode);sp=m.uc.reg_read(UC_ARM_REG_SP)
    for i,reg in enumerate(regs):m.uc.reg_write(reg,0x12345000+i)
    m.uc.reg_write(UC_ARM_REG_R3,h['event6']);m.uc.reg_write(UC_ARM_REG_APSR,flags)
    m.execute(h['site'],h['site']+4,count=80)
    equal(m.uc.reg_read(UC_ARM_REG_PC),h['site']+4);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
    equal(m.uc.reg_read(UC_ARM_REG_APSR)&0xf0000000,flags&0x30000000)
    equal(m.uc.reg_read(UC_ARM_REG_R3),2)
    for i,reg in enumerate(regs):equal(m.uc.reg_read(reg),0x12345000+i)
    no_flash(m)
 check('mask-ABI-and-NZCV',abi)
 def GPIO():
  for mode in (0,0x40,0x80,0xc0):
   for event in (0,2,1,4,8,16,32,64,128):
    m=board(mode);m.put(h['event6'],bytes([event]));mask=0x73 if effective(m.num(r['group0'])) else 0x71
    equal(charge(m),bool(event&mask));no_flash(m)
 check('complete-charge-GPIO-mode-selection',GPIO)
 def recovery():
  for mode in (0,0x40,0x80,0xc0):
   m=board(mode);m.put(h['current'],(-1100).to_bytes(2,'little',signed=True));m.put(h['recovery_counter'],b'\x09')
   equal(charge(m),False);equal(m.num(h['recovery_counter']),10)
   m.put(h['current'],bytes(2));equal(charge(m),effective(m.num(r['group0'])))
   m.put(h['current'],(-1100).to_bytes(2,'little',signed=True));m.put(h['recovery_counter'],b'\x09');m.put(h['ovp_event'],b'\x22')
   equal(charge(m),True);equal(m.num(h['ovp_event'])&0x22,0);no_flash(m)
 check('discharge-recovery-and-OVP-priority',recovery)
 def protections():
  pairs=((h['ovp_event'],2),(h['ovp_event'],32),(h['temperature_raw'],2),(h['temperature_raw'],8),
   (h['event6']-2,2),(h['event6']-2,8),(h['event6']-2,16),(h['event6']-1,2))
  for mode in (0,0x40,0x80,0xc0):
   for address,value in pairs:
    m=board(mode);m.put(h['event6'],b'\0');m.put(address,bytes([value]));equal(charge(m),True);no_flash(m)
 check('temperature-and-other-protections',protections)
 def live():
  m=board()
  for mode in (0x40,0,0x40,0x80,0xc0):
   setmode(m,mode);equal(charge(m),effective(m.num(r['group0'])));no_flash(m)
 check('live-selection-without-flash',live)
 def persist():
  for port in ('R','C','D'):
   for mode in (0,0x40,0x80,0xc0):
    m=board();before=m.payload();payload=bytearray(before);payload[150]=(payload[150]&0x3f)|mode
    if port=='C':equal(m.transact(frame(1,0xa1,payload),True),frame(1,0xa1))
    elif port=='R':equal(ascii_payload(uart0_exchange(m,ascii_frame(1,0xa1,b'\1'+payload+m.read(r['name'],10))),1),(0,b''))
    else:
     m.put(r['lcd_meta']+18,payload);m.run(f['lcd_write']);equal(m.num(r['lcd_meta']+9),0xa1)
    equal(m.payload(),payload);equal(m.num(r['group0'])&0x3f,before[150]&0x3f)
    n=reboot(m);equal(n.payload(),payload);equal(n.num(r['group0'])&0xc0,mode)
    n.put(h['event6'],b'\2');equal(charge(n),effective(n.num(r['group0'])))
 check('explicit-R-C-D-parameter-persistence',persist)
 def denied():
  m=board();m.put(r['group0'],bytes([m.num(r['group0'])&~1]));before=m.payload();payload=bytearray(before);payload[150]=(payload[150]&0x3f)|0x40
  equal(m.transact(frame(1,0xa1,payload),True),frame(1,0xe3));equal(m.payload(),before);no_flash(m)
 check('C-A1-permission-remains',denied)
 def lock():
  for mode in (0,0x40,0x80,0xc0):
   m=board(mode)
   equal(ascii_payload(m.transact(ascii_frame(1,0x45,b'\0\4\x1f'),True),1),(0,b''))
   m.put(h['current'],(-1100).to_bytes(2,'little',signed=True));m.put(h['recovery_counter'],b'\x09');m.executed.clear()
   m.run(d['entries']['hook_cut_charge'])
   equal(m.num(d['onoff'])&0x17,0);equal(m.num(0x50002000,4)&((1<<10)|(1<<12)),0)
   assert h['site'] not in m.executed
 check('persistent-pack-lock-wins',lock)
 def imports():
  for mode in (0,0x40,0x80,0xc0):
   m=board(mode);value=m.num(r['group0']);m.run(f['serializer']);n=reboot(m);equal(n.num(r['group0']),value)
 check('imports-preserve-all-four-encodings',imports)
 def diagnostics():
  for mode in (0,0x40,0x80,0xc0):
   m=board(mode);m.run(f['serializer']);m.saves.clear();m.nv_ops.clear();m.flash_ops.clear()
   before=m.read(0x23000,0xa000)
   for port in ('R','C'):
    packet=ascii_frame(1,0x64,b'\4');answer=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
    rtn,data=ascii_payload(answer,1);equal((rtn,len(data),data[0]),(0,10,1))
   equal(m.read(0x23000,0xa000),before);no_flash(m)
 check('diagnostics-unchanged-and-no-writes',diagnostics)
 def addressed():
  boards=[board(0xc0,i) for i in range(12)]
  packet=frame(7,0xa1,boards[7].payload()[:150]+bytes([(boards[7].payload()[150]&0x3f)|0x40])+boards[7].payload()[151:])
  answers=[m.transact(packet,True) for m in boards];equal([i for i,x in enumerate(answers) if x],[7])
  equal(boards[7].num(r['group0'])&0xc0,0x40)
  for i,m in enumerate(boards):
   rtn,data=ascii_payload(m.transact(ascii_frame(i,0x64,b'\3'),True),i);equal((rtn,data[7:10]),(0,b'\1\6\3'))
 check('addressed-slave-config-and-version',addressed)
 def refused():
  from .configurable_hardstop import discover_configurable
  equal(report['ram_bytes'],4);equal(original.sp,patched.sp)
  bad=copy.deepcopy(facts);bad['hard_stop']['offset']+=2
  try:discover_configurable(original,bad)
  except ValueError:pass
  else:raise AssertionError('unknown instruction pair accepted')
 check('no-new-RAM-and-unknown-native-ABI-refused',refused)
 def static():
  m=board();answers=[]
  for mode in (0,0x40,0x80,0xc0):
   setmode(m,mode);rtn,data=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1);equal(rtn,0);answers.append(data)
  equal(len(set(answers)),1);equal(answers[0][-1],0xfe|int(default))
 check('MNT-default-not-runtime',static)
 equal({t['name'] for t in rows},set(REQUIRED))
 return rows
