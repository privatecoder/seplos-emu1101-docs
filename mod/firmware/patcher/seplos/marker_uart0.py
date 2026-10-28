"""Discover the existing UART0 parser/response ABI for revision-one MAINT.

No second UART buffer: a wrapper handles only raw ASCII64 frames; all other
commands follow the frozen original/cutoff parser path. OEM full-code guards
run before this discovery in the publisher. Unknown dispatcher shapes fail.
"""
from pathlib import Path
from .analysis import unique
from .guards import collect
from .thumb import Code


def discover_marker_uart0(image,facts):
 c=Code(image.app);bodies=collect(c,facts);power=facts['power_rtc']['power_handler']
 dispatch=unique([a for a,body in bodies.items() if any(i.op=='bl' and i.target==power for i in body)],'UART0 power dispatcher owner')
 w=c.window(dispatch,12)
 if [i.op for i in w[:7]]!=['push','ldr','ldrb','cmp','bne','ldr','movs']:raise ValueError('unsupported UART0 marker dispatcher ABI')
 if [w[i].args for i in (2,3,6)]!=['r0, [r4]','r0, #0x4','r0, #0x12']:raise ValueError('unsupported UART0 marker response ABI')
 rx=facts['power_rtc']['uart0_rx'];state=w[1].literal;txbase=w[5].literal
 j=7
 if w[j].op=='subs' and w[j].args=='r5, #0x3c':txbase-=0x3c;j+=1
 if txbase+0x36!=rx-6 or [i.op for i in w[j:j+4]]!=['strh','bl','cmp','beq']:raise ValueError('unsupported UART0 marker length ABI')
 if w[j].args!='r0, [r5, #0x36]' or w[j+2].args!='r0, #0x0':raise ValueError('unsupported UART0 marker handled-return ABI')
 parser_call=w[j+1]
 if not 0x20000000<=state<rx<image.sp-0x200:raise ValueError('UART0 marker RAM relationship')
 body=bodies[dispatch];calls=[i for i in body if i.op=='bl']
 # .11/.12 place the common send tail before later command handlers; lexical
 # last-call ordering is not a role proof. Match the encoder's actual header.
 encoders=[]
 for call in calls:
  header=c.window(call.target,5)
  if [i.op for i in header]==['push','ldr','movs','mov','strb'] and header[1].literal==state and header[2].args=='r1, #0x7e' and header[3].args=='r4, r7' and header[4].args=='r1, [r7, #0x1]':encoders.append(call)
 encoder_call=unique(encoders,'UART0 ASCII response encoder')
 after=c.ins[encoder_call.at+4]
 for _ in range(3):
  if after.op!='b':break
  after=c.ins[after.target]
 if after.op!='bl':raise ValueError('UART0 encoder/send chain ABI')
 sender=after.target;encoder=encoder_call.target
 # Prove the command metadata load despite different compiler register choices.
 registers={};command=None
 for i in c.window(parser_call.at+8,8):
  reg=i.args.split(',')[0]
  if i.op=='ldr' and i.literal is not None:registers[reg]=i.literal
  elif i.op in ('adds','subs') and reg in registers and ', #' in i.args:
   amount=int(i.args.split('#')[1],0);registers[reg]+=amount if i.op=='adds' else -amount
  elif i.op=='ldrb':
   import re
   match=re.search(r'\[(r[0-7]), #(0x[0-9a-f]+|[0-9]+)\]',i.args)
   if match and match[1] in registers:command=registers[match[1]]+int(match[2],0);break
 if command!=rx+0x1f4:raise ValueError('UART0 command metadata ABI')
 d=dict(uart0_dispatch=dispatch,uart0_parser=parser_call.target,uart0_rx=rx,
        uart0_state=state,uart0_rtn=rx-7,uart0_tx_length=rx-6,
        uart0_rx_length=rx+0x1f6,uart0_command=rx+0x1f4,
        uart0_info=state+15,uart0_encoder=encoder,uart0_sender=sender)
 d['hooks']={'hook_uart0_marker_parser':parser_call.at}
 d['evidence']=[dict(hook='hook_uart0_marker_parser',site=parser_call.at,original_target=parser_call.target,opcode=image.app[parser_call.at:parser_call.at+4].hex())]
 facts['marker_uart0']=d
 return d


def source_revision(source,version):
 minor=int(version.split('.')[1])
 old=f'.byte 3, 0, 0, BASE_REVISION, 1, {minor}'
 patch=int(version.split('.')[2])
 for before,after in ((old,f'.byte 4, 0, 0, BASE_REVISION, 1, {minor}, {patch}'),
                      ('cmp r3, #18','cmp r3, #19'),('movs r0, #0x36','movs r0, #0x38')):
  if source.count(before)!=1:raise ValueError('unknown revision source contract: '+before)
  source=source.replace(before,after)
 if version.startswith('1.6.'):
  if source.count('hook_cut_uart0_parser:')!=1:raise ValueError('missing cutoff parser for UART0 marker chain')
  source=source.replace('hook_cut_uart0_parser:', 'hook_cut_uart0_parser:\n.Lmarker_cut_parser:')
 return source+'\n'+Path(__file__).with_name('marker_uart0.s').read_text()
