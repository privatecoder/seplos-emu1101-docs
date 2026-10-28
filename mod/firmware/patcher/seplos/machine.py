"""Bounded real Cortex-M0 execution; UART/IAP hardware model only.

Derived from UART1-Parameter-Patch/tests/emulator.py. All code and RAM addresses
come from the input image's analysis/probes. No physical interfaces are opened.
"""
from collections import deque
import binascii
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PRIMASK, UC_CPU_ARM_CORTEX_M0
from .analysis import unique
from .thumb import Code,encode_bl
UART=0x50011000
STOP=0x3F000

class PowerLoss(RuntimeError):
 pass


def frame(address, command, data=b''):
 body=bytes([address,command,len(data)])+data
 return b'\x55'+body+binascii.crc_hqx(body,0).to_bytes(2,'big')+b'\xaa'


def ascii_frame(address, command, info=b''):
 length=len(info)*2
 check=(-(length+(length>>4)+(length>>8)))&15
 body=f'20{address:02X}46{command:02X}{(check<<12)|length:04X}{info.hex().upper()}'.encode()
 return b'~'+body+f'{(-sum(body))&0xffff:04X}'.encode()+b'\r'


def modbus_frame(body):
 crc=0xffff
 for byte in body:
  crc^=byte
  for _ in range(8):crc=(crc>>1)^(0xa001 if crc&1 else 0)
 return body+crc.to_bytes(2,'little')


class Machine:
 def __init__(self,image,facts):
  self.f=facts['functions']; self.r=facts.get('ram',{}); self.facts=facts
  self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
  self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
  self.uc.mem_map(0,0x40000); self.uc.mem_write(0,image.app)
  self.uc.mem_write(0x23000,b'\xff'*4096)
  self.uc.mem_write(0x25000,b'\xff'*8192)
  self.uc.mem_map(0x20000000,0x4000)
  self.uc.mem_map(0x40000000,0x10000)
  self.uc.mem_map(0x50000000,0x30000); self.uc.mem_map(0xE000E000,0x1000)
  self.uc.reg_write(UC_ARM_REG_SP,image.sp)
  self.uc.mem_write(0x50001000,(1<<9).to_bytes(4,'little'))
  self.queue=deque(); self.timeout=False; self.output=bytearray(); self.direction=[]
  self.trace=[]; self.tracing=False; self.executed=set(); self.saves=[]; self.record=None
  self.flash_reads=[]
  self.pause=None; self.callback=None; self.iap_fail=False; self.flash_ops=[]
  self.interrupt_data=None;self.inject=None;self.interrupted=False
  self.rtc_registers=bytearray(16);self.rtc_fail=False;self.rtc_transfers=[]
  cut=facts.get('cutoff',{});entry=cut.get('entries',{}).get('hook_cut_loader');site=cut.get('hooks',{}).get('hook_cut_loader')
  self.cutoff_entries=cut.get('entries',{}) if entry is not None and entry<len(image.app) and image.app[site:site+4]==encode_bl(site,entry) else {}
  self.real_parameter_flash=bool(self.cutoff_entries);self.nv_ops=[];self.nv_step=0;self.nv_fail_at=set();self.nv_cut_after=None
  service=facts.get('service',{});entry=service.get('entries',{}).get('hook_service_soc_iap');site=service.get('hooks',{}).get('hook_service_soc_iap')
  self.real_soc_flash=bool(entry is not None and entry<len(image.app) and image.app[site:site+4]==encode_bl(site,entry))
  if self.real_soc_flash:self.uc.mem_write(service['soc_primary'],b'\xff'*8192)
  self.uc.hook_add(UC_HOOK_MEM_READ,self._read)
  self.uc.hook_add(UC_HOOK_MEM_WRITE,self._write)
  self.uc.hook_add(UC_HOOK_CODE,self._code)

 def read(self,a,n=1):return bytes(self.uc.mem_read(a,n))
 def put(self,a,data):self.uc.mem_write(a,bytes(data))
 def num(self,a,n=1):return int.from_bytes(self.read(a,n),'little')
 def ret(self,value=None):
  if value is not None:self.uc.reg_write(UC_ARM_REG_R0,value)
  self.uc.reg_write(UC_ARM_REG_PC,self.uc.reg_read(UC_ARM_REG_LR))

 def _read(self,uc,access,address,size,value,user):
  if self.tracing and 0xC0<=address<self.facts['original_app_size']:
   self.flash_reads.append((address,size,self.num(address,size),uc.reg_read(UC_ARM_REG_PC)))
  if self.tracing and 0x20000000<=address<self.facts['sp']-256:
   self.trace.append(('r',address,size,self.num(address,size),uc.reg_read(UC_ARM_REG_PC)))
  if address==UART+8:
   control=self.num(UART+4,4)
   status=(1<<16 if self.queue else 0)|(1<<21 if self.queue and self.timeout else 0)|(1<<27 if control&0x40 else 0)
   self.put(address,status.to_bytes(4,'little'))
  elif address==UART+12:self.put(address,len(self.queue).to_bytes(4,'little'))
  elif address==UART:
   if not self.queue:raise AssertionError('FIFO underflow')
   self.put(address,self.queue.popleft().to_bytes(4,'little'))
   if not self.queue:self.timeout=False

 def _write(self,uc,access,address,size,value,user):
  if self.tracing and 0x20000000<=address<self.facts['sp']-256:
   self.trace.append(('w',address,size,value & ((1 << (size*8))-1),uc.reg_read(UC_ARM_REG_PC)))
  if address==UART:self.output.append(value&255)
  elif address==0x50001000:self.direction.append(bool(value&(1<<9)))

 def _code(self,uc,address,size,user):
  self.executed.add(address)
  if self.interrupt_data is not None and self.r and self.num(self.r['state'])==3:
   self.inject=self.interrupt_data;self.interrupt_data=None;uc.emu_stop();return
  if self.pause==address:
   uc.emu_stop();return
  if self.callback and self.callback(self,address):return
  if address==self.cutoff_entries.get('hook_cut_nv_write'):
   a=self.r['iap_buffer'];data=self.read(a,self.num(a+1));self.saves.append((0,data));self.record=data
  rtc=self.facts.get('power_rtc',{})
  if address==rtc.get('rtc_transfer'):
   a=rtc['rtc'];reg=self.num(a+3);n=self.num(a+0x8c);reading=bool(uc.reg_read(UC_ARM_REG_R0))
   assert self.num(a)==0xa2 and 0<=reg<reg+n<=16,'unexpected RTC I2C transfer'
   if not self.rtc_fail:
    if reading:self.put(a+10,self.rtc_registers[reg:reg+n])
    else:self.rtc_registers[reg:reg+n]=self.read(a+10,n)
   self.rtc_transfers.append({'read':reading,'register':reg,'data':list(self.read(a+10,n)),'failed':self.rtc_fail})
   self.ret(0 if self.rtc_fail else 1);return
  if address==self.f['iap_read']:
   if self.real_parameter_flash and uc.reg_read(UC_ARM_REG_R0)==0:return
   if self.real_soc_flash and uc.reg_read(UC_ARM_REG_R0)==6:return
   if self.record is not None and uc.reg_read(UC_ARM_REG_R0)==0:
    self.put(self.r['iap_buffer'],self.record);self.ret(1)
   else:self.ret(0)
  elif address==self.f['iap_write']:
   if 'iap_buffer' in self.r:
    a=self.r['iap_buffer'];data=self.read(a,self.num(a+1))
    block=uc.reg_read(UC_ARM_REG_R0);self.saves.append((block,data))
    if block==0:self.record=data
   if self.real_parameter_flash and uc.reg_read(UC_ARM_REG_R0)==0:return
   self.ret(1)
  elif address==self.f['iap_erase']:
   dest=uc.reg_read(UC_ARM_REG_R0)&~4095
   if (self.real_parameter_flash and dest in (0x25000,0x26000)) or (self.real_soc_flash and dest in (0x2b000,0x2c000)):
    self.nv_step+=1;self.nv_ops.append(('erase',dest))
    if self.nv_step not in self.nv_fail_at:self.put(dest,b'\xff'*4096)
    # OEM primitives end with CPSIE i, even for an originally masked caller.
    if self.real_soc_flash and dest in (0x2b000,0x2c000):uc.reg_write(UC_ARM_REG_PRIMASK,0)
    self.ret(0)
    if self.nv_cut_after==self.nv_step:raise PowerLoss('simulated power loss')
    return
   self.flash_ops.append(('erase',dest))
   assert dest==0x23000,'unexpected sector erase'
   if not self.iap_fail:self.put(dest,b'\xff'*4096)
   self.ret(0)
  elif address==self.f['iap_program']:
   dest=uc.reg_read(UC_ARM_REG_R0);source=uc.reg_read(UC_ARM_REG_R1);count=uc.reg_read(UC_ARM_REG_R2)
   if (self.real_parameter_flash and dest in (0x25000,0x26000)) or (self.real_soc_flash and dest in (0x2b000,0x2c000)):
    assert source==self.r['iap_buffer'] and count==(44 if dest<0x27000 else 6),'unexpected record programming'
    self.nv_step+=1;self.nv_ops.append(('program',dest,count))
    if self.nv_step not in self.nv_fail_at:self.put(dest,bytes(a&b for a,b in zip(self.read(dest,count*4),self.read(source,count*4))))
    if self.real_soc_flash and dest in (0x2b000,0x2c000):uc.reg_write(UC_ARM_REG_PRIMASK,0)
    self.ret(0)
    if self.nv_cut_after==self.nv_step:raise PowerLoss('simulated power loss')
    return
   self.flash_ops.append(('program',dest,count))
   assert dest==0x23000 and count==1 and 0x20000000<=source<self.facts['sp'],'unexpected programming request'
   if not self.iap_fail:self.put(dest,self.read(source,count*4))
   self.ret(0)

 def execute(self,address,stop=STOP,count=300000):
  self.uc.emu_start(address|1,stop,count=count)
  if self.inject is not None:
   incoming,self.inject=self.inject,None
   context=self.uc.context_save();resume=self.uc.reg_read(UC_ARM_REG_PC)
   self.uc.reg_write(UC_ARM_REG_SP,self.uc.reg_read(UC_ARM_REG_SP)-32)
   self.queue.extend(incoming);self.timeout=True
   while self.queue:self.run(self.f['irq'])
   self.uc.context_restore(context);self.interrupted=True
   self.uc.emu_start(resume|1,stop,count=count)
  actual=self.uc.reg_read(UC_ARM_REG_PC)
  if actual!=stop and actual!=self.pause:raise AssertionError(f'instruction limit: {actual:#x}, entry {address:#x}')

 def run(self,address,count=300000):
  sp=self.uc.reg_read(UC_ARM_REG_SP)
  self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
  self.execute(address,count=count)
  if self.pause is None:assert sp==self.uc.reg_read(UC_ARM_REG_SP),'stack imbalance'
  return self.uc.reg_read(UC_ARM_REG_R0)

 def capture(self,address):
  self.trace=[];self.flash_reads=[];self.tracing=True
  try:self.run(address)
  finally:self.tracing=False
  return self.trace[:]

 def feed(self,data,end=True):
  self.timeout=False
  for i in range(0,len(data),7):
   self.queue.extend(data[i:i+7]);self.run(self.f['irq'])
  if end and self.queue:self.timeout=True;self.run(self.f['irq'])

 def dispatch(self,patched=False):
  if patched:
   site=self.facts['hooks']['hook_dispatch'];sp=self.uc.reg_read(UC_ARM_REG_SP)
   self.execute(site,site+4)
   assert self.uc.reg_read(UC_ARM_REG_SP)==sp
  else:self.run(self.f['dispatch'])
  self.run(self.f['modbus'])

 def drain(self):
  for _ in range(100):
   if not self.num(UART+4,4)&0x40:return bytes(self.output)
   self.run(self.f['irq'])
  raise AssertionError('TX stuck')

 def transact(self,data,patched=False):
  self.output.clear();self.feed(data)
  if self.num(self.r['state'])==4:self.dispatch(patched)
  return self.drain()

 def payload(self):
  r=self.r;words=self.read(r['words'],120)
  return b'\x3c'+b''.join(words[i:i+2][::-1] for i in range(0,120,2))+b'\x1b'+self.read(r['small'],27)+b'\x08'+self.read(r['group0'],8)

 def defaults(self,address=0):
  self.record=None;self.run(self.cutoff_entries.get('hook_cut_loader',self.f['loader']))
  if 'modbus_gate' in self.r:self.put(self.r['modbus_gate'],b'\x80')
  self.put(self.r['address'],bytes([address]));self.put(self.r['name'],b'SYNTHETIC0')
  self.put(self.r['learned'],self.read(self.r['words']+116,2));self.saves.clear()


def run_start(trace,kind,size,count,stride):
 accesses=[e for e in trace if e[0]==kind and e[2]==size]
 hits=[]
 for j in range(len(accesses)-count+1):
  chunk=accesses[j:j+count];start=chunk[0][1]
  if all(e[1]==start+i*stride for i,e in enumerate(chunk)):
   # Require the exact maximal run, not an arbitrary subrange of a larger one.
   if j and accesses[j-1][1]+stride==start:continue
   if j+count<len(accesses) and accesses[j+count][1]==start+count*stride:continue
   hits.append(start)
 return unique(hits,f'{kind} {count}×{size} stride {stride} RAM trace')


def probe(image,facts):
 code=Code(image.app);f=facts['functions'];r={};facts['ram']=r
 m=Machine(image,facts)
 m.capture(f['loader'])
 trace=m.capture(f['lcd_read'])
 r['words']=run_start(trace,'r',2,60,2)
 r['small']=run_start(trace,'r',1,27,1)
 r['group0']=run_start(trace,'r',1,8,1)
 r['name']=run_start(trace,'r',1,10,1)
 writes=[e for e in trace if e[0]=='w']
 lcd_output=writes[0][1]-5
 r['lcd_meta']=writes[-1][1]-10
 payload=m.read(lcd_output+5,168)
 assert payload==m.payload()+m.read(r['name'],10),'OEM LCD payload structure mismatch'
 assert writes[-2][3]==0x47 and writes[-1][3]==175,'OEM LCD reply metadata mismatch'
 ser=m.capture(f['serializer'])
 swrites=[e for e in ser if e[0]=='w']
 r['iap_buffer']=swrites[0][1]-2
 m.capture(f['serializer']);assert m.record and m.record[0]==0xa0 and m.record[2]==0x3c and len(m.record)==171,'unexpected parameter IAP record'
 original=m.record
 m.put(r['words'],b'\0'*120);m.put(r['small'],b'\0'*27)
 m.run(f['loader']);assert m.payload()+m.read(r['name'],10)==payload,'original serializer/loader mismatch'
 # Stage a real LCD A1 and stop at the original validator to find shadow fields.
 context=m.uc.context_save();m.put(r['lcd_meta']+18,payload[:158]);m.pause=f['validator']
 stage=m.capture(f['lcd_write']);m.pause=None;m.uc.context_restore(context)
 r['shadow_words']=run_start(stage,'w',2,60,2)
 r['shadow_small']=run_start(stage,'w',1,27,1)
 # Original LCD capacity path independently identifies learned capacity and coulomb maximum.
 cap_events=[]
 # Read/write events between return of serializer and entry of capacity saver.
 ser_return=unique([i.at+i.size for i in code.body(f['lcd_write']) if i.op=='bl' and i.target==f['serializer']], 'LCD serializer return')
 def cb(board,pc):
  if pc==ser_return:board.trace=[];board.tracing=True
  if pc==f['capacity_save']:cap_events.extend(board.trace);board.tracing=False
  return False
 m.put(r['lcd_meta']+18,payload[:158]);m.callback=cb;m.run(f['lcd_write']);m.callback=None
 learned=[e[1] for e in cap_events if e[0]=='w' and e[2]==2]
 maximum=[e[1] for e in cap_events if e[0]=='w' and e[2]==4]
 r['learned']=unique(learned,'learned capacity RAM');r['coulomb_max']=unique(maximum,'coulomb maximum RAM')
 assert m.num(r['learned'],2)==m.num(r['words']+116,2)
 assert m.num(r['coulomb_max'],4)==m.num(r['learned'],2)*3600
 # Original UART1 receiver/dispatcher literal identifies state; real ASCII roundtrip identifies TX layout.
 dw=code.window(f['dispatch'],2);r['state']=dw[1].literal;r['rx']=r['state']+1
 assert 0x20000000<=r['state']<image.sp
 m.put(r['state'],b'\0');m.output.clear()
 req=ascii_frame(0,0x51)
 m.put(r['group0']-1,b'\0') # verified later against parser's address read
 rxtrace=[];m.trace=[];m.tracing=True;m.feed(req);m.tracing=False;rxtrace=m.trace[:]
 assert m.num(r['state'])==4,'OEM ASCII receive failed'
 # len excludes no bytes after final timeout: original counts differently before finalizing.
 r['rx_meta']=unique(list({e[1] for e in rxtrace if e[0]=='w' and e[2]==1 and e[3]==len(req) and e[1]>r['rx']+len(req)}),'RX length')
 assert any(e[:4]==('w',r['rx'],1,req[0]) for e in rxtrace),'RX base unproven'
 assert any(e[:4]==('w',r['rx_meta']+1,1,len(req)-1) for e in rxtrace),'RX counter ABI unproven'
 r['rx_limit']=min(230,r['rx_meta']-r['rx'])
 dtrace=m.capture(f['dispatch']);flash_reads=m.flash_reads[:];m.drain()
 response=bytes(m.output);assert response.startswith(b'~20') and response.endswith(b'\r'),'OEM UART1 ASCII 51 failed'
 # TX sender reads length then buffer bytes; use observed frame writes, not a layout shift.
 r['tx']=unique(list({e[1] for e in dtrace if e[0]=='w' and e[2]==1 and e[3]==0x7e}),'TX frame start')
 r['tx_length']=unique(list({e[1] for e in dtrace if e[0]=='r' and e[2]==2 and e[3]==len(response)}),'TX length')
 
 if r['tx_length']-r['tx']<175 or r['rx_meta']-r['rx']<165:raise ValueError(f'UART1 buffers too small for MAINT1.5: {r}')
 # The parser stores command and address; original 51 provides two version bytes.
 r['command']=unique(list({e[1] for e in dtrace if e[0]=='w' and e[2]==1 and e[3]==0x51 and r['rx_meta']<e[1]<r['tx']}),'decoded command')
 # Probe a slave address to disambiguate decoded/local ADR and identify parser address dependency.
 m.put(r['state'],b'\0');m.put(r['group0']-1,b'\x07');m.output.clear();m.feed(ascii_frame(7,0x51))
 slave_trace=m.capture(f['dispatch']);m.drain();assert m.output,'OEM slave ASCII51 failed'
 r['address']=unique(list({e[1] for e in slave_trace if e[0]=='r' and e[2]==1 and e[3]==7 and e[1]<r['group0']}),'local address')
 r['decoded_address']=unique(list({e[1] for e in slave_trace if e[0]=='w' and e[2]==1 and e[3]==7 and e[1]>r['tx_length']}),'decoded address')
 # INFO fields have stride 2. They are populated before the response gets hex-expanded.
 version=bytes.fromhex(response[13:-5].decode())[10:12]
 info_candidates=[e for e in dtrace if e[0]=='w' and e[2]==1 and e[3]==version[0] and r['tx']<=e[1]<r['tx_length']]
 r['info']=unique(list({e[1] for e in info_candidates if any(x[0]=='w' and x[1]==e[1]+2 and x[3]==version[1] for x in dtrace)}),'response version INFO')-20
 # Locate the flash reads producing precisely the OEM 51 version, from executable handler's literals.
 literals=[a for a,size,val,pc in flash_reads if size==1 and val==version[0] and any(b==a+1 and sz==1 and v==version[1] for b,sz,v,p in flash_reads)]
 facts['version_address']=unique(sorted(set(literals)),'OEM 51 version source')
 assert r['decoded_address']==r['tx_length']+10,'unsupported address/RTN structure'
 r['rtn']=r['tx_length']+6
 # Three 30-byte strings are read consecutively by the original identity serializer.
 identity=m.capture(f['identity_serializer'])
 r['string1']=run_start(identity,'r',1,90,1)
 r['string2']=r['string1']+30
 # Independent static consumer: serializer literals resolve the first string base.
 assert r['string1'] in {i.literal for i in code.body(f['identity_serializer'])}
 # Original DIP code independently proves address, effective slaves and Group7.
 m.put(r['group0']+7,bytes([m.num(r['group0']+7)&~0x20]))
 dip=m.capture(f['dip'])
 low_writes={e[1] for e in dip if e[0]=='w' and e[2]==1 and 0x20000000<=e[1]<0x20000090}
 assert r['address'] in low_writes,'DIP local address write missing'
 r['slaves']=unique(sorted(low_writes-{r['address']}),'effective slave count from DIP writes')
 assert any(e[0]=='r' and e[1]==r['group0']+7 for e in dip),'DIP auto-address switch read missing'
 m.put(r['group0']+7,bytes([m.num(r['group0']+7)|0x20]));m.put(r['address'],b'\x03');m.put(r['slaves'],b'\x11')
 m.run(f['dip']);assert m.num(r['address'])==3 and m.num(r['slaves'])==17,'DIP automatic mode preservation failed'
 assert r['slaves']==r['address']-1,'unsupported scheduler layout'
 assert r['group0']==r['address']+1,'unsupported switch/address relationship'
 # Independent Modbus gate address, followed by an original real UART1 transaction.
 window=code.window(f['modbus'],9)
 assert [i.op for i in window]==['push','ldr','ldrb','cmp','bne','ldr','ldrb','lsrs','beq'],'unknown Modbus gate layout'
 assert window[1].literal==r['state'] and window[7].args.endswith('#0x7'),'Modbus gate ABI mismatch'
 r['modbus_gate']=window[5].literal
 assert 0x20000000<=r['modbus_gate']<image.sp
 m.put(r['address'],b'\0');m.put(r['state'],b'\0');m.put(r['modbus_gate'],b'\x80')
 modbus=m.transact(modbus_frame(bytes.fromhex('01030000000C')))
 assert modbus and modbus[:2]==b'\x01\x03','OEM Modbus baseline failed'
 assert modbus_frame(modbus[:-2])==modbus,'OEM Modbus response CRC'
 # CRC independently checked against Python's XMODEM reference.
 m.put(r['rx'],b'123456789');m.uc.reg_write(UC_ARM_REG_R0,r['rx']);m.uc.reg_write(UC_ARM_REG_R1,9)
 crc=m.run(f['crc']);assert crc==binascii.crc_hqx(b'123456789',0)==0x31c3
 facts['oracle']={'modbus_response':modbus.hex(),'defaults_roundtrip':True,'lcd_payload_length':len(payload),'crc_123456789':crc,'original_51_response':response.hex(),'base_version':list(version),'iap_record_length':len(original)}
 facts['evidence'].append({'probe':'OEM execution traces','ram':r.copy(),'initial_sp':image.sp})
 from .power_rtc import prove_power_rtc
 prove_power_rtc(image,facts,Machine)
 return facts
