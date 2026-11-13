"""Mandatory Full-profile real Thumb/CRC/flash transaction and output-path regressions."""
from .machine import Machine,PowerLoss,ascii_frame,frame
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2

FAST_REQUIRED=(
 'cutoff-fast-current-signed-threshold-and-gates',
 'cutoff-persistent-off-fast-current-boundaries',
)


def _fast_current_roles(original,facts):
 """Derive the signed operand and event byte from the native handover branch."""
 import re
 from .thumb import Code
 from .analysis import unique
 code=Code(original.app);body=code.body(facts['cutoff']['fast']);thresholds=[]
 for ins in body:
  m=re.fullmatch(r'(r\d+), #(0x[0-9a-f]+|\d+)',ins.args)
  w=code.window(ins.at,4)
  if ins.op!='movs' or not m or len(w)!=4 or w[1].op!='lsls' or w[2].op!='cmp' or w[3].op!='blt':continue
  shift=re.fullmatch(rf'{m[1]}, {m[1]}, #(0x[0-9a-f]+|\d+)',w[1].args)
  operand=re.fullmatch(rf'(r\d+), {m[1]}',w[2].args)
  if shift and operand and int(m[2],0)<<int(shift[1],0)==1000:thresholds.append((ins.at,operand[1]))
 at,reg=unique(thresholds,'signed fast-current threshold branch')
 operands=[]
 for ins in body:
  following=code.ins.get(ins.at+ins.size)
  if ins.at>=at or ins.literal is None or not 0x20000000<=ins.literal<original.sp or not following or following.op!='ldr':continue
  base=ins.args.split(',')[0]
  m=re.fullmatch(rf'{reg}, \[{base}(?:, #(0x[0-9a-f]+|\d+))?\]',following.args)
  if m:operands.append(ins.literal+(int(m[1],0) if m[1] else 0))
 current=unique(operands,'native signed fast-current operand')
 prior=[i for i in body if i.at<at and i.literal is not None and 0x20000000<=i.literal<original.sp
        and code.ins.get(i.at+i.size) and code.ins[i.at+i.size].op=='ldrb']
 if not prior:raise ValueError('missing fast-current interlock operand')
 event=prior[-1].literal
 return current,event


def validate_fast_handover(original,patched,facts,report):
 """Native boundary checks independent of the slow charge-recovery current."""
 from .selftest import ascii_payload
 d=facts['cutoff'];r=facts['ram'];e=d['entries'];current,event=_fast_current_roles(original,facts)
 gpio=0x50002000;mask=(1<<10)|(1<<12)|(1<<13)|(1<<15);rows=[]
 values=(-1001,-1,0,999,1000,1001)
 def board():
  m=Machine(patched,facts);m.defaults(1)
  m.put(r['group0'],bytes([m.num(r['group0'])|0x18]))
  m.put(d['onoff'],b'\3');m.put(d['onoff']+1,b'\3')
  m.put(gpio,((1<<1)|(1<<12)|(1<<13)|(1<<14)).to_bytes(4,'little'))
  return m
 def prepare(m,value):
  m.put(r['group0']+4,bytes([m.num(r['group0']+4)&~0x10]))
  m.put(r['group0']+6,bytes([m.num(r['group0']+6)|0x40]))
  m.put(event,bytes([m.num(event)&~0x40]))
  m.put(current,value.to_bytes(4,'little',signed=True))
 def observe(m):
  writes=[]
  def callback(uc,access,address,size,value,user):
   if address==gpio:writes.append(value)
  m.uc.hook_add(UC_HOOK_MEM_WRITE,callback);return writes
 def controls():
  for value in values:
   m=board();prepare(m,value);m.put(d['onoff'],b'\2');m.put(d['onoff']+2,b'\2');m.put(event-1,b'\0')
   m.run(d['fast']);expected=4 if value>=1000 else 2
   assert m.num(d['onoff'])==expected,(value,hex(current),m.num(d['onoff']))
   assert bool(m.num(event)&0x40)==(value>=1000),value
   assert bool(m.num(gpio,4)&(1<<12))==(value<1000),value
  for gate in ('switch-disabled','charge-disabled','already-limited','interlock-set'):
   m=board();prepare(m,1001);m.put(d['onoff'],b'\2');m.put(d['onoff']+2,b'\2')
   if gate=='switch-disabled':m.put(r['group0']+6,bytes([m.num(r['group0']+6)&~0x40]))
   elif gate=='charge-disabled':m.put(d['onoff'],b'\0');m.put(gpio,(m.num(gpio,4)&~(1<<12)).to_bytes(4,'little'))
   elif gate=='already-limited':m.put(d['onoff'],b'\6');m.put(d['onoff']+2,b'\6')
   else:m.put(event,bytes([m.num(event)|0x40]))
   before=m.num(d['onoff']);m.run(d['fast']);assert m.num(d['onoff'])==before,gate
 def locked():
  for value in values:
   m=board();response=ascii_payload(m.transact(ascii_frame(1,0x45,b'\0\4\x1f'),True),1)
   assert response==(0,b'') and m.num(d['ram'])==1 and len(m.nv_ops)==4,value
   assert not m.num(d['onoff'])&0x17 and not m.num(gpio,4)&mask,value
   # Preserve the real Off result: never synthesize new OnOff bits after it.
   prepare(m,value);writes=observe(m)
   for _ in range(3):
    m.run(e['hook_cut_charge']);m.run(e['hook_cut_discharge']);m.run(d['fast']);m.run(d['precharge'])
   assert m.num(d['ram'])==1 and not m.num(d['onoff'])&0x17,value
   assert writes and all(not word&mask for word in writes),(value,writes)
 for name,func in zip(FAST_REQUIRED,(controls,locked)):
  try:func()
  except Exception as exc:raise AssertionError(name+': '+str(exc)) from exc
  rows.append({'name':name,'passed':True})
 return rows


def validate_cutoff(original,patched,facts,report):
 from .selftest import ascii_payload
 d=facts['cutoff'];e=d['entries'];r=facts['ram'];f=facts['functions'];out=[]
 positive=report.get('positive_flags',False)
 def equal(a,b):assert a==b,(a,b)
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('cutoff-'+name+': '+str(exc)) from exc
  out.append({'name':'cutoff-'+name,'passed':True})
 def board(address=1,enable=True,persist=False):
  m=Machine(patched,facts);m.defaults(address)
  if enable:m.put(r['group0'],bytes([(m.num(r['group0'])|0x18) if positive else (m.num(r['group0'])&~0x18)]))
  m.put(d['onoff'],b'\x03');m.put(d['onoff']+1,b'\x03')
  m.put(0x50002000,((1<<1)|(1<<12)|(1<<13)).to_bytes(4,'little'))
  if persist:m.run(e['hook_cut_serializer_0']);m.nv_ops.clear();m.nv_step=0;m.saves.clear()
  return m
 def power(m,value):
  adr=m.num(r['address']);return ascii_payload(m.transact(ascii_frame(adr,0x45,bytes([0,4,value])),True),adr)
 def latch(m):return m.num(d['ram'])
 def reboot(m):
  n=Machine(patched,facts);n.put(0x25000,m.read(0x25000,8192));n.defaults(m.num(r['address']));return n
 def u0(m,value,address=None):
  address=m.num(r['address']) if address is None else address
  m.put(d['uart0_rx'],ascii_frame(address,0x45,bytes([0,4,value])))
  m.put(d['uart0_state'],b'\x03');m.put(d['uart0_rtn'],b'\0')
  m.run(e['hook_cut_uart0_power']);return m.num(d['uart0_rtn'])
 def no_paths(m):
  equal(m.num(d['onoff'])&0x17,0)
  equal(m.num(0x50002000,4)&((1<<10)|(1<<12)|(1<<13)|(1<<15)),0)
 def off(m):equal(power(m,0x1f),(0,b''));equal(latch(m),1);no_paths(m)

 def integrity():
  allowed={a for site in report['hooks'].values() for a in range(site,site+4)}
  allowed.update(range(d['zero_size_offset'],d['zero_size_offset']+4))
  if report.get('scheduler_atomic'):
   a=facts['scheduler_atomic']['branch_site'];allowed.update(range(a,a+2))
  if report['hard_stop'].get('changed'):allowed.add(report['hard_stop']['offset'])
  assert all(a in allowed or x==y for a,(x,y) in enumerate(zip(original.app,patched.app)))
  equal(original.sp,patched.sp);equal(d['ram'],original.sp)
  equal(int.from_bytes(patched.app[d['zero_size_offset']:d['zero_size_offset']+4],'little'),d['zero_size_old']+4)
  m=board();rtn,data=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)
  equal((rtn,len(data),data[7:9],data[18]),(0,report['info_bytes'],b'\1\6',report['image_flags']))
  # Real OEM zero helper initializes the added cache bytes without moving SP.
  m.put(d['ram'],b'XXXX');m.uc.reg_write(UC_ARM_REG_R0,0);m.uc.reg_write(UC_ARM_REG_R1,d['ram']);m.uc.reg_write(UC_ARM_REG_R2,4)
  m.run(d['zero_helper']);equal(m.read(d['ram'],4),bytes(4))
 check('layout-version-SRAM-startup-original-SP',integrity)

 def factory():
  m=board(enable=False);equal(latch(m),0);equal(m.num(r['group0']),255)
  m.put(r['group0'],b'\xef' if positive else b'\xf7');equal(power(m,0x1f),(0,b''));equal(latch(m),0);equal(m.nv_ops,[])
  m.run(e['hook_cut_charge']);assert m.num(d['onoff'])&2
 check('explicit-cutoff-disabled-is-OEM-behavior' if positive else 'legacy-FF-is-OEM-behavior-no-new-persistence',factory)

 for address in (0,1,11,15,21):
  def roundtrip(address=address):
   m=board(address);sp=m.uc.reg_read(UC_ARM_REG_SP);off(m)
   equal(len(m.nv_ops),4);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
   assert not m.num(r['group0'])&32
   n=reboot(m);equal(latch(n),1);no_paths(n);assert n.num(0x50011000+4,4)&0x40==0
   equal(power(n,0x10),(0,b''));equal(latch(n),0);assert n.num(r['group0'])&32
   z=reboot(n);equal(latch(z),0);equal(z.num(r['group0'])&32,32)
   if address==0:assert m.num(facts['power_rtc']['control_flags'])&16
  check(f'persistent-off-explicit-on-reboot-{address}',roundtrip)

 def idempotent():
  m=board();off(m);n=len(m.nv_ops)
  off(m);equal(len(m.nv_ops),n)
  equal(power(m,0x10),(0,b''));n=len(m.nv_ops)
  equal(power(m,0x10),(0,b''));equal(len(m.nv_ops),n)
 check('idempotent-no-extra-flash-wear',idempotent)

 def repair_unlocked():
  m=board(persist=True);m.nv_fail_at={2}
  m.put(r['words'],(m.num(r['words'],2)+1).to_bytes(2,'little'))
  m.run(e['hook_cut_serializer_0']);equal(latch(m),0);equal(m.num(d['ram']+2),0)
  equal(latch(reboot(m)),1)
  m.nv_fail_at.clear();before=len(m.nv_ops)
  equal(power(m,0x10),(0,b''));equal(len(m.nv_ops)-before,4)
  equal(latch(reboot(m)),0)
 check('explicit-on-repairs-inconsistent-unlocked-records',repair_unlocked)

 def repair_fails():
  m=board(persist=True);m.nv_fail_at={2}
  m.run(e['hook_cut_serializer_0']);equal(latch(m),0);equal(m.num(d['ram']+2),0)
  m.nv_fail_at={m.nv_step+2}
  equal(power(m,0x10),(8,b''));equal(latch(m),1);no_paths(m)
  equal(latch(reboot(m)),1)
 check('failed-explicit-on-repair-locks-previously-unlocked-RAM',repair_fails)

 def diagnostic():
  m=board();off(m);m.put(r['group0'],bytes([(m.num(r['group0'])&~8) if positive else (m.num(r['group0'])|8)]))
  for command,length in ((0x47,168),(0xa2,30),(0xa4,30)):
   reply=m.transact(frame(1,command),True)
   equal((reply[1],reply[2],reply[3]),(1,command,length))
  equal(ascii_payload(m.transact(ascii_frame(1,0x4d),True),1)[0],0)
  equal(ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)[0],0)
  equal(power(m,0x10),(5,b''));equal(latch(m),1);no_paths(m)
 check('diagnostics-remain-available-with-latch-and-power-lock',diagnostic)

 def uart0():
  m=board();equal(u0(m,0x1f),0);equal(latch(m),1);no_paths(m)
  before=m.read(0x25000,8192);equal(u0(m,0x10,255),0)
  equal(m.num(d['uart0_state']),0);equal(latch(m),1);equal(m.read(0x25000,8192),before)
  equal(u0(m,0x10),0);equal(latch(m),0)
  equal(u0(m,0x1f,255),0);equal(latch(m),0);equal(m.num(d['uart0_state']),0)
  assert m.num(facts['power_rtc']['system_status'])&32
  equal(u0(m,0x10,255),0);equal(latch(m),0);assert not m.num(facts['power_rtc']['system_status'])&32
 check('UART0-unicast-vs-FF-no-broadcast-unlock-or-persistent-global-off',uart0)
 for adr in (0,2,255):
  def foreign(adr=adr):
   m=board();off(m);before=m.read(0x25000,8192)
   equal(m.transact(ascii_frame(adr,0x45,b'\0\4\x10'),True),b'');equal(latch(m),1)
   equal(m.read(0x25000,8192),before);equal(u0(m,0x10,adr),0);equal(latch(m),1)
  check(f'foreign-and-UART1-FF-cannot-release-{adr}',foreign)

 for channel in ('uart0','uart2','uart1'):
  for valid in (False,True):
   def backup(channel=channel,valid=valid):
    m=board();off(m);p=bytearray(m.payload());p[150]=(p[150]&~16)|32 if positive else p[150]|0x30;p[130]=110
    if not valid:p[1:3]=b'\0\0'
    if channel=='uart1':equal(m.transact(frame(1,0xa1,p),True),frame(1,0xe3))
    elif channel=='uart2':
     m.put(r['lcd_meta']+18,p);m.run(e['hook_cut_lcd_a1'])
    else:
     m.put(d['uart0_rx'],ascii_frame(1,0xa1,b'\1'+p+m.read(r['name'],10)));m.run(e['hook_cut_uart0_a1'])
    equal(latch(m),1);assert not m.num(r['group0'])&32;no_paths(m)
    n=reboot(m);equal(latch(n),1);no_paths(n)
    equal(u0(n,0x10),0);equal(latch(n),0)
   check(f'old-backup-preserves-latch-{channel}-valid-{valid}',backup)

 def fast_and_wakeup():
  m=board();off(m);seen=[]
  def writes(uc,access,address,size,value,user):
   if address==0x50002000:seen.append(value)
  m.uc.hook_add(UC_HOOK_MEM_WRITE,writes)
  for current,status in ((0,0x20),(400,0xa2),(-1100,0x61)):
   m.put(facts['power_rtc']['system_status'],bytes([status]));m.put(d['measure']+8,current.to_bytes(2,'little',signed=True))
   m.put(d['state_timer']+10,b'\x1d');m.put(d['measure']+18,(6500).to_bytes(2,'little'))
   m.run(e['hook_cut_charge']);m.run(e['hook_cut_discharge']);m.run(e['hook_cut_power_state'])
   for _ in range(30):m.run(d['fast']);m.run(d['precharge'])
   no_paths(m);equal(latch(m),1);assert m.num(facts['power_rtc']['system_status'])&32
   assert m.num(0x50001000,4)&2,'BMS self-hold must remain on'
  assert all(not v&((1<<10)|(1<<12)|(1<<13)|(1<<15)) for v in seen)
 check('no-charge-discharge-override-port-wakeup-fast-limiter-precharge-or-powerdown',fast_and_wakeup)

 def real_protection():
  m=board();off(m);equal(power(m,0x10),(0,b''));m.put(0x20000031,b'\xaa')
  m.run(e['hook_cut_charge']);m.run(e['hook_cut_discharge']);no_paths(m)
 check('explicit-on-does-not-override-real-protections',real_protection)

 for command in (0x10,0x1f):
  for fail_at in (1,2,3,4):
   def failure(command=command,fail_at=fail_at):
    m=board(persist=True)
    if command==0x10:off(m)
    m.nv_step=0;m.nv_fail_at={fail_at}
    result=power(m,command)
    if result==(0,b''):
     n=reboot(m);equal(latch(n),int(command==0x1f))
    else:
     equal(result,(8,b''));equal(latch(m),1);no_paths(m)
     n=reboot(m);equal(latch(n),1)
    if fail_at==2:assert len(m.nv_ops)%4==2,'failed primary must preserve backup'
   check(f'write-failure-step-{fail_at}-command-{command:02x}',failure)

 for command in (0x10,0x1f):
  for cut in (1,2,3,4):
   def interrupted(command=command,cut=cut):
    m=board(persist=True)
    if command==0x10:off(m)
    m.nv_step=0;m.nv_cut_after=cut
    try:power(m,command)
    except PowerLoss:pass
    else:raise AssertionError('power cut did not execute')
    n=reboot(m)
    # Release is durable only after both independently valid unlocked records.
    equal(latch(n),0 if command==0x10 and cut==4 else 1)
    if latch(n):no_paths(n)
   check(f'power-cut-after-step-{cut}-command-{command:02x}',interrupted)

 def disagreement():
  m=board(persist=True);unlocked=m.read(0x25000,4096);off(m);locked=m.read(0x25000,4096)
  for a,b in ((unlocked,locked),(locked,unlocked)):
   n=Machine(patched,facts);n.put(0x25000,a);n.put(0x26000,b);n.defaults(1)
   equal(latch(n),1);equal(n.nv_ops,[]);no_paths(n)
   equal(latch(reboot(n)),1);equal(u0(n,0x10),0);equal(latch(reboot(n)),0)
 check('CRC-valid-disagreeing-mirrors-lock-dominates-primary',disagreement)
 for both in (False,True):
  def corrupt(both=both):
   m=board(persist=True);off(m);m.put(0x25000+171,bytes([m.num(0x25000+171)^1]))
   if both:m.put(0x26000+171,bytes([m.num(0x26000+171)^1]))
   n=reboot(m);equal(latch(n),1);no_paths(n);equal(n.nv_ops,[])
   equal(latch(reboot(n)),1);equal(u0(n,0x10),0);equal(latch(reboot(n)),0)
  check(f'nonempty-corrupt-record-no-repair-loss-both-{both}',corrupt)

 def aggregate(off_count=0,heating=False):
  m=board(0);m.put(r['slaves'],b'\x0b');m.put(d['poll_mask'],(4095).to_bytes(4,'little'))
  m.put(d['aggregate'],bytes([12,12]));m.put(d['aggregate']+32,(500).to_bytes(2,'little'))
  m.put(d['aggregate']+36,(9000).to_bytes(2,'little'));m.put(r['words']+100,(15000).to_bytes(2,'little'))
  m.put(r['words']+104,(-15500).to_bytes(2,'little',signed=True))
  m.put(d['aggregate']-24,(3300).to_bytes(2,'little')*2+(2981).to_bytes(2,'little')*2)
  m.put(d['state_control']+6,b'\x04');m.put(r['group0']+7,b'\0')
  for i in range(12):
   p=bytearray(30);p[10:12]=(5280).to_bytes(2,'little');p[26]=0 if i<off_count else 3;p[29]=0x20 if i<off_count else 0x10
   m.put(d['pack_table']+30*i,p)
  if heating:
   m.put(r['group0']+3,b'\x40');m.put(d['aggregate']-20,(2600).to_bytes(2,'little')*2)
   m.put(r['words']+72,(2731).to_bytes(2,'little'));m.put(r['words']+74,(2831).to_bytes(2,'little'))
  else:m.put(r['group0']+3,b'\0')
  m.run(d['count']);m.run(e['hook_cut_ccl']);return m
 for count,heat,ccl,dcl in ((0,False,9000,17400),(1,False,8250,15950),(11,True,750,1450),(12,True,0,0)):
  def clamp(count=count,heat=heat,ccl=ccl,dcl=dcl):
   m=aggregate(count,heat);equal(m.num(d['aggregate']+36,2),ccl);equal(m.num(d['aggregate']+40,2),dcl)
  check(f'CCL-DCL-count-{count}-heat-{heat}',clamp)
 def stale_poll_bit():
  m=aggregate();m.put(r['slaves'],b'\0');m.put(d['poll_mask'],(3).to_bytes(4,'little'))
  m.put(d['pack_table']+30+26,b'\0');m.put(d['pack_table']+30+29,b'\x20')
  m.put(d['aggregate']+36,(9000).to_bytes(2,'little'))
  m.run(d['count']);m.run(d['ccl']);expected=m.num(d['aggregate']+36,2)
  m.put(d['aggregate']+36,(9000).to_bytes(2,'little'))
  m.run(e['hook_cut_ccl']);equal(m.num(d['aggregate']+36,2),expected)
 check('stale-online-record-outside-configured-slaves-does-not-clamp',stale_poll_bit)
 out.extend(validate_fast_handover(original,patched,facts,report))
 assert len(out)>=30
 return out
