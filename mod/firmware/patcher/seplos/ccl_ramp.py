"""Full-only source-bound downward CCL configuration; existing mirrored record tail."""
from pathlib import Path
from .thumb import Code
from .analysis import unique

def discover_ccl_ramp(image,facts):
 if image.sha!=facts['original_app_sha256']:raise ValueError('CCL analysis/input digest mismatch')
 from .guards import guard
 guard(image,facts)
 c=Code(image.app);cut=facts['cutoff'];body=c.body(cut['ccl'])
 signature=[['subs','r3, r1, r0'],['cmp','r3, r2'],['ble',None],['subs','r0, r1, r2'],['strh','r0, [r5, #0x24]']]
 site=unique([i.at for i in body if [x.token() for x in c.window(i.at,2)]==signature[:2]],'CCL downward comparison')
 w=c.window(site,7)
 if [i.op for i in w]!=['subs','cmp','ble','subs','strh','b','strh'] or w[2].target!=w[6].at or w[3].token()!=signature[3] or w[4].token()!=signature[4] or w[6].token()!=['strh','r0, [r5, #0x24]']:
  raise ValueError('unsupported CCL saturation branch')
 if [i.token() for i in c.window(site-28,4)]!=[['movs','r2, #0xa'],['muls','r1, r2, r1'],['uxth','r2, r1'],['ldrh','r1, [r5, #0x24]']]:
  raise ValueError('unsupported CCL step/count arithmetic')
 if any(i.target==site+2 for i in c.ins.values()):raise ValueError('CCL hook has an interior branch entry')
 if cut['ram']!=image.sp or cut['nv_group_offset']!=163:raise ValueError('CCL cache/record layout changed')
 d=dict(site=site,ram=cut['ram']+3,record_offset=173,record_bytes=176,minimum=1,maximum=20,default=1)
 d['hooks']={'hook_ccl_decrease':site}
 d['evidence']=[dict(hook='hook_ccl_decrease',site=site,opcode=image.app[site:site+4].hex())]
 facts['ccl_ramp']=d
 return d

def source_ccl_ramp(source):
 def once(old,new):
  nonlocal source
  if source.count(old)!=1:raise ValueError('CCL source contract: '+old)
  source=source.replace(old,new)
 once('.byte 0, 15','.byte 0, 31')
 if source.count('    movs r2, #44\n    ldr r3, =IAP_PROGRAM+1')!=1 or source.count('    cmp r1, #176\n    blo .Lnv_compare')!=1:
  raise ValueError('CCL extension requires the verified 176-byte parameter writer')
 # Both mirrors are still in their respective buffers at this point.
 once('    bl .Lcut_mirrors\n    mov r4, r0','    bl .Lcut_mirrors\n    bl .Lccl_load\n    mov r4, r0')
 once('    ldr r5, =CUT_NV_PRIMARY\n    bl .Lnv_one','    bl .Lccl_store\n    ldr r5, =CUT_NV_PRIMARY\n    bl .Lnv_one')
 # Only UART1 writes use its ordinary parameter-write permission gate.
 once('    bl .Lrem_service\n    b .Lrem_C_reply','    movs r3, #1\n    bl .Lrem_service\n    b .Lrem_C_reply')
 once('    ldr r2, =M0_UART0_INFO\n    bl .Lrem_service','    ldr r2, =M0_UART0_INFO\n    movs r3, #0\n    bl .Lrem_service')
 once('    beq .Lrem_raw_check\n    cmp r0, #0x36\n    bne .Lrem_raw_good','    beq .Lrem_raw_check\n    cmp r0, #0x37\n    beq .Lrem_raw_check\n    cmp r0, #0x38\n    beq .Lrem_raw_check\n    cmp r0, #0x36\n    bne .Lrem_raw_good')
 once('    cmp r0, #0x36\n    bne .Lrem_C_original','    cmp r0, #0x37\n    beq .Lrem_C_own\n    cmp r0, #0x38\n    beq .Lrem_C_own\n    cmp r0, #0x36\n    bne .Lrem_C_original')
 once('.Lrem_service:\n','.Lrem_service:\n    push {r4, lr}\n    push {r0, r1, r2, r3}\n    bl .Lccl_service\n    cmp r0, #0\n    blt .Lccl_delegate\n    add sp, #16\n    pop {r4, pc}\n.Lccl_delegate:\n    pop {r0, r1, r2, r3}\n    bl .Lccl_old_service\n    pop {r4, pc}\n.Lccl_old_service:\n')
 return source+'\n'+Path(__file__).with_name('ccl_ramp.s').read_text()
