"""Read-only storage diagnostics overlay: no new OEM hooks, no Cutoff discovery.

The guarded OEM IAP reader proves both buffers and sector addressing. Only
raw reads and the native record CRC are called; the repairing reader is never
invoked by the new target code. Reuse the diagnostic core of service.s at
build time while excluding all lock/cache/checkpoint/write code.
"""
from pathlib import Path
from .analysis import unique
from .thumb import Code


def discover_diagnostics(image,facts):
 c=Code(image.app);f=facts['functions'];r=facts['ram']
 w=c.window(f['iap_read'],11)
 expected=[['push','{r1, r2, r3, r4, r5, r6, r7, lr}'],['mov','r7, r0'],
  ['lsls','r0, r7, #0xc'],['movs','r1, #0x25'],['lsls','r1, r1, #0xc'],
  ['adds','r4, r0, r1'],['str','r4, [sp, #0x4]'],['movs','r2, #0x40'],
  ['ldr-pc','r1','ram'],['mov','r0, r4'],['bl']]
 if [i.token() for i in w]!=expected or w[8].literal!=r['iap_buffer']:
  raise ValueError('unsupported diagnostic IAP addressing/buffer ABI')
 calls=[i for i in c.body(f['iap_read']) if i.op=='bl']
 raw_read=w[-1].target
 if len(calls)<3 or calls[1].target!=raw_read:raise ValueError('diagnostic mirror raw-read ABI')
 mirror=c.window(w[-1].at+4,6)
 if [i.token() for i in mirror]!=[['movs','r0, #0x1'],['lsls','r0, r0, #0xc'],['adds','r0, r4, r0'],['movs','r2, #0x40'],['ldr-pc','r1','ram'],['bl']] or mirror[4].literal!=r['iap_buffer']+256:
  raise ValueError('unsupported diagnostic mirror stride/buffer ABI')
 crc=unique([i.target for i in c.body(f['iap_write']) if i.op=='bl' and i.target not in (f['iap_erase'],f['iap_program'])],'diagnostic record CRC')
 if calls[2].target!=crc:raise ValueError('diagnostic CRC reader/writer disagreement')
 # Both256-byte scratch ranges are original IAP buffers, below parameter RAM
 # and original SP; no startup reservation or display/UART buffer is borrowed.
 if not (0x20000000<=r['iap_buffer'] and r['iap_buffer']+512<=r['words']<image.sp):
  raise ValueError('diagnostic two-buffer bounds/overlap')
 # These constants are proved above by the native IAP block<<12 +25<<12 ABI.
 page=1<<12;primary=0x25*page
 roles=dict(nv_primary=primary,nv_backup=primary+page,soc_primary=primary+6*page,
  soc_backup=primary+7*page,nv_scratch=r['iap_buffer']+256,nv_crc=crc,flash_read=raw_read)
 facts['storage_diagnostics']=roles
 return roles


def _replace_once(source,old,new):
 if source.count(old)!=1:raise ValueError('unknown storage diagnostic source contract: '+old)
 return source.replace(old,new)


def source_diagnostics(source):
 # Extend existing handlers only: these calls live entirely in the appendix.
 source=_replace_once(source,'address_ok:\n    cmp r2, #0',
  'address_ok:\n    bl .Lsvc_C_diag\n    cmp r0, #1\n    bne .Ldiag152_C_continue\n    b handled\n.Ldiag152_C_continue:\n    cmp r2, #0')
 source=_replace_once(source,'    cmp r0, #0x33\n    m0_bne .Lm0_bad',
  '    cmp r0, #0x34\n    m0_beq .Ldiag152_R_diag\n    cmp r0, #0x33\n    m0_bne .Lm0_bad')
 source=_replace_once(source,'.Lm0_clear:\n',
  '.Ldiag152_R_diag:\n    ldr r0, =M0_UART0_INFO\n    bl .Lsvc_diag\n    movs r0, #0x26\n    b .Lm0_success\n.Lm0_clear:\n')
 shared=Path(__file__).with_name('service.s').read_text()
 end='/* Snapshot with native serializer; r4 mask is saved at native frame SP+0. */'
 if shared.count(end)!=1:raise ValueError('unknown shared diagnostic boundary')
 shared=shared[shared.index('.p2align 2'):shared.index(end)]
 # Omit reserved-bit interpretation completely, including unused lock helpers.
 for buffer,offset in (('IAP_BUFFER',7),('CUT_NV_SCRATCH',8)):
  shared=_replace_once(shared,f'    ldr r1, ={buffer}\n    bl .Lsvc_lock\n    strb r0, [r6, #{offset}]',
   f'    movs r0, #255\n    strb r0, [r6, #{offset}]')
 start=shared.index('    ldr r0, =CUT_RAM\n');stop=shared.index('.Lsvc_diag_copy:')
 cache=shared[start:stop]
 if cache.count('strb r2, [r6, #9]')!=1 or cache.count('.Lsvc_cache_done:')!=1:raise ValueError('unknown shared diagnostic cache block')
 shared=shared[:start]+'    movs r0, #0\n    strb r0, [r6, #9]\n'+shared[stop:]
 start=shared.index('.Lsvc_lock:');stop=shared.index('.Lsvc_pair_equal:')
 shared=shared[:start]+shared[stop:]
 if any(word in shared for word in ('CUT_RAM','GROUP0','.Lsvc_lock','hook_service_','CAPACITY_SAVE','IAP_WRITE','IAP_ERASE','IAP_PROGRAM')):
  raise ValueError('non-reading code in storage diagnostics')
 return source+'\n/*Raw record diagnostics only; no lock/cache or reset code. */\n'+shared
