"""Configurable SP80 mask for1.6.3, preserving the original decision order.

Group0 &C0:00 explicit soft,40 explicit hard,80/C0 inherited image default.
No parameter migration, write command, event-byte mutation or RAM reservation.
Only1.6-compatible r3 charge-path ABI is admitted after Cutoff discovery.
"""
from pathlib import Path
import re
from .analysis import unique
from .thumb import Code
from .hardstop import locate


def discover_configurable(image,facts):
 c=Code(image.app);h=facts.get('hard_stop') or locate(image,facts)
 d=facts['cutoff'];site=h['offset'];w=c.window(site-2,5)
 if h['function']!=d['charge'] or len(w)!=5 or [i.token() for i in w]!=[
  ['ldr-pc','r3','ram'],['movs','r4, #0x'+format(h['old_mask'],'x')],
  ['ldrb','r3, [r3]'],['tst','r3, r4'],['bne']]:
  raise ValueError('unsupported configurable hard-stop r3 ABI')
 if w[0].literal!=h['event6'] or w[4].target!=h['branch_target']:
  raise ValueError('configurable hard-stop Event6/branch binding')
 prefix=c.window(h['function'],8)
 expected=[['push','{r4, r5, r6, r7, lr}'],['ldr-pc','r1','ram'],
  ['movs','r0, #0x8'],['ldrsh','r0, [r1, r0]'],['ldr-pc','r6','ram'],
  ['movs','r1, #0x7d'],['lsls','r1, r1, #0x3'],['subs','r6, #0x8']]
 if [i.token() for i in prefix]!=expected or prefix[1].literal!=d['measure']:
  raise ValueError('unsupported configurable hard-stop recovery ABI')
 # .11 uses r6+15hex, .12/.13 use r6+14hex. Derive the counter from the
 # native read/write relationship instead of assuming a shared RAM offset.
 early=c.window(h['function'],38)
 offsets=[int(match[1],0) for i in early if i.op=='ldrb' and (match:=re.fullmatch(r'r5, \[r6, #(0x[0-9a-f]+|[0-9]+)\]',i.args))]
 offset=unique(offsets,'hard-stop recovery counter offset')
 read=f'r0, [r6, #0x{offset:x}]'
 if not any(i.op=='ldrb' and i.args==read for i in early) or sum(i.op=='strb' and i.args==read for i in early)!=2:
  raise ValueError('unsupported hard-stop recovery counter read/write ABI')
 roles=dict(site=site,event6=h['event6'],function=h['function'],current=prefix[1].literal+8,
  recovery_counter=prefix[4].literal-8+offset,temperature_raw=prefix[4].literal+3,
  ovp_event=h['event6']-4,parameter_mask=0xc0,explicit_on=0x40,explicit_off=0)
 roles['hooks']={'hook_configurable_hard_stop':site}
 roles['evidence']=[dict(hook='hook_configurable_hard_stop',site=site,
  opcode=image.app[site:site+4].hex(),original_instructions=[i.token() for i in w[1:3]])]
 facts['configurable_hardstop']=roles
 return roles


def source_configurable(source):
 return source+'\n'+Path(__file__).with_name('configurable_hardstop.s').read_text()
