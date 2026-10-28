"""Conservative MAINT1.6 role discovery and version-specific source composition."""
from pathlib import Path
import json,struct
from .analysis import unique
from .thumb import Code
from .guards import collect


def discover_cutoff(image,facts):
 c=Code(image.app);bodies=collect(c,facts);f=facts['functions'];r=facts['ram'];d={}
 for name,signature in json.loads(Path(__file__).with_name('cutoff_signatures.json').read_text()).items():
  hits=[a for a in bodies if [i.token() for i in c.window(a,len(signature))]==signature]
  if len(hits)!=1:raise ValueError('unsupported MAINT1.6 gate ABI: '+name)
  d[name]=hits[0]
 def calls(at):return [i for i in bodies[at] if i.op=='bl']
 def owner_calls(target):return unique([a for a,body in bodies.items() if any(i.op=='bl' and i.target==target for i in body)],'owner '+hex(target))
 d['uart0_a1']=unique([a for a in bodies if a!=f['lcd_write'] and {f['validator'],f['serializer']}<={i.target for i in calls(a)}],'UART0 A1')
 d['uart0_dispatch']=owner_calls(facts['power_rtc']['power_handler'])
 w=c.window(d['uart0_dispatch'],12)
 if [i.op for i in w]!=['push','ldr','ldrb','cmp','bne','ldr','movs','subs','strh','bl','cmp','beq']:raise ValueError('UART0 dispatcher ABI')
 d['uart0_state']=w[1].literal;d['uart0_parser']=w[9].target
 d['uart0_rx']=facts['power_rtc']['uart0_rx'];d['uart0_rtn']=d['uart0_rx']-7
 d['uart0_meta']=d['uart0_rx']+0x200-4
 d['onoff']=unique([i.literal-3 for i in c.window(d['discharge'],5) if i.literal is not None],'OnOff ABI')
 if d['onoff']!=0x200000b5:raise ValueError('unknown OnOff RAM')
 d['event8']=facts['hard_stop']['forbidden_flags'] if 'hard_stop' in facts else 0x20000005
 cb=bodies[d['charge']];db=bodies[d['discharge']];sb=bodies[d['power_state']];hb=bodies[d['heater']]
 d['charge_tail']=unique([i.at for i in cb if [x.token() for x in c.window(i.at,3)]==[['ldrb','r0, [r0]'],['movs','r2, #0xfd'],['lsls','r3, r0, #0x19']]],'charge output tail')
 d['discharge_tail']=unique([i.at for i in db if [x.op for x in c.window(i.at,4)]==['ldrb','ldr','ldr','ldr'] and c.ins[i.at].args=='r1, [r0]' and c.ins[i.at+2].literal==0x50002000],'discharge output tail')
 d['heater_tail']=unique([i.at for i in hb if i.token()==['ldrb','r0, [r0]'] and c.ins.get(i.at+2) and c.ins[i.at+2].literal==0x800],'heater output tail')
 d['state_on_tail']=unique([i.at for i in sb if [x.token() for x in c.window(i.at,5)]==[['ldr-pc','r1',0x50004000],['ldr','r0, [r1]'],['movs','r2, #0x8'],['orrs','r0, r2'],['str','r0, [r1]']]],'state power hold tail')
 for role,mask in (('charge','{r4, r5, r6, r7, lr}'),('discharge','{r4, r5, r6, r7, lr}'),('power_state','{r3, r4, r5, r6, r7, lr}'),('heater','{r4, r5, r6, lr}')):
  if c.ins[d[role]].args!=mask:raise ValueError('unknown output frame '+role)
 d['state_control']=c.window(d['power_state'],3)[2].literal
 d['state_shadow']=d['state_control']-1
 if not any(i.literal==d['state_shadow'] for i in sb):raise ValueError('state shadow ABI')
 d['state_timer']=unique(list({i.literal for i in sb if i.op=='ldr' and i.args.startswith('r5, [pc,') and i.literal is not None and r['words']+512<i.literal<image.sp}),'state timer')
 d['aggregate']=c.window(d['ccl'],3)[2].literal+24
 d['divide']=calls(d['ccl'])[0].target
 # The role signatures plus the complete OEM guards bind the aggregation ABI;
 # independently verify the actual record stride and gate constants here.
 aggregate_owner=owner_calls(d['ccl']);aggregate_calls=calls(aggregate_owner)
 ccl_site=unique([i.at for i in aggregate_calls if i.target==d['ccl']],'aggregation CCL call')
 d['count']=unique([i.target for i in aggregate_calls if i.at+4==ccl_site],'preceding capability count')
 count_body=bodies[d['count']]
 poll=unique([i.literal for i in count_body if i.op=='ldr' and i.args.startswith('r0, [pc,') and c.ins.get(i.at+2) and c.ins[i.at+2].token()==['ldr','r3, [r0, #0x18]']],'poll mask base')
 d['poll_mask']=poll+24;d['pack_table']=poll+36
 if not any(i.literal==d['pack_table'] for i in count_body) or not any(i.op=='movs' and i.args.endswith('#0x1e') for i in count_body):raise ValueError('unknown pack table ABI')
 crc=unique([i.target for i in calls(f['iap_write']) if i.target not in (f['iap_erase'],f['iap_program'])],'parameter CRC')
 d['nv_crc']=crc;d['flash_read']=calls(f['iap_read'])[0].target
 d['nv_primary']=0x25000;d['nv_backup']=0x26000;d['nv_group_offset']=163
 if r['iap_buffer']+256>image.sp:raise ValueError('IAP buffer bounds')
 d['nv_scratch']=r['iap_buffer']+256
 table,end,regions=c.rom_table
 if len(regions)!=2 or regions[-1][1]+regions[-1][2]!=image.sp:raise ValueError('startup zero/stack extent')
 if not c.ins[regions[-1][3]].token()==['movs','r0, #0x0']:raise ValueError('startup zero helper ABI')
 d['measure']=c.window(d['charge'],2)[1].literal
 if image.sp+4>0x20002000:raise ValueError('insufficient reviewed 8KiB SRAM')
 if any(i.literal is not None and image.sp<=i.literal<0x20004000 and not (i.at==0xc0 and i.literal==image.sp) for body in bodies.values() for i in body):raise ValueError('OEM RAM reference above original SP')
 d['ram']=image.sp;d['zero_size_offset']=end-8;d['zero_size_old']=regions[-1][2];d['zero_helper']=regions[-1][3]
 hooks={}
 def bind(name,sites):
  for j,site in enumerate(sites):
   key=name if len(sites)==1 else name+'_'+str(j)
   hooks[key]=site
 def main_call(role):
  return [i.at for i in calls(f['main']) if i.target==d[role]]
 for role in ('charge','discharge','power_state','heater'):
  bind('hook_cut_'+role,[unique(main_call(role),role+' main call')])
 bind('hook_cut_ccl',[unique(c.callers(d['ccl']),'CCL call')])
 bind('hook_cut_loader',[unique(c.callers(f['loader']),'loader call')])
 bind('hook_cut_record',[unique([i.at for i in calls(f['loader']) if i.target==f['iap_read']],'loader record read')])
 bind('hook_cut_nv_write',[unique([i.at for i in calls(f['serializer']) if i.target==f['iap_write']],'parameter record write')])
 bind('hook_cut_serializer',sorted(c.callers(f['serializer'])))
 bind('hook_cut_uart0_a1',[unique(c.callers(d['uart0_a1']),'UART0 A1 call')])
 bind('hook_cut_lcd_a1',[unique(c.callers(f['lcd_write']),'LCD A1 call')])
 bind('hook_cut_uart0_power',[unique(c.callers(facts['power_rtc']['power_handler']),'UART0 power call')])
 bind('hook_cut_uart0_parser',[w[9].at])
 if not hooks['hook_cut_loader']<hooks['hook_cut_charge']:raise ValueError('gates before parameter loader')
 d['hooks']=hooks
 d['evidence']=[{'hook':name,'site':site,'original_target':c.ins[site].target,'opcode':image.app[site:site+4].hex()} for name,site in hooks.items()]
 facts['cutoff']=d
 return d


def source16(source):
 replacements={
  '.byte 3, 0, 0, BASE_REVISION, 1, 5':'.byte 3, 0, 0, BASE_REVISION, 1, 6',
  'movs r2, #12':'movs r2, #44',
  '    ldr r3, =SERIALIZER+1\n    blx r3':'    bl hook_cut_serializer_0',
  '.Lext_switch:\n    bl .Lext_power\n    b .Lext_success':'.Lext_switch:\n    mov r0, r1\n    movs r1, #0\n    bl .Lcut_action\n    cmp r0, #1\n    beq .Lcut_uart1_apply\n    b .Lext_rtc_error\n.Lcut_uart1_apply:\n    mov r0, sp\n    ldrb r1, [r0, #2]\n    bl .Lext_power\n    bl hook_cut_enforce\n    b .Lext_success',
 }
 for old,new in replacements.items():
  if source.count(old)!=1:raise ValueError('unknown frozen1.5 source pattern: '+old)
  source=source.replace(old,new)
 return (source+'\n'+Path(__file__).with_name('cutoff.s').read_text()).replace('bl hook_cut_enforce','bl .Lcut_enforce').replace('bl hook_cut_serializer_0','bl .Lcut_serializer')
