"""Conservative compatibility contracts for the understood SWM181 code family.

All reachable functions, exact RAM/MMIO values, local branches, call edges and
referenced ROM regions are checked. Unknown forms never enroll themselves.
"""
from pathlib import Path
import hashlib,json,re,struct
from .thumb import Code


def digest(value):return hashlib.sha256(json.dumps(value,separators=(',',':'),sort_keys=True).encode()).hexdigest()


def pointer_edges(code,body):
 result={}
 for i in body:
  if i.op!='bx' or i.args=='lr':continue
  before=code.ins.get(i.at-2)
  if before and before.op=='ldr' and before.args.startswith(i.args+', [pc,') and before.literal is not None and before.literal&1 and 0xc0<=(before.literal&~1)<len(code.app):
   result[before.at]=before.literal&~1
 return result


def collect(code,facts):
 roots={facts['functions']['main'],0xc0}
 roots.update(v&~1 for (v,) in struct.iter_unpack('<I',code.app[4:0xc0]) if v&1 and 0xc0<=(v&~1)<len(code.app))
 # Reviewed Keil two-region copy/zero startup descriptor. Sources are data;
 # descriptor function pointers become explicit graph roots and contract edges.
 init=code.ins[0xc4].target;window=code.window(init,4)
 if [i.op for i in window]!=['ldr','movs','ldr','b'] or window[0].args.split(',')[0]!='r4' or window[2].args.split(',')[0]!='r6':raise ValueError('unknown Keil initializer')
 table,end=window[0].literal,window[2].literal
 if table is None or end is None or not 0xc0<=table<end<=len(code.app) or (end-table)%16 or end-table>128:raise ValueError('unknown startup region table')
 regions=[]
 for at in range(table,end,16):
  src,dst,size,fn=struct.unpack_from('<IIII',code.app,at)
  if not 0x20000000<=dst<=dst+size<=facts['sp'] or fn&1 or not 0xc0<=fn<len(code.app):raise ValueError('unsupported startup region ABI')
  roots.add(fn);regions.append((src,dst,size,fn))
 todo=list(roots);bodies={}
 while todo:
  at=todo.pop()
  if at in bodies:continue
  body=code.body(at,16384)  # Every error propagates: no skipped opaque functions.
  bodies[at]=body
  todo.extend(i.target for i in body if i.op=='bl' and i.target is not None)
  todo.extend(pointer_edges(code,body).values())
 for name,at in facts['functions'].items():
  if at not in bodies:raise ValueError(f'unreachable role: {name} at {at:x}')
 executable={i.at for b in bodies.values() for i in b}
 if not set(facts['hooks'].values())<=executable:raise ValueError('unreachable hook')
 code.rom_table=(table,end,regions)
 bounds={len(code.app),table,end}
 bounds.update(bodies)
 # Split ROM objects at literal pools, referenced object starts and init bounds.
 for a in executable:
  i=code.ins[a]
  if i.op=='ldr' and '[pc,' in i.args:
   pool=((a+4)&~3)+(int.from_bytes(i.raw,'little')&255)*4
   bounds.add(pool)
   if i.literal is not None and 0xc0<=i.literal<len(code.app):bounds.add(i.literal&~1)
 for src,dst,size,fn in regions:
  # Copy helper starts with a branch and performs LDM/STM; zero helper MOVS r0,0.
  body=bodies[fn]
  copy=any(i.op=='ldm' for i in body)
  if copy:
   if not 0xc0<=src<=src+size<=len(code.app):raise ValueError('invalid startup copy source')
   bounds.update((src,src+size))
 code.rom_bounds=sorted(bounds)
 return bodies


def shape(code,body):
 positions={i.at:j for j,i in enumerate(body)};pointer=pointer_edges(code,body)
 # Track direct literal bases through aliases; this classifies ROM pointers,
 # while scalar constants and ALL RAM/MMIO literal values remain exact.
 regs={};dereferenced=set()
 for i in body:
  dst=i.args.split(',')[0]
  if i.op=='ldr' and '[pc,' in i.args:regs[dst]=i.literal;continue
  m=re.fullmatch(r'(r\d+), (r\d+)',i.args)
  if i.op=='mov' and m:
   if m[2] in regs:regs[m[1]]=regs[m[2]]
   else:regs.pop(m[1],None)
   continue
  m=re.search(r'\[(r\d+)',i.args)
  if i.op.startswith(('ldr','str')) and m and m[1] in regs:dereferenced.add(regs[m[1]])
  if i.op not in ('cmp','tst','str','strb','strh','b') and not i.op.startswith('b'):regs.pop(dst,None)
  if i.op=='bl':
   for reg in ('r0','r1','r2','r3'):regs.pop(reg,None)
 out=[]
 for i in body:
  if i.op=='ldr' and '[pc,' in i.args:
   v=i.literal
   if i.at in pointer:v='code-pointer-bound-by-edge'
   elif v is not None and v in dereferenced and 0xc0<=v<len(code.app):
    table,end,regions=code.rom_table
    if v in (table,end):v=['startup-region-bound',v-table]
    else:
     stop=min((x for x in code.rom_bounds if x>v),default=len(code.app))
     v=['ROM-data',stop-v,hashlib.sha256(code.app[v:stop]).hexdigest()]
   out.append(['ldr-pc',i.args.split(',')[0],v])
  elif i.op=='bl' and i.target in code.switches:
   out.append(['switch8',[positions[t] for t in code.switch_targets(i)]])
  elif i.target is not None:
   if i.op!='bl' and i.target not in positions:raise ValueError('unbound branch target')
   out.append([i.op,positions[i.target] if i.op!='bl' else 'bound-callee'])
  else:out.append(i.token())
 return digest(out)


def contracts(code,facts):
 bodies=collect(code,facts)
 shapes={at:shape(code,body) for at,body in bodies.items()}
 result=[]
 for at,body in bodies.items():
  edges=[]
  for j,i in enumerate(body):
   if i.op=='bl':edges.append([j,'bl',shapes[i.target]])
  for site,target in pointer_edges(code,body).items():edges.append([next(j for j,i in enumerate(body) if i.at==site),'code-pointer',shapes[target]])
  result.append({'entry':at,'shape':shapes[at],'contract':digest([shapes[at],edges]),'instructions':len(body),'edges':len(edges),'indirect':sum(i.op=='blx' or i.op=='bx' and i.args!='lr' for i in body)})
 table,end,regions=code.rom_table
 initialization=[]
 for src,dst,size,fn in regions:
  copy=any(i.op=='ldm' for i in bodies[fn]);data=hashlib.sha256(code.app[src:src+size]).hexdigest() if copy else None
  initialization.append([dst,size,shapes[fn],data])
 return result,digest(initialization)


def guard(image,facts):
 code=Code(image.app);variants=json.loads(Path(__file__).with_name('shapes.json').read_text())
 proof,initialization=contracts(code,facts)
 allowed=set(variants['function_contracts'])
 for item in proof:
  if item['contract'] not in allowed:raise ValueError(f"unknown complete code/ROM/call contract at {item['entry']:x}")
 if initialization not in variants['initialization']:raise ValueError('unknown startup data/region contract')
 if any(i.literal is not None and 0x23000<=i.literal<0x24000 for i in code.ins.values()):raise ValueError('OEM references maintenance sector 23000')
 facts['guard_evidence']=proof
 facts['guard_summary']={'reachable_functions':len(proof),'fully_checked_functions':len(proof),'unknown_contexts':0,'reviewed_indirect_contexts':sum(x['indirect'] for x in proof),'startup_contract':initialization,'RAM_literals':'exact','ROM_data':'content-bound','calls':'callee-shape-bound'}
 return facts
