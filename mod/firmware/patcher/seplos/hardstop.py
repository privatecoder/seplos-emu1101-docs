"""Discover the SP80 Event6 mask; no user-supplied firmware offsets required."""
from .analysis import unique
from .thumb import Code
from .guards import collect
from .image import record


def locate(image,facts):
 code=Code(image.app);bodies=collect(code,facts);executable={i.at for body in bodies.values() for i in body}
 hits=[]
 for a in sorted(executable):
  w=code.window(a,5)
  if len(w)!=5 or [i.op for i in w]!=['ldr','movs','ldrb','tst','bne']:continue
  reg=w[0].args.split(',')[0]
  if w[0].literal!=0x20000035 or w[1].args not in ('r4, #0x71','r4, #0x73'):continue
  if w[2].args!=f'{reg}, [{reg}]' or w[3].args!=f'{reg}, r4':continue
  owner=unique([at for at,body in bodies.items() if a in {i.at for i in body}],'charge-inhibit function owner')
  flags=[]
  for ins in bodies[owner]:
   q=code.window(ins.at,8)
   if len(q)==8 and q[0].op=='ldr' and q[0].args.startswith('r0, [pc,') and ('ldrb','r1, [r0]') in [(x.op,x.args) for x in q] and all(any(x.op=='movs' and x.args.endswith(suffix) for x in q) for suffix in ('#0xbf','#0x40')):flags.append(q[0].literal)
  forbidden_flags=unique(flags,'charge-inhibit output flags')
  hits.append({'forbidden_flags':forbidden_flags,'offset':a+2,'entry':a,'branch_target':w[4].target,'fallthrough':w[4].at+w[4].size,'function':owner,'event6':w[0].literal,'enabled':image.app[a+2]==0x73,'old_mask':image.app[a+2]})
 return unique(hits,'reachable SP80 charge-inhibit mask')


def apply(image,facts,found=None):
 detail=found or locate(image,facts);app=bytearray(image.app)
 detail={**detail,'requested':'enable','changed':not detail['enabled'],'new_mask':0x73,'enabled_before':detail['enabled'],'enabled':True}
 app[detail['offset']]=0x73
 return image.with_app(app),detail




def validate_hardstop(original,patched,facts,detail):
 from unicorn.arm_const import UC_ARM_REG_PC
 from .machine import Machine
 if not __debug__:raise RuntimeError('assertions required')
 out=[];m=Machine(patched,facts);mask=patched.app[detail['offset']]
 assert mask==0x73,'hard-stop mask not enabled'
 changed={a for a,(x,y) in enumerate(zip(original.app,patched.app)) if x!=y}
 assert changed<={detail['offset']} and len(original.app)==len(patched.app),'hard-stop-only diff exceeded'
 for event in range(256):
  m.put(detail['event6'],bytes([event]));expected=detail['branch_target'] if event&0x73 else detail['fallthrough']
  m.uc.emu_start(detail['entry']|1,expected,count=10)
  assert m.uc.reg_read(UC_ARM_REG_PC)==expected,f'Event6 {event:02x} branch mismatch'
  out.append({'name':f'hard-stop-real-Event6-mask-{event:02x}','passed':True})
 # Execute the complete original charge-inhibit function with synthetic defaults.
 for event in (0,1,2,0x10,0x20,0x40,0x80):
  board=Machine(patched,facts);board.run(facts['functions']['loader']);board.put(0x20000030,bytes(8));board.put(detail['event6'],bytes([event]));board.run(detail['function'])
  assert bool(board.num(detail['forbidden_flags'])&0x40)==bool(event&0x73),f'charge-inhibit Event8 output {event:02x}'
  assert bool(board.num(0x50002000,4)&(1<<12))==(not bool(event&0x73)),'charge MOSFET GPIO mismatch'
  out.append({'name':f'hard-stop-complete-charge-inhibit-{event:02x}','passed':True})
 return out
