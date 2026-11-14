"""UART0 native FIFO/IRQ, parser and snapshot regression for early master polls.

Logical character arrivals and silence are explicit hardware inputs. No physical
latency or cycle-accurate peripheral behavior is claimed.
"""
from .interrupt_tests import InterruptMachine,PRIORITIES,CALLEE
from .machine import ascii_frame
from .thumb import Code,encode_bl
from unicorn.arm_const import UC_ARM_REG_PRIMASK,UC_ARM_REG_SP

REQUIRED=tuple('polling-'+s for s in (
 'guarded-native-contract','valid-native-frame-early','reject-and-recover',
 'expiry-failure-offline','counter-reset-and-broadcast','FIFO-silence-and-turnaround',
 'IRQ-ownership-and-mask','deadline-orders-and-duplicates','round-and-aggregate',
 'native-UART0-timing','auto-address-and-role-gates','CCL-and-Full-override'))

class PollMachine(InterruptMachine):
 """NVIC write-one semantics; UART0 silence is separate from final arrival."""
 def __init__(self,image,facts):
  self.nvic_enabled=0x3f;self.rx_silence=False;self.steps=[]
  self.threshold=6;self.threshold_mode='gt';self.now=0;self.last_arrival=None
  self.character_ticks=16*156*10;self.timeout_ticks=self.character_ticks*10
  super().__init__(image,facts)
 def rx_ready(self):
  threshold=len(self.uart0_queue)>self.threshold if self.threshold_mode=='gt' else len(self.uart0_queue)>=self.threshold
  return bool(threshold or self.rx_silence and self.uart0_queue)
 def _read(self,uc,access,address,size,value,user):
  if address in (0xe000e100,0xe000e180):
   self.put(address,self.nvic_enabled.to_bytes(4,'little'));return
  if address==0x50010008:
   status=(1<<16 if self.rx_ready() else 0)|(1<<21 if self.rx_silence and self.uart0_queue and not self.uart0_wire else 0)
   status|=1<<27 if self.num(0x50010004,4)&0x40 else 0
   self.put(address,status.to_bytes(4,'little'));return
  super()._read(uc,access,address,size,value,user)
 def _write(self,uc,access,address,size,value,user):
  if address==0xe000e100:self.nvic_enabled|=value
  elif address==0xe000e180:self.nvic_enabled&=~value
  super()._write(uc,access,address,size,value,user)
 def _eligible(self):
  if self.uc.reg_read(UC_ARM_REG_PRIMASK):return None
  ceiling=self.priorities[self.active[-1]] if self.active else 4
  ready=[i for i in self.pending if self.nvic_enabled&(1<<i) and self.priorities[i]<ceiling]
  return min(ready,key=lambda i:(self.priorities[i],i)) if ready else None
 def _deliver(self,irq):
  super()._deliver(irq)
  if irq==3 and not self.rx_ready():self.pending.discard(3)
 def advance(self,ticks):
  assert ticks>=0
  self.now+=ticks
  if self.uart0_queue and self.last_arrival is not None and self.now-self.last_arrival>=self.timeout_ticks:
   self.rx_silence=True;self.pend(3);self.idle()
 def arrive(self,byte):
  assert len(self.uart0_queue)<8,'UART0 modeled FIFO overflow'
  self.uart0_queue.append(byte);self.last_arrival=self.now;self.rx_silence=False
  if self.rx_ready():self.pend(3);self.idle()
 def receive(self,packet,silence=True):
  self.rx_silence=silence;self.uart0_receive(packet);self.idle()
 def silence(self):self.rx_silence=True;self.pend(3);self.idle()
 def turnaround(self):
  for _ in range(100):
   if not self.num(0x50010004,4)&0x40:return
   self.pend(3);self.idle()
  raise AssertionError('UART0 native TX turnaround bound')
 def _code(self,uc,address,size,user):
  self.steps.append((address,uc.reg_read(UC_ARM_REG_PRIMASK),self.nvic_enabled))
  super()._code(uc,address,size,user)


def validate_polling(original,patched,facts,build):
 from .polling import discover_polling
 d=discover_polling(original,facts);rows=[]
 def check(name,fn):
  try:detail=fn()
  except Exception as exc:raise AssertionError('polling-'+name+': '+str(exc)) from exc
  rows.append(dict(name='polling-'+name,passed=True,**(detail or {})))
 def board(count=11):
  m=PollMachine(patched,facts);m.defaults(0);m.put(d['maximum'],bytes([count]));return m
 def start(m):
  m.execute(d['start_site'],d['start_site']+4);m.turnaround()
 def evaluate(m):m.execute(d['evaluate_site'],d['evaluate_site']+4)
 def ticks(m,n):
  for _ in range(n):m.pend(1);m.idle()
 def packet(address=1):return ascii_frame(address,0x5a,bytes(range(32)))
 def guarded():
  assert build.get('polling')==dict(d,enabled=True),'published source contract mismatch'
  for name,site in d['hooks'].items():assert patched.app[site:site+4]==encode_bl(site,build['entries'][name]),'polling veneer mismatch'
  return dict(native_parser=d['parser'],native_decode=d['decode'],ram_bytes=0)
 check('guarded-native-contract',guarded)
 def valid():
  m=board();start(m);m.receive(packet());evaluate(m)
  assert not m.num(d['flags'])&1,'valid complete response still waits for tick30'
  assert m.num(d['online'],4)&2,'native online update missing'
  assert d['parser'] in m.executed and d['decode'] in m.executed,'native parsing/decoding absent'
  assert m.num(d['state'])==0,'completed frame not consumed'
  return dict(frame_bytes=82)
 check('valid-native-frame-early',valid)
 def badframes():
  valid=packet();bad_checksum=bytearray(valid);bad_checksum[-2]=ord('0') if valid[-2]!=ord('0') else ord('1')
  bad_length=bytearray(valid);bad_length[9:13]=b'0042'
  cases=[bytes(bad_checksum),bytes(bad_length),packet(2),ascii_frame(1,0x59,bytes(range(32))),valid[:-10]+b'\r',valid[:-1]+b'X',valid[:20]+b'G'+valid[21:]]
  for bad in cases:
   m=board();start(m);ticks(m,7);m.receive(bad);evaluate(m)
   assert m.num(d['flags'])&1 and m.num(d['index'])==1,'invalid frame finished transaction'
   assert m.num(d['counter'])==7 and m.num(d['failures']+1)==0,'rejection changed original deadline/failure'
   assert m.num(d['state'])==0,'invalid frame not discarded'
   m.receive(valid);evaluate(m)
   assert not m.num(d['flags'])&1 and m.num(d['online'],4)&2,'valid-after-invalid failed'
  m=board();start(m)
  for _ in range(29):
   ticks(m,1);m.receive(bytes(bad_checksum));evaluate(m)
  assert m.num(d['counter'])==29 and m.num(d['failures']+1)==0,'bad-frame stream extended deadline'
  ticks(m,1);evaluate(m)
  assert m.num(d['failures']+1)==1 and not m.num(d['flags'])&1,'bad-frame timeout not counted once'
  return dict(cases=len(cases))
 check('reject-and-recover',badframes)
 def expiry():
  m=board(1);m.put(d['online'],(3).to_bytes(4,'little'))
  for attempt in range(11):
   start(m);ticks(m,29);evaluate(m)
   assert m.num(d['flags'])&1,'no response ended before native deadline'
   ticks(m,1);evaluate(m)
   assert not m.num(d['flags'])&1,'expiry did not finish'
   assert m.num(d['failures']+1)==min(attempt+1,10),'native failure count changed'
   evaluate(m);assert m.num(d['failures']+1)==min(attempt+1,10),'expiry counted twice'
  assert not m.num(d['online'],4)&2,'native offline threshold missing'
 check('expiry-failure-offline',expiry)
 def resets():
  m=board();start(m);ticks(m,12);m.receive(packet());evaluate(m);start(m)
  assert m.num(d['index'])==2 and m.num(d['counter'])==0,'next transaction counter not reset'
  ticks(m,29);evaluate(m);assert m.num(d['flags'])&1,'next transaction deadline shortened'
  ticks(m,1);evaluate(m);assert not m.num(d['flags'])&1
  for flag in (0x10,0x20):
   m=board();m.put(d['flags'],bytes([flag]))
   m.execute(d['start_site'],d['start_site']+4)
   assert m.num(d['state'])==2,'broadcast did not enter TX state'
   evaluate(m)
   assert m.num(d['state'])==2,'broadcast evaluator cleared in-flight TX state before deadline'
   m=board();m.put(d['flags'],bytes([flag]));start(m);m.receive(packet());evaluate(m)
   assert m.num(d['flags'])&1,'broadcast ended early'
   ticks(m,30);evaluate(m);assert not m.num(d['flags'])&0x33,'broadcast expiry changed'
 check('counter-reset-and-broadcast',resets)
 def fifo():
  m=board();start(m);assert len(m.uart0_output)==18,'native request length'
  assert m.num(d['state'])==0 and not m.num(0x50010004,4)&0x40,'native turnaround absent'
  m.receive(packet(),silence=False);evaluate(m)
  assert m.num(d['flags'])&1 and m.num(d['state'])==1,'frame completed before silence'
  m.silence();evaluate(m);assert not m.num(d['flags'])&1,'silence completion failed'
  return dict(fifo_depth=8,character_bits=10,baud=19200,nominal_silence_ms=5.2,physical_timing_proven=False)
 check('FIFO-silence-and-turnaround',fifo)
 def timing():
  from .hardware_tests import discover_hardware,HardwareModel
  hw=discover_hardware(original,facts);cfg=HardwareModel(patched,hw)
  cfg.put(hw['clock_ram'],48000000);cfg.run(hw['uart_init'][0])
  divider=cfg.num(0x50010008)&0x3fff;control=cfg.num(0x50010004)
  threshold=(cfg.num(0x5001000c)>>16)&7;timeout=control>>24
  assert divider==155 and timeout==10 and threshold==6,'UART0 native initial timing changed'
  assert control&(1<<14) and control&(1<<4),'UART0 RX interrupts disabled'
  assert not control&((1<<18)|(1<<19)|(3<<22)),'UART0 not 8N1'
  for mode in ('gt','ge'):
   m=board();m.threshold=threshold;m.threshold_mode=mode
   m.character_ticks=16*(divider+1)*10;m.timeout_ticks=timeout*m.character_ticks
   start(m)
   for byte in packet():m.advance(m.character_ticks);m.arrive(byte)
   evaluate(m);assert m.num(d['flags'])&1,'early before native silence'
   m.advance(m.timeout_ticks-1);evaluate(m)
   assert m.num(d['flags'])&1,'early before silence deadline'
   m.advance(1);evaluate(m)
   assert not m.num(d['flags'])&1 and m.num(d['online'],4)&2,'native timed reception failed'
  return dict(divider=divider,clock_hz=48000000,timeout_characters=timeout,threshold=threshold,
              nominal_silence_seconds=timeout*16*(divider+1)*10/48000000,
              threshold_interpretations=['gt','ge'],CPU_time_modeled=False)
 check('native-UART0-timing',timing)
 def irq():
  code=Code(patched.app);entry=build['entries']['hook_poll_evaluate'];body=code.body(entry)
  # Timer remains deliverable while UART0 owns the buffer, including during parse.
  for mask in (0,1):
   for enabled in (0x3f,0x37):
    m=board();start(m);m.receive(packet());m.nvic_enabled=enabled;m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
    before=m.num(d['counter']);m.at(d['parser'],lambda b:b.pend(1));sp=m.uc.reg_read(UC_ARM_REG_SP)
    evaluate(m)
    assert m.nvic_enabled==enabled and m.uc.reg_read(UC_ARM_REG_PRIMASK)==mask,'incoming mask/NVIC state changed'
    assert m.uc.reg_read(UC_ARM_REG_SP)==sp,'wrapper stack imbalance'
    assert not m.num(d['flags'])&1,'timer race lost completion'
    if not mask:assert any(e[:2]==('enter',1) for e in m.irq_log),'timer suppressed during parsing'
  # A queued foreign frame must not overwrite the accepted record during parse.
  base=board();start(base);base.receive(packet());evaluate(base)
  record=base.read(d['records']+30,30)
  from .interrupt_tests import _native_contract
  native=_native_contract(original,facts,Code(original.app))
  for pc in (d['parser'],d['decode']):
   m=board();start(m);m.receive(packet())
   m.put(native['startup'],(601).to_bytes(2,'little'));m.put(native['flags'],b'\2')
   m.put(native['cmp_enable'],bytes([m.num(native['cmp_enable'])|32]))
   m.put(0x50002000,(1<<13).to_bytes(4,'little'))
   def competing(b):
    assert not b.nvic_enabled&8,'UART0 buffer not owned during native consume'
    b.uart0_receive(ascii_frame(2,0x5a,bytes([0xaa])*32));b.pend(0);b.pend(1)
   m.at(pc,competing);evaluate(m)
   assert m.read(d['records']+30,30)==record,'queued foreign frame overwrote native record'
   assert any(e[:2]==('enter',0) for e in m.irq_log),'CMP suppressed during consume'
   assert any(e[:2]==('enter',1) for e in m.irq_log),'timer suppressed during consume'
   assert set(native['enabled_calls'])<=m.executed,'enabled protection chain absent during consume'
   assert native['cmp'] in m.executed and not m.num(0x50002000,4)&(1<<13),'CMP trip absent during consume'
  # Every wrapper instruction boundary sees a timer at the expiry edge.
  wrappers=[code.body(build['entries'][name]) for name in ('hook_poll_start','hook_poll_evaluate')]
  # Direct BL targets include lock/unlock and the bounded validator.
  callees={i.target for body in wrappers for i in body if i.op=='bl'}
  boundaries=sorted({i.at for body in wrappers for i in body} |
                    {i.at for target in callees for i in code.body(target)})
  injected=0
  for pc in boundaries:
   m=board();start(m);ticks(m,29);m.receive(packet())
   for reg in CALLEE:m.uc.reg_write(reg,0x11220000+reg)
   before=[m.uc.reg_read(reg) for reg in CALLEE];sp=m.uc.reg_read(UC_ARM_REG_SP)
   m.at(pc,lambda b:b.pend(1));evaluate(m);start(m)
   # Conditional reject/broadcast paths are covered separately below; only
   # executed success-path boundaries count as this injection schedule.
   if pc in m.events:continue
   injected+=1
   assert [m.uc.reg_read(reg) for reg in CALLEE]==before,'poll ABI callee clobber'
   assert m.uc.reg_read(UC_ARM_REG_SP)==sp,'poll ABI stack imbalance'
   assert m.uc.reg_read(UC_ARM_REG_PRIMASK)==0 and m.nvic_enabled==0x3f,'mask not restored'
   assert m.num(d['index'])==2 and m.num(d['failures']+1)==0,'boundary double/lost completion'
   assert m.num(d['counter'])<=1,'prior transaction counter carried forward'
  # Explicit start/reset boundary matrix, including incoming disabled states.
  start_boundaries=[i.at for i in code.body(build['entries']['hook_poll_start'])]
  for pc in start_boundaries:
   for mask in (0,1):
    for enabled in (0x3f,0x37):
     m=board();m.put(d['counter'],bytes([29]));m.nvic_enabled=enabled
     m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
     for reg in CALLEE:m.uc.reg_write(reg,0x11220000+reg)
     before=[m.uc.reg_read(reg) for reg in CALLEE];sp=m.uc.reg_read(UC_ARM_REG_SP)
     m.at(pc,lambda b:b.pend(1));m.execute(d['start_site'],d['start_site']+4)
     assert not m.events,'start boundary injection not reached'
     assert m.uc.reg_read(UC_ARM_REG_PRIMASK)==mask and m.nvic_enabled==enabled,'start mask/NVIC changed'
     assert [m.uc.reg_read(reg) for reg in CALLEE]==before and m.uc.reg_read(UC_ARM_REG_SP)==sp,'start ABI changed'
     assert m.num(d['counter'])<=1 and m.num(d['flags'])&1 and not m.num(d['flags'])&2,'start carried old expiry'
  # Count exclusion instructions in both calls, including callees.
  m=board();m.steps=[];start(m);m.receive(packet());evaluate(m)
  longest=run=0
  for _,mask,_ in m.steps:
   run=run+1 if mask else 0;longest=max(longest,run)
  assert longest<=32,'global exclusion includes excessive work or frame parsing'
  return dict(incoming_masks=[0,1],uart0_enable_states=[False,True],
              timer_boundary_cases=injected,start_boundary_mask_cases=4*len(start_boundaries),
              max_global_masked_instructions=longest)
 check('IRQ-ownership-and-mask',irq)
 def deadline():
  for order in ('rx-first','timer-first'):
   m=board();start(m);ticks(m,29)
   if order=='rx-first':m.receive(packet());evaluate(m);ticks(m,1)
   else:ticks(m,1);evaluate(m);m.receive(packet());evaluate(m)
   assert not m.num(d['flags'])&1,'boundary transaction not finished'
   assert m.num(d['failures']+1)==(order=='timer-first'),'deadline accounted incorrectly'
  # OEM expiry is serviced in main; it is not a latched RX timestamp.
  # A ready valid response wins if both events precede evaluator service.
  for order in ('rx-then-expiry','expiry-then-rx'):
   m=board();start(m);ticks(m,29)
   if order=='rx-then-expiry':m.receive(packet());ticks(m,1)
   else:ticks(m,1);m.receive(packet())
   evaluate(m)
   assert not m.num(d['flags'])&1 and m.num(d['online'],4)&2,'ready/expiry native compatibility lost'
   assert m.num(d['failures']+1)==0,'ready response counted as failure'
   snapshot=(m.num(d['flags']),m.num(d['online'],4),m.num(d['failures']+1))
   evaluate(m)
   assert snapshot==(m.num(d['flags']),m.num(d['online'],4),m.num(d['failures']+1)),'ready/expiry evaluated twice'
  m=board();start(m);m.receive(packet());evaluate(m);m.receive(packet());evaluate(m)
  start(m);evaluate(m);assert m.num(d['flags'])&1 and m.num(d['index'])==2,'duplicate crossed transaction'
  m.receive(packet(1));evaluate(m)
  assert m.num(d['flags'])&1 and m.num(d['failures']+2)==0,'late prior address completed new transaction'
  m.receive(packet(2));evaluate(m)
  assert not m.num(d['flags'])&1 and m.num(d['online'],4)&4,'new address response lost after late frame'
 check('deadline-orders-and-duplicates',deadline)
 def rounds():
  m=board()
  for address in range(1,12):
   start(m);assert m.num(d['index'])==address
   m.receive(packet(address));evaluate(m)
   assert bool(m.num(d['flags'])&4)==(address==11),'native round gate moved'
   if address<11:
    m.executed.discard(d['ccl']);m.run(d['aggregate'])
    assert d['ccl'] not in m.executed,'CCL updated before full round'
  assert m.num(d['online'],4)&0xffe==0xffe,'round snapshot online mask'
  m.executed.discard(d['ccl']);m.run(d['aggregate'])
  assert d['ccl'] in m.executed and not m.num(d['flags'])&4,'completed round not consumed'
  m.executed.discard(d['ccl']);m.run(d['aggregate'])
  assert d['ccl'] not in m.executed,'same round consumed twice'
  return dict(slaves=11,requests=11,aggregate_per_response=False)
 check('round-and-aggregate',rounds)
 def roles():
  for count,address in ((0,0),(11,1),(11,0)):
   m=board(count);m.put(facts['ram']['address'],bytes([address]))
   # Use the actual role/round gate, not a direct call to the send helper.
   m.execute(d['main_dispatch'],d['main_dispatch_end'])
   assert bool(m.num(d['flags'])&1)==(count>0 and address==0),'master/slave routing changed'
  m=board();m.put(d['flags'],b'\4');m.execute(d['main_dispatch'],d['main_dispatch_end'])
  assert m.num(d['index'])==0,'round-complete gate started another poll'
  for successor,expected in ((False,1),(True,2)):
   m=board(1);m.put(facts['ram']['group0']+7,b'\x20');start(m)
   info=bytearray(32);info[30]=0 if successor else 0x80
   m.receive(ascii_frame(1,0x5a,info));evaluate(m)
   assert m.num(d['maximum'])==expected,'native automatic chain extension changed'
  return dict(master_slave_routes=3,automatic_successor_cases=2)
 check('auto-address-and-role-gates',roles)
 def ccl():
  # Seed records as real completed responses; then run the original aggregate
  # entry, including Full's existing CCL wrapper when present in this image.
  def seeded(off=False):
   m=board();m.put(d['online'],(0xfff).to_bytes(4,'little'))
   m.put(facts['ram']['group0']+7,b'\x80');m.put(facts['ram']['group0']+3,b'\0')
   m.put(facts['ram']['words']+100,(14000).to_bytes(2,'little'))
   m.put(facts['ram']['words']+8,(3650).to_bytes(2,'little'))
   for i in range(12):
    data=bytearray(30);data[21]=1;data[26]=3;m.put(d['records']+30*i,data)
   if off:m.put(d['records']+29,b'\x20');m.put(d['records']+26,b'\0')
   m.put(d['system']+36,(15600).to_bytes(2,'little'));m.put(d['flags'],b'\4')
   return m
  m=seeded();m.run(d['aggregate'])
  assert m.num(d['system']+36,2)==15480,'ordinary 12A CCL step changed'
  m.run(d['aggregate']);assert m.num(d['system']+36,2)==15480,'CCL repeated without round'
  for _ in range(59):m.put(d['flags'],b'\4');m.run(d['aggregate'])
  assert m.num(d['system']+36,2)==8400,'60-update descent changed'
  for _ in range(70):m.put(d['flags'],b'\4');m.run(d['aggregate'])
  assert m.num(d['system']+36,2)==100,'130-update fallback changed'
  m=seeded(True);m.run(d['aggregate'])
  assert m.num(d['system']+36,2)==(100 if build.get('cutoff') else 15480),'Full Off override changed'
  return dict(first_at_840A_update=60,first_at_10A_update=130,physical_time_proven=False)
 check('CCL-and-Full-override',ccl)
 assert {r['name'] for r in rows}==set(REQUIRED)
 return rows
