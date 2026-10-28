"""Prove OEM power/RTC entry points without a firmware-version address table."""
from pathlib import Path
import json
from .analysis import unique
from .thumb import Code


def discover_power_rtc(image):
 c=Code(image.app);roles={}
 for name,signature in json.loads(Path(__file__).with_name('power_rtc_signatures.json').read_text()).items():
  roles[name]=unique([a for a in c.ins if [i.token() for i in c.window(a,len(signature))]==signature],name)
  if not c.callers(roles[name]):raise ValueError(name+': missing original caller')
 def call(at):
  i=c.ins[at]
  if i.op!='bl':raise ValueError('expected OEM call')
  return i.target
 p=roles['power_handler'];body=c.body(p)
 def branch_after(args):
  at=unique([i.at for i in body if i.op=='cmp' and i.args==args],args)
  i=c.ins[at+2]
  if i.op!='beq':raise ValueError('unknown OEM power selection')
  return i.target
 action=branch_after('r4, #0x4');reset=call(branch_after('r4, #0x6'))
 w=c.window(action,4)
 if [i.token() for i in w]!=[['ldr-pc','r6','ram'],['ldr-pc','r2','ram'],['movs','r4, #0x20'],['cmp','r1, #0x10']]:raise ValueError('unknown power action ABI')
 # This fragment returns through the handler's original six-word pop frame.
 fragment=c.body(action)
 if any(i.op=='bl' for i in fragment) or any(i.args!='{r3, r4, r5, r6, r7, pc}' for i in fragment if i.op=='pop'):raise ValueError('unknown power action return ABI')
 if not any(i.op=='ldrb' and i.args=='r0, [r0, #0x1f]' for i in fragment):raise ValueError('unproven FF detection ABI')
 if c.ins[reset].token()!=['cpsid','i']:raise ValueError('unknown reset ABI')
 get=roles['rtc_get_handler'];set_=roles['rtc_set_handler']
 read=call(get+2)
 write=[i.target for i in c.body(set_) if i.op=='bl'][-1]
 rb=c.window(read,2);wb=c.window(write,2)
 if rb[0].args!='{r4, lr}' or wb[0].args!='{r4, r5, r6, lr}' or rb[1].literal!=wb[1].literal:raise ValueError('unknown RTC driver ABI')
 rtc=rb[1].literal
 read_calls=[i.target for i in c.body(read) if i.op=='bl']
 write_calls=[i.target for i in c.body(write) if i.op=='bl']
 transfer=read_calls[0]
 if transfer!=write_calls[-1]:raise ValueError('RTC transfer relationship missing')
 if not 0x20000000<=rtc<image.sp-0x90:raise ValueError('RTC buffer out of RAM')
 roles.update(power_action=action,reset=reset,rtc_read=read,rtc_write=write,rtc_transfer=transfer,rtc=rtc,
              system_status=w[0].literal,control_flags=w[1].literal,uart0_rx=c.ins[p+2].literal)
 return roles


def prove_power_rtc(image,facts,machine):
 from .machine import ascii_frame
 from unicorn.arm_const import UC_ARM_REG_R0
 d=discover_power_rtc(image);facts['power_rtc']=d
 # Trace the real UART0 handler, independently from the new transport wrapper.
 for value in (0x10,0x1f):
  m=machine(image,facts);m.defaults(1)
  m.put(d['system_status'],b'\x02');m.put(d['control_flags'],b'\x00')
  m.put(d['uart0_rx'],ascii_frame(1,0x45,bytes([0,4,value])))
  m.run(d['power_handler'])
  assert bool(m.num(d['system_status'])&0x20)==(value==0x1f)
  assert m.num(d['control_flags'])==(0x20 if value==0x10 else 0x10)
 # Execute original BCD conversion and RTC drivers; model only their I2C transfer.
 m=machine(image,facts);m.defaults(1)
 m.put(d['rtc']+4,bytes([0,2,29,23,58,59]))
 assert m.run(d['rtc_write'])==1
 assert m.rtc_transfers[-1]['data'][2:9]==[0x59,0x58,0x23,0x29,0,2,0]
 m.put(d['rtc']+4,bytes(6));assert m.run(d['rtc_read'])==1
 assert m.read(d['rtc']+4,6)==bytes([0,2,29,23,58,59])
 m.rtc_fail=True;assert m.run(d['rtc_read'])==0
 facts['evidence'].append({'probe':'OEM power action and actual RTC drivers',**d,'rtc_hardware_model':'I2C transfer boundary, PCF8563 register bytes'})
 return d
