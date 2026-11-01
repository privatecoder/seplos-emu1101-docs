"""Guarded read-only history, calibration and SOC/energy appendix extension.

Roles are resolved from native call relationships and complete instruction-body
contracts. The contracts normalize PC-relative addresses, retain local branch
edges and operand offsets, and deliberately reject unreviewed compiler shapes.
No image/version-to-address table and no new OEM hooks or static RAM.
The publisher must first run the complete OEM guards. The local cross-checks
bind every address/callee reused by these reads; unrelated native calibration
defaults, secondary conversions and loaders remain covered by those guards.
"""
from pathlib import Path
import hashlib,json
from .analysis import unique
from .thumb import Code

_CONTRACTS={
 'cal_save':'f9e5118f7f9760c4057dc0a452931436a94bd511ce5267765d9e86fef4a120a5',
 'cal_load':'a84f35cf171c5ddde73371210a6deb2f4bcac82216e2c063bc816f07ff27b5d2',
 'soc_save':'975a7fee06943c543bc59720d800b7a516df3b1938243616afa3f6cef1fa47d0',
 'soc_load':'8878ef18a173a48df6fe61e550d340afb93c5a33bda3f1bd3db62dd9e8b68f72',
 'history_read':'e39ddd800e84fa8432141b6ac766ee9deb321765a57f366ee4993effbc7be568',
 'history_select':'7516909f4bddcedf958850efc832556065712e0fd31581a394b01f66294c5d92',
 'history_oem':'c5da0d923864972d72639bbcca95b06b5b7d6b45ddf6489bb984333007ed585e',
 'voltage_cal':'cb6d071de74a45061247fb17c09c6133cbb0cac6401493fe2fae78b059bd2ba7',
}

def _fingerprint(c,a):
 return hashlib.sha256(json.dumps([[i.at-a,i.token(),i.target-a if i.target is not None and i.op!='bl' else None] for i in c.body(a)],separators=(',',':')).encode()).hexdigest()

def discover_remote(image,facts):
 c=Code(image.app);f=facts['functions'];r=facts['ram'];proof=[]
 def guard(a,name):
  if _fingerprint(c,a)!=_CONTRACTS[name]:raise ValueError('unsupported remote diagnostic '+name+' body')
  proof.append(dict(role=name,at=a,contract=_CONTRACTS[name]));return a
 def lit(a,offset):
  i=c.ins.get(a+offset)
  if i is None or i.literal is None:raise ValueError('remote diagnostic missing role literal')
  return i.literal
 # Block-2 serializer is selected by its actual IAP call, not a known address.
 sites=[i.at for i in c.ins.values() if i.op=='bl' and i.target==f['iap_write'] and c.ins.get(i.at-2) and c.ins[i.at-2].token()==['movs','r0, #0x2']]
 call=unique(sites,'remote calibration block-2 serializer')
 cal=guard(call-0xc0,'cal_save');load=guard(max(i.at+i.size for i in c.body(cal)),'cal_load')
 if c.ins[load+4].target!=f['iap_read'] or lit(cal,4)!=r['iap_buffer'] or lit(load,0x14)!=r['iap_buffer']:
  raise ValueError('remote calibration loader/scratch relationship')
 voltage=unique([i.at-0x86 for i in c.ins.values() if i.op=='bl' and i.target==cal and c.ins.get(i.at-0x86) and c.ins[i.at-0x86].op=='push'],'remote voltage calibration consumer')
 guard(voltage,'voltage_cal')
 if lit(voltage,0x22)!=r['small'] or lit(voltage,0x54)!=r['small'] or lit(voltage,0x5a)!=lit(cal,0x12):
  raise ValueError('remote calibration cell-count/gain consumer binding')
 soc=guard(f['capacity_save'],'soc_save');socload=guard(max(i.at+i.size for i in c.body(soc)),'soc_load')
 measure=lit(soc,2)
 if c.ins[soc+0x60].target!=f['iap_write'] or c.ins[socload+4].target!=f['iap_read'] or lit(socload,8)!=measure or lit(socload,0x14)!=r['iap_buffer']:
  raise ValueError('remote SOC serializer/loader IAP and RAM binding')
 if lit(soc,4)!=r['iap_buffer'] or measure+14!=r['learned'] or lit(socload,0x7a)!=r['words']+64:
  raise ValueError('remote SOC serializer/fallback binding')
 # Unique read-only EEPROM adapter: 128-byte index stride, 94-byte read, mode1.
 signature=[['push','{r4, lr}'],['ldr-pc','r1','ram'],['movs','r2, #0xa4'],['strb','r2, [r1]'],['lsls','r0, r0, #0x7']]
 reader=guard(unique([a for a in c.ins if [i.token() for i in c.window(a,len(signature))]==signature],'remote history record reader'),'history_read')
 select=guard(reader+max(i.at+i.size-reader for i in c.body(reader)),'history_select')
 ctrl=lit(reader,2)
 if lit(reader,12)!=ctrl or lit(select,2)!=ctrl:raise ValueError('remote history shared-control binding')
 owner=unique([i.at-0x26 for i in c.ins.values() if i.op=='bl' and i.target==reader and c.ins.get(i.at-0x26) and c.ins[i.at-0x26].op=='push'],'remote OEM history owner')
 guard(owner,'history_oem')
 if c.ins[owner+0x22].target!=select or lit(owner,2)!=ctrl+128 or lit(owner,0x12)!=facts['marker_uart0']['uart0_rx']:
  raise ValueError('remote history cursor/reader/OEM consumer binding')
 transfer=c.ins[reader+0x16].target
 if transfer!=facts['power_rtc']['rtc_transfer']:raise ValueError('remote history common I2C driver binding')
 if r['tx_length']-r['tx']<212 or r['info']+194>r['tx_length']:
  raise ValueError('remote UART1 history buffer bounds')
 roles=dict(cal_save=cal,cal_load=load,event=lit(cal,2),cell_gains=lit(cal,0x12)+8,
  cell_count=r['small']+5,voltage0=lit(cal,0x32)+8,voltage1=lit(cal,0x44)+8,
  current_a=lit(cal,0x56),current_b=lit(cal,0x88),measure=measure,
  p58=r['words']+116,p59=r['words']+118,soc_save=soc,soc_load=socload,
  history_read=reader,history_select=select,history_control=ctrl,
  history_count=ctrl+0x8e,history_start=ctrl+0x90,history_cursor=ctrl+0x92,
  history_data=ctrl+10,history_transfer=transfer,history_oem=owner,
  cal_primary=facts.get('storage_diagnostics',facts.get('cutoff'))['nv_primary']+2*4096)
 roles['cal_backup']=roles['cal_primary']+4096
 for name in ('event','cell_gains','cell_count','voltage0','voltage1','current_a','current_b','measure','p58','p59','history_control'):
  if not 0x20000000<=roles[name]<image.sp-256:raise ValueError('remote diagnostic RAM role bounds: '+name)
 if roles['event']!=lit(voltage,0x7a)+1 or roles['current_a']!=measure-0x50 or roles['current_b']!=measure-0x28 or roles['voltage1']!=measure-0x9c or roles['voltage0']!=measure-0x84 or roles['cell_gains']!=measure-0x15c:
  raise ValueError('remote diagnostic measurement/calibration layout relationship')
 if len({roles[k] for k in ('current_a','current_b','voltage0','voltage1','cell_gains')})!=5:
  raise ValueError('remote diagnostic aliased calibration roles')
 # Saver/loader independently bind the active structures and original IAP buffer.
 for off,name in ((8,'event'),(10,'cell_gains'),(12,'current_a'),(14,'current_b'),(0x46,'voltage0'),(0x5a,'voltage1')):
  expected=roles[name]-(8 if name in ('cell_gains','voltage0','voltage1') else 0)
  if lit(load,off)!=expected:raise ValueError('remote calibration load/save role disagreement')
 roles['evidence']=proof
 facts['remote_diagnostics']=roles
 return roles


def _once(source,old,new):
 if source.count(old)!=1:raise ValueError('unknown remote diagnostic source contract: '+old)
 return source.replace(old,new)


def source_remote(source):
 source=_once(source,'.Lraw_address_ok:\n    ldr r3, =PARSER+1',
  '.Lraw_address_ok:\n    bl .Lrem_raw_C\n    cmp r0, #1\n    beq .Lrem_raw_valid\n    b silent\n.Lrem_raw_valid:\n    ldr r3, =PARSER+1')
 source=_once(source,'parsed:\n    ldr r4, =COMMAND',
  'parsed:\n    bl .Lrem_C\n    cmp r0, #1\n    beq .Lrem_C_continue\n    b handled\n.Lrem_C_continue:\n    ldr r4, =COMMAND')
 source=_once(source,'    cmp r6, #24\n    beq .Lm0_size',
  '    cmp r6, #22\n    beq .Lm0_size\n    cmp r6, #24\n    beq .Lm0_size')
 source=_once(source,'    cmp r6, #19\n    bne .Lm0_clear',
  '    mov r0, r4\n    adds r1, r6, #1\n    ldr r2, =M0_UART0_INFO\n    bl .Lrem_service\n    cmp r0, #0\n    blt .Lrem_R_continue\n    ldr r2, =M0_UART0_TX_LENGTH\n    strh r0, [r2]\n    ldr r2, =M0_UART0_RTN\n    strb r1, [r2]\n    b .Lm0_return\n.Lrem_R_continue:\n    cmp r6, #19\n    bne .Lm0_clear')
 return source+'\n'+Path(__file__).with_name('remote_diagnostics.s').read_text()
