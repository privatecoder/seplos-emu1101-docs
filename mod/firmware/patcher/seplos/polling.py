"""Source-bound UART0 master poll roles; no firmware address/version table."""
from pathlib import Path
import json,struct
from .analysis import unique
from .thumb import Code
from .guards import collect,contracts,guard


def discover_polling(image,facts):
 if image.sha!=facts['original_app_sha256']:raise ValueError('polling analysis/input digest mismatch')
 # Recheck the entire reachable source graph: unreviewed IRQ writers cannot
 # inherit the buffer-ownership proof merely by retaining a polling prefix.
 guard(image,facts)
 c=Code(image.app);bodies=collect(c,facts);proof,_=contracts(c,facts)
 proofs={p['entry']:p for p in proof};d={}
 signatures=json.loads(Path(__file__).with_name('polling_signatures.json').read_text())
 for role,signature in signatures.items():
  at=unique([a for a in bodies if [i.token() for i in c.window(a,len(signature['prefix']))]==signature['prefix'] and proofs[a]['contract']==signature['contract']],'polling '+role+' role')
  if proofs[at]['contract']!=signature['contract']:raise ValueError('unsupported polling '+role+' complete contract')
  d[role]=at
 def literal(role,register,occurrence=0):
  values=[i.literal for i in bodies[d[role]] if i.op=='ldr' and i.args.startswith(register+', [pc,')]
  if len(values)<=occurrence:raise ValueError('polling literal role '+role+'/'+register)
  return values[occurrence]
 d['flags']=literal('start','r5');d['state']=literal('rx','r4')
 d['records']=literal('timer','r2');d['index']=d['records']-0x24
 d['counter']=d['index']+1;d['failures']=d['index']+2;d['online']=d['index']+24
 d['maximum']=literal('start','r6');d['rx_buffer']=literal('parser','r0')
 d['rx_length']=literal('parser','r6')+0x32;d['rx_count']=d['rx_length']+2
 d['system']=c.window(d['ccl'],3)[2].literal+24
 if literal('evaluate','r6')!=d['flags'] or literal('timer','r4')!=d['flags'] or literal('parser','r1')!=d['state']:
  raise ValueError('polling shared native roles disagree')
 if d['rx_length']!=d['rx_buffer']+0x1f6 or not 0x20000000<=d['rx_buffer']<d['rx_buffer']+82<=d['rx_length']<image.sp:
  raise ValueError('polling RX buffer/metadata bounds')
 def calls(role):return [i.target for i in bodies[d[role]] if i.op=='bl']
 if calls('evaluate')!=[d['parser'],d['decode']] or calls('start')[-1]!=d['tx_start']:
  raise ValueError('polling native evaluator/sender call binding')
 main=bodies[facts['functions']['main']];sites={i.at for i in main}
 for role in ('start','evaluate'):
  d[role+'_site']=unique([at for at in c.callers(d[role]) if at in sites],'polling main '+role+' call')
 if d['evaluate_site']!=d['start_site']+4:raise ValueError('polling main call ordering')
 # Bind the native address/count/round dispatch region, not arbitrary callers.
 s=d['start_site'];w=c.window(s-24,17)
 if [i.op for i in w]!=['ldr','ldrb','cmp','bne','ldr','ldrb','cmp','beq','ldr','ldrb','lsls','bmi','bl','bl','b','bl','bl']:
  raise ValueError('polling main role/round gate shape')
 if w[4].literal!=d['maximum'] or w[8].literal!=d['flags'] or w[10].args!='r0, r0, #0x1d' or w[3].target!=w[15].at or w[7].target!=w[15].at or w[11].target!=s+18 or w[14].target!=s+18:
  raise ValueError('polling main role/round gate binding')
 d['main_dispatch']=s-24;d['main_dispatch_end']=s+18;d['address']=w[0].literal
 # The actual UART0 vector establishes the mask, rather than a guessed IRQ.
 irq=unique([n for n in range(32) if 0x40+4*n+4<=0xc0 and any(i.op=='bl' and i.target==d['rx'] for i in bodies.get(struct.unpack_from('<I',image.app,0x40+4*n)[0]&~1,[]))],'UART0 IRQ role')
 wrapper=c.body(struct.unpack_from('<I',image.app,0x40+4*irq)[0]&~1)
 if [i.target for i in wrapper if i.op=='bl']!=[d['tx_irq'],d['rx']]:raise ValueError('polling UART0 vector ownership')
 d['irq_mask']=1<<irq
 timer_entry=struct.unpack_from('<I',image.app,0x44)[0]&~1
 if not any(i.op=='bl' and i.target==d['timer'] for i in bodies[timer_entry]) or not any(i.op=='bl' and i.target==d['tx_watchdog'] for i in bodies[timer_entry]):
  raise ValueError('polling timer IRQ call binding')
 d['timer_irq']=timer_entry
 d['hooks']={'hook_poll_start':d['start_site'],'hook_poll_evaluate':d['evaluate_site']}
 d['evidence']=[dict(hook=name,site=site,opcode=image.app[site:site+4].hex(),original_target=c.ins[site].target) for name,site in d['hooks'].items()]
 d['native_contracts']={role:proofs[d[role]]['contract'] for role in signatures}
 d['ram_bytes']=0;d['wrapper_stack_bytes']=16;d['validator_stack_bytes']=24;d['extra_native_stack_bytes']=16
 facts['polling']=d
 return d


def source_polling(source):
 if 'hook_poll_start:' in source:raise ValueError('polling source already appended')
 return source+'\n'+Path(__file__).with_name('polling.s').read_text()


def verify_polling_payload(original,candidate,reported_entries):
 """Independently bind the emitted polling implementation without parent JIT.

 This checks the exact final polling appendix and its native call veneers.
 Other appendix features retain their existing publication checks. No worker
 role, RAM address, payload offset or entry address supplies this expectation.
 """
 import hashlib,re,tempfile
 from .analysis import discover
 from .thumb import llvm,command,encode_bl
 d=discover_polling(original,discover(original))
 constants='\n'.join(f'.equ POLL_{k.upper()}, 0x{v:x}' for k,v in sorted(d.items()) if type(v) is int)
 header='.syntax unified\n.cpu cortex-m0\n.thumb\n.section .text,"ax",%progbits\n'
 payload=Path(__file__).with_name('polling.s').read_text();matches=[]
 with tempfile.TemporaryDirectory(prefix='seplos-poll-proof-') as temp:
  temp=Path(temp);asm=temp/'poll.s';obj=temp/'poll.o';raw=temp/'poll.bin'
  # Thumb code is halfword-aligned; literal placement additionally depends on
  # the independently checked suffix address modulo four.
  for pad in (0,2):
   asm.write_text(header+constants+f'\n.space {pad}\n'+payload)
   command([llvm('llvm-mc'),'-triple=thumbv6m-none-eabi','-filetype=obj','-o',str(obj),str(asm)])
   if 'R_ARM_' in command([llvm('llvm-objdump'),'-r',str(obj)]):raise ValueError('independent UART0 polling unresolved relocation')
   command([llvm('llvm-objcopy'),'-O','binary','--only-section=.text',str(obj),str(raw)])
   expected=raw.read_bytes()[pad:];start=len(candidate.app)-len(expected)
   if start<len(original.app) or start%4!=pad or candidate.app[start:]!=expected:continue
   symbols={m[2]:int(m[1],16)-pad for line in command([llvm('llvm-nm'),'--defined-only',str(obj)]).splitlines() if (m:=re.match(r'([0-9a-fA-F]+)\s+[A-Za-z]\s+(hook_poll_\w+)$',line))}
   if set(symbols)!=set(d['hooks']):raise ValueError('independent UART0 polling symbol contract')
   entries={name:start+offset for name,offset in symbols.items()}
   matches.append(dict(append_at=start,bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),entries=entries))
 if len(matches)!=1:raise ValueError('independent UART0 polling payload mismatch')
 match=matches[0]
 for name,site in d['hooks'].items():
  entry=match['entries'][name]
  if reported_entries.get(name)!=entry or candidate.app[site:site+4]!=encode_bl(site,entry):
   raise ValueError('independent UART0 polling entry/veneer mismatch')
 return dict(verified=True,**match)
