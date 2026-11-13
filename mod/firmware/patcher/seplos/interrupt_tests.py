"""Deterministic native IRQ interleavings, with explicit exception accounting.

UART0 = RS485-1/RS485-2; UART1 = RS485 pair in the CAN socket;
UART2 = local display/Bluetooth. Event boundaries are synthetic instruction
boundaries, not physical timing or a cycle-accurate NVIC model.
"""
import struct
from collections import deque
from .machine import STOP,ascii_frame
from .remote_diagnostics_tests import RemoteMachine,query
from .thumb import Code
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
 UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
 UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,
 UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR,UC_ARM_REG_PRIMASK)

REQUIRED=tuple('interrupt-'+s for s in (
 'native-priorities-and-vectors','native-progress-mask','masked-pending-and-priority',
 'nested-equal-priority-and-exception-ABI','diagnostics-history-native-coexistence',
 'A8-native-wake-lost-update-and-coalescing-controls'))
FULL_REQUIRED=('interrupt-checkpoint-native-coexistence',)
STACKED=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
 UC_ARM_REG_R12,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR)
CALLEE=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
 UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
IRQ_RETURN=0x3ee00
PRIORITIES={0:0,1:1,2:1,3:2,4:3,5:3}

class InterruptMachine(RemoteMachine):
 """Opt-in scheduler. Only hardware-stacked registers are restored on return.

 Native handlers use an explicit return sentinel. The synthetic frame preserves
 caller state, while R4-R11 and frame/stack canaries are checked before unstacking.
 PRIMASK and active IRQ priority control pending delivery at every instruction.
 """
 def __init__(self,image,facts):
  self.handlers={i:struct.unpack_from('<I',image.app,0x40+4*i)[0]&~1 for i in range(6)}
  self.priorities=PRIORITIES.copy();self.pending=set();self.active=[];self.irq_log=[]
  self.events={};self._irq_trap=False;self._steps=0
  self.uart0_queue=deque();self.uart0_wire=deque();self.uart0_output=bytearray();self.uart0_depth=8
  super().__init__(image,facts)
  self.uc.mem_map(0x41000000,0x1000)
 def uart0_receive(self,packet):
  self.uart0_wire.extend(packet);self._uart0_arrive();self.pend(3)
 def _uart0_arrive(self):
  for _ in range(min(8,self.uart0_depth-len(self.uart0_queue),len(self.uart0_wire))):self.uart0_queue.append(self.uart0_wire.popleft())
  assert len(self.uart0_queue)<=self.uart0_depth,'UART0 synthetic FIFO depth'
 def _read(self,uc,access,address,size,value,user):
  if address==0x50010008:
   # Explicit synthetic arrivals are paced in chunks of eight, within a
   # eight-byte FIFO bound. Final-byte timeout follows the last arrival;
   # native IRQ service retains its actual eight-byte RX budget.
   status=(1<<16 if self.uart0_queue else 0)|(1<<21 if len(self.uart0_queue)==1 and not self.uart0_wire else 0)
   status|=1<<27 if self.num(0x50010004,4)&0x40 else 0
   self.put(address,status.to_bytes(4,'little'));return
  if address==0x5001000c:self.put(address,len(self.uart0_queue).to_bytes(4,'little'));return
  if address==0x50010000:
   assert self.uart0_queue,'UART0 FIFO underflow'
   self.put(address,self.uart0_queue.popleft().to_bytes(4,'little'));return
  super()._read(uc,access,address,size,value,user)
 def _write(self,uc,access,address,size,value,user):
  if address==0x50010000:self.uart0_output.append(value&255)
  super()._write(uc,access,address,size,value,user)
 def idle(self):
  self.put(0x3ed00,bytes.fromhex('00467047'));return self.run(0x3ed00)
 def pend(self,irq):
  assert irq in self.handlers,'unknown IRQ';self.pending.add(irq)
 def at(self,pc,action):self.events.setdefault(pc,[]).append(action)
 def _eligible(self):
  if self.uc.reg_read(UC_ARM_REG_PRIMASK):return None
  ceiling=self.priorities[self.active[-1]] if self.active else 4
  ready=[i for i in self.pending if self.priorities[i]<ceiling]
  return min(ready,key=lambda i:(self.priorities[i],i)) if ready else None
 def _code(self,uc,address,size,user):
  self._steps+=1
  assert self._steps<2000000,'interrupt execution bound'
  for event in self.events.pop(address,[]):event(self)
  if self._eligible() is not None:
   self._irq_trap=True;uc.emu_stop();return
  super()._code(uc,address,size,user)
 def execute(self,address,stop=STOP,count=300000):
  resume=address
  while True:
   self._irq_trap=False
   self.uc.emu_start(resume|1,stop,count=count)
   resume=self.uc.reg_read(UC_ARM_REG_PC)
   if self._irq_trap:
    self._deliver(self._eligible());continue
   assert self.inject is None,'legacy injection is disabled in deterministic IRQ replay'
   if resume!=stop and resume!=self.pause:raise AssertionError(f'instruction limit: {resume:#x}, entry {address:#x}')
   return
 def _deliver(self,irq):
  self.pending.remove(irq);uc=self.uc;sp=uc.reg_read(UC_ARM_REG_SP)
  saved=[uc.reg_read(r) for r in STACKED];callee=[uc.reg_read(r) for r in CALLEE]
  mask=uc.reg_read(UC_ARM_REG_PRIMASK);padding=sp&4;frame=sp-padding-32
  raw=struct.pack('<8I',*saved);self.put(frame,raw)
  # A bounded stack envelope; deeper nested envelopes have separate guards.
  guard=frame-768;canary=bytes(range(16));old=self.read(guard,16);self.put(guard,canary)
  uc.reg_write(UC_ARM_REG_SP,frame);uc.reg_write(UC_ARM_REG_LR,IRQ_RETURN|1)
  self.active.append(irq);self.irq_log.append(('enter',irq,len(self.active)))
  self.execute(self.handlers[irq],IRQ_RETURN)
  assert uc.reg_read(UC_ARM_REG_SP)==frame,'IRQ stack imbalance'
  assert [uc.reg_read(r) for r in CALLEE]==callee,'IRQ callee-saved register clobber'
  assert self.read(frame,32)==raw,'IRQ hardware exception frame clobber'
  assert self.read(guard,16)==canary,'IRQ nested stack canary clobber'
  assert uc.reg_read(UC_ARM_REG_PRIMASK)==mask,'IRQ PRIMASK changed'
  self.put(guard,old);self.active.pop();self.irq_log.append(('exit',irq,len(self.active)+1))
  if irq==3:
   self._uart0_arrive()
   if self.uart0_queue:self.pend(3)
  for reg,value in zip(STACKED,saved):uc.reg_write(reg,value)
  uc.reg_write(UC_ARM_REG_SP,sp)


def _native_contract(image,facts,code):
 handlers={i:struct.unpack_from('<I',image.app,0x40+4*i)[0]&~1 for i in range(6)}
 assert handlers[4]==facts['functions']['irq'],'UART1 vector binding'
 timer=code.body(handlers[1]);literals=[i.literal for i in timer if i.literal is not None]
 flags=[a for a in set(literals) if 0x20000000<=a<0x20000100 and literals.count(a)>=2]
 assert len(flags)==1,'timer flag literal role'
 a8=flags[0]
 # Resolve the seven native calls gated by measurement-enable bit1.
 gate=next(i for i in timer if i.op=='lsls' and i.args=='r0, r0, #0x1e' and code.ins[i.at+2].op=='bpl')
 gate_end=code.ins[gate.at+2].target
 enabled_calls=[i.target for i in timer if gate.at<i.at<gate_end and i.op=='bl']
 assert len(enabled_calls)==7,'enabled timer protection chain'
 cmp=next(i.target for i in reversed(code.body(handlers[0])) if i.op=='bl')
 cmp_body=code.body(cmp);cmp_enable=next(i.literal for i in cmp_body if i.literal is not None)
 # Native wake routine: an ISR callee with this flag literal and a 200-tick gate.
 wake=[]
 for call in timer:
  if call.op!='bl':continue
  body=code.body(call.target)
  if any(i.literal==a8 for i in body) and any(i.op=='cmp' and i.args=='r0, #0xc8' for i in body) and any([(j.op,j.args) for j in code.window(i.at,3)]==[('ldrb','r1, [r0]'),('orrs','r1, r6'),('strb','r1, [r0]')] for i in body):wake.append((call.target,body))
 assert len(wake)==1,'native wake-path role'
 wake,body=wake[0]
 measurement=[]
 for call in timer:
  if call.op!='bl':continue
  b=code.body(call.target)
  if any(i.literal==a8 for i in b) and any(i.op=='ldrh' and i.args=='r6, [r5, #0x28]' for i in b):measurement.append((call.target,b))
 assert len(measurement)==1,'native slow flag producer role'
 measure,mbody=measurement[0]
 slow_counter=next(i.literal for i in mbody if i.op=='ldr' and i.args.startswith('r5, [pc,'))+0x28
 slow_store=next(i.at for i in mbody if i.op=='strb' and i.args=='r1, [r2]' and code.ins[i.at-2].op=='orrs')
 status=next(i.literal for i in body if i.op=='ldr' and i.args.startswith('r7, [pc,'))
 counter=next(i.literal for i in body if i.op=='ldr' and i.args.startswith('r4, [pc,'))
 # Main cleanup is identified by the exact clear-bit2/set-bit3 RMW shape.
 clean=[]
 for at in code.ins:
  w=code.window(at,7)
  if len(w)==7 and [(i.op,i.args) for i in w]==[
   ('ldrb','r0, [r5]'),('orrs','r0, r6'),('b',hex(at+8)),
   ('b',hex(at+14)),('movs','r1, #0xfb'),('ands','r0, r1'),('strb','r0, [r5]')]:clean.append(at)
 assert len(clean)==1,'main flag cleanup role'
 return dict(handlers=handlers,flags=a8,progress=a8+1,startup=a8+2,wake=wake,
  wake_status=status,wake_counter=counter+12,cleanup=clean[0],measurement=measure,slow_counter=slow_counter,slow_store=slow_store,enabled_calls=enabled_calls,cmp=cmp,cmp_enable=cmp_enable)


def validate_interrupts(original,patched,facts,build):
 rows=[];code=Code(original.app);native=_native_contract(original,facts,code)
 patched_code=Code(patched.app)
 snapshots=[i.at+i.size for i in patched_code.ins.values() if i.at>=len(original.app) and i.op=='cpsid' and [(j.op,j.args) for j in patched_code.window(i.at+i.size,3)]==[('ldr','r0, [r4]'),('ldrh','r1, [r4, #0x4]'),('ldrh','r2, [r4, #0x6]')]]
 assert len(snapshots)==1,'remote bounded RAM snapshot role'
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('interrupt-'+name+': '+str(exc)) from exc
  rows.append(dict(name='interrupt-'+name,passed=True))
 def board(image=patched):
  m=InterruptMachine(image,facts);m.defaults(1)
  m.put(native['startup'],(601).to_bytes(2,'little'));m.put(native['flags'],b'\2')
  m.put(native['cmp_enable'],bytes([m.num(native['cmp_enable'])|32]));m.put(0x50002000,(1<<13).to_bytes(4,'little'))
  return m
 def all_irqs(m):
  for irq in (3,2,1,0):m.pend(irq)
 def order(m):return [i for kind,i,depth in m.irq_log if kind=='enter']
 def priorities():
  from .hardware_tests import discover_hardware
  hw=discover_hardware(original,facts)
  m=board();m.uc.mem_map(0x45000000,0x1000)
  for irq in range(6):
   assert hw['irq'][irq]==native['handlers'][irq],'native IRQ vector role'
   m.run(hw['irq_init'][irq])
   assert m.num(0x45000000+4*irq,4)==(0x67,0x54,0x55,0x58,0x59,0x5a)[irq],'native IRQMUX source'
   assert m.num(0xe000e400+irq)>>6==PRIORITIES[irq],'native NVIC priority'
 check('native-priorities-and-vectors',priorities)
 def progress():
  m=board();m.pend(1);m.idle()
  assert m.num(native['progress'])==0x80,'timer0 progress bit7'
  for missing in range(8):
   m.put(native['progress'],bytes([255^(1<<missing)]));m.put(0x50009010,b'\0'*4)
   m.pend(2);m.idle()
   assert m.num(0x50009010,4)==0,'incomplete progress fed watchdog'
   assert m.num(native['progress'])==255^(1<<missing),'incomplete progress cleared'
  m.put(native['progress'],b'\xff');m.pend(2);m.idle()
  assert m.num(0x50009010,4)==0x55 and m.num(native['progress'])==0,'complete progress feed/clear'
 check('native-progress-mask',progress)
 def masked():
  m=board();m.uc.reg_write(UC_ARM_REG_PRIMASK,1);all_irqs(m);m.idle();assert not m.irq_log
  m.uc.reg_write(UC_ARM_REG_PRIMASK,0);m.idle();assert order(m)==[0,1,2,3],'pending priority order'
 check('masked-pending-and-priority',masked)
 def nested():
  m=board();values=[0x12340000+i for i in range(8)]
  for r,v in zip(CALLEE,values):m.uc.reg_write(r,v)
  # UART1 native handler is interrupted by UART0, then TIMR0, then CMP.
  m.at(m.handlers[4],lambda b:b.pend(3));m.at(m.handlers[3],lambda b:b.pend(1))
  def timer(b):b.pend(2);b.pend(0)
  m.at(m.handlers[1],timer);m.pend(4);m.idle()
  assert order(m)==[4,3,1,0,2],'nested/equal-priority deferral'
  assert max(x[2] for x in m.irq_log)==4,'native nested depth'
  assert [m.uc.reg_read(r) for r in CALLEE]==values,'interrupted callee registers'
 check('nested-equal-priority-and-exception-ABI',nested)
 def coexistence():
  for info,cmd in ((b'\5',0x64),(b'\5\1',0x64),(b'\6',0x64),(b'\0\0',0x4b)):
   control=board();control.put(control.remote['history_count'],b'\1\0')
   snapshot=cmd==0x64 and info in (b'\5',b'\6')
   if not snapshot:all_irqs(control);control.idle()
   expected=query(control,info=info,command=cmd)
   m=board();m.put(m.remote['history_count'],b'\1\0')
   boundary=snapshots[0] if snapshot else m.remote['history_transfer'] if cmd==0x4b else facts.get('storage_diagnostics',facts.get('cutoff'))['flash_read']
   packet=ascii_frame(1,0x51)
   def arrival(b):
    if snapshot:assert b.uc.reg_read(UC_ARM_REG_PRIMASK)==1,'snapshot IRQ injection was not masked'
    all_irqs(b);b.uart0_receive(packet)
   m.at(boundary,arrival);actual=query(m,info=info,command=cmd)
   assert actual==expected and actual is not None,'diagnostic/history response changed'
   assert order(m)[:4]==[0,1,2,3] and set(order(m))=={0,1,2,3},'missing native IRQ delivery'
   assert set(native['enabled_calls'])<=m.executed,'native enabled measurement/fast/protection chain absent'
   assert native['cmp'] in m.executed and not m.num(0x50002000,4)&(1<<13),'native CMP discharge trip absent'
   d=facts['marker_uart0'];assert m.num(d['uart0_state'])==4,'UART0 native RX did not complete frame'
   assert m.read(d['uart0_rx'],len(packet))==packet,'UART0 frame corrupted during diagnostic/history'
   previous=m.callback
   def sender(b,pc):
    if pc==d['uart0_sender']:b.ret();return True
    return bool(previous and previous(b,pc))
   m.callback=sender;m.run(d['uart0_dispatch']);m.callback=previous
   from .selftest import ascii_payload
   response=m.read(d['uart0_state']+1,m.num(d['uart0_tx_length'],2))
   assert ascii_payload(response,1)[0]==0,'deferred UART0 native parser/encoder failed'
   assert m.num(native['progress'])&128,'native timer progress absent'
   assert not m.pending,'IRQ backlog after diagnostic/history'
 check('diagnostics-history-native-coexistence',coexistence)
 def flag_race():
  def cleanup(preempt=False,coalesce=False):
   m=board(original if build.get('scheduler_atomic') else patched);a=native['flags'];m.put(a,b'\4')
   m.uc.reg_write(UC_ARM_REG_R5,a);m.uc.reg_write(UC_ARM_REG_R6,8)
   m.put(native['wake_status'],b'\x20' if not coalesce else b'\0')
   m.put(native['wake_counter'],(200).to_bytes(2,'little'))
   observed=[]
   if preempt:m.at(native['cleanup']+2,lambda b:b.pend(1))
   if coalesce:
    # The actual measurement sequencer reaches its 200th tick, ORs bit2
    # that was already set, and records backlog. No independent update exists.
    m.put(a,b'\6');m.put(native['slow_counter'],(199).to_bytes(2,'little'))
    m.at(native['cleanup']+2,lambda b:b.pend(1))
    m.at(native['slow_store'],lambda b:observed.append(b.num(a)))
   m.execute(native['cleanup'],native['cleanup']+14)
   return m,observed
  m,_=cleanup();assert m.num(native['flags'])==8,'cleanup control'
  # No preemption: native wake after cleanup retains independent enable bit1.
  m.pend(1);m.idle();assert m.num(native['flags'])==10,'native wake control'
  raced,_=cleanup(True);assert native['wake'] in raced.executed,'native wake path did not execute'
  assert raced.num(native['flags'])==8,'controlled old-value overwrite changed'
  assert raced.num(native['wake_status'])&32==0,'wake transition not completed'
  coalesced,seen=cleanup(coalesce=True);assert seen==[6] and coalesced.num(native['flags'])==10,'already-set slow flag coalescing'
  assert native['measurement'] in coalesced.executed and coalesced.num(native['slow_counter'],2)==0,'native slow flag producer not completed'
 check('A8-native-wake-lost-update-and-coalescing-controls',flag_race)
 rows[-1].update(kind='characterization',observed_oem_lost_update=True,control_image='original' if build.get('scheduler_atomic') else 'patched-reference',synthetic_call_state=True,full_system_reachability_proven=False,physical_occurrence_proven=False)
 if build.get('checkpoint_before_reset'):
  def checkpoint():
   m=board();s=facts['service'];r=facts['ram'];m.put(r['group0'],bytes([m.num(r['group0'])|8]))
   m.run(m.f['serializer']);m.nv_ops.clear();m.nv_step=0
   # The wrapper masks the runtime snapshot, then the contextual IAP hook
   # restores the caller's mask before flash work. Pending events wait for
   # that actual restore boundary, before the native reset veneer.
   queued=[]
   def flash(b):
    queued.append(bool(b.uc.reg_read(UC_ARM_REG_PRIMASK)));all_irqs(b)
   m.at(m.f['capacity_save'],flash);m.pause=facts['power_rtc']['reset']
   m.feed(ascii_frame(1,0x45,b'\0\6\0'));site=facts['hooks']['hook_dispatch'];m.execute(site,site+4)
   assert queued==[True],('checkpoint snapshot is not masked',queued)
   assert len(m.nv_ops)==4,'checkpoint flash transaction changed'
   assert order(m)==[0,1,2,3] and not m.pending,'checkpoint IRQ restore/delivery'
   assert m.uc.reg_read(UC_ARM_REG_PRIMASK)==0,'checkpoint mask restore'
  check('checkpoint-native-coexistence',checkpoint)
 assert {x['name'] for x in rows}==set(REQUIRED+(FULL_REQUIRED if build.get('checkpoint_before_reset') else ()))
 return rows
