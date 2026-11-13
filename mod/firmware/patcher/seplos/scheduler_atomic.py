"""Source-derived atomic scheduler cleanup; no firmware address/version table."""
from pathlib import Path
import struct
from .thumb import Code
from .guards import collect,pointer_edges


def _registers_at(code,body,entry,site):
 """Conservative forward constants for the two callee-preserved cleanup bases."""
 instructions={i.at:i for i in body};states={entry:(None,None)};todo=[entry]
 while todo:
  at=todo.pop();i=instructions[at];state=list(states[at]);dst=i.args.split(',')[0].rstrip('!')
  writes=set()
  if i.op in ('pop','ldm'):
   registers=i.args[i.args.index('{')+1:i.args.index('}')].split(', ')
   writes.update(registers)
  if i.op in ('ldm','stm') and '!' in i.args.split(',')[0]:writes.add(dst)
  readonly=i.op in ('cmp','cmn','tst','push','str','strb','strh','stm','bx','blx') or i.target is not None
  if not readonly and i.op not in ('pop','ldm'):writes.add(dst)
  for reg in writes&{'r5','r6'}:
   slot=('r5','r6').index(reg);value=None
   if reg==dst:
    if i.op=='ldr' and '[pc,' in i.args:value=i.literal
    elif i.op=='movs' and ', #' in i.args:value=int(i.args.split('#')[1],0)
    elif i.op=='mov' and i.args.split(', ')[-1] in ('r5','r6'):value=state[('r5','r6').index(i.args.split(', ')[-1])]
   state[slot]=value
  successors=[]
  if i.op=='bl' and i.target in code.switches:successors=code.switch_targets(i)
  elif i.op=='b':successors=[i.target]
  elif i.op=='bx' or i.op=='pop' and 'pc' in i.args:pass
  else:
   successors=[at+i.size]
   if i.target is not None and i.op!='bl':successors.append(i.target)
  for target in successors:
   if target not in instructions:raise ValueError('scheduler main CFG leaves validated body')
   incoming=tuple(state)
   if target in states:incoming=tuple(a if a==b else None for a,b in zip(states[target],incoming))
   if target not in states or incoming!=states[target]:states[target]=incoming;todo.append(target)
 return states.get(site)


def discover_scheduler_atomic(image,facts):
 if image.sha!=facts['original_app_sha256']:raise ValueError('scheduler analysis/input digest mismatch')
 code=Code(image.app);bodies=collect(code,facts);main=facts['functions']['main'];body=bodies[main]
 candidates=[]
 for i in body:
  at=i.at;w=code.window(at,7)
  expected=[('ldrb','r0, [r5]'),('orrs','r0, r6'),('b',hex(at+8)),('b',hex(at+14)),('movs','r1, #0xfb'),('ands','r0, r1'),('strb','r0, [r5]')]
  if len(w)==7 and [(j.op,j.args) for j in w]==expected and all(j.at in {k.at for k in body} for j in w):candidates.append(at)
 if len(candidates)!=1:raise ValueError('unsupported scheduler main cleanup role')
 site=candidates[0]
 timer=struct.unpack_from('<I',image.app,0x44)[0]&~1;timer_body=bodies[timer]
 literals=[i.literal for i in timer_body if i.literal is not None]
 flags=[a for a in set(literals) if 0x20000000<=a<0x20000100 and literals.count(a)>=2]
 if len(flags)!=1:raise ValueError('unsupported scheduler timer flag role')
 flags=flags[0]
 # Bind the shared byte to a timer callee's native wake-enable RMW.
 wakes=[]
 for call in timer_body:
  if call.op!='bl':continue
  b=bodies[call.target]
  if any(i.literal==flags for i in b) and any(i.op=='cmp' and i.args=='r0, #0xc8' for i in b) and any([(j.op,j.args) for j in code.window(i.at,3)]==[('ldrb','r1, [r0]'),('orrs','r1, r6'),('strb','r1, [r0]')] for i in b):wakes.append(call.target)
 if len(wakes)!=1:raise ValueError('unsupported scheduler native wake flag binding')
 if _registers_at(code,body,main,site)!=(flags,8):raise ValueError('scheduler R5/R6 cleanup inputs unproven')
 incoming=[]
 for entry,b in bodies.items():
  targets=[(i.at,i.target) for i in b if i.target is not None]
  targets.extend(pointer_edges(code,b).items())
  targets.extend((i.at,t) for i in b if i.op=='bl' and i.target in code.switches for t in code.switch_targets(i))
  targets.append((None,entry))
  for source,target in targets:
   if target in (site+2,site+4):raise ValueError('scheduler branch enters overwritten cleanup')
   if target in (site+8,site+10,site+12) and (source,target)!=(site+4,site+8):raise ValueError('scheduler branch bypasses atomic cleanup')
   if site<=target<=site+14:incoming.append(dict(source=source,target=target))
 d=dict(site=site,branch_site=site+4,continuation=site+14,flags=flags,
  opcode=image.app[site:site+4].hex(),branch_opcode=image.app[site+4:site+6].hex(),
  branch_replacement=struct.pack('<H',0xe000|((site+14-(site+4)-4)//2)).hex(),
  hooks={'hook_scheduler_atomic':site},main=main,native_wake=wakes[0],incoming=incoming,
  appendix_instructions=10,masked_instructions=6,ram_bytes=0)
 d['evidence']=[dict(hook='hook_scheduler_atomic',site=site,opcode=d['opcode'])]
 facts['scheduler_atomic']=d
 return d


def source_atomic(source):
 if 'hook_scheduler_atomic:' in source:raise ValueError('scheduler atomic source already appended')
 return source+'\n'+Path(__file__).with_name('scheduler_atomic.s').read_text()
