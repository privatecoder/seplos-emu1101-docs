"""Mandatory independent native scheduler regression; synthetic IRQ boundaries only.

UART0 = RS485-1/RS485-2; UART1 = RS485 pair in the CAN socket;
UART2 = local display/Bluetooth. Maskable native IRQ delivery is modeled; physical
occurrence, all firmware races and complete system reachability are not proven.
"""
from .interrupt_tests import InterruptMachine,_native_contract,CALLEE
from .thumb import Code,encode_bl
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
 UC_ARM_REG_R3,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R12,UC_ARM_REG_SP,
 UC_ARM_REG_LR,UC_ARM_REG_XPSR,UC_ARM_REG_PRIMASK)

REQUIRED=tuple('scheduler_atomic-'+name for name in (
 'guarded-veneer-and-native-skip','all-byte-semantics-and-ABI',
 'native-wake-every-boundary-and-exact-mask','bounded-masked-interval',
 'slow-coalescing-and-new-pending','OEM-lost-update-control'))


def validate_scheduler_atomic(original,patched,facts,build):
 """Execute published bytes, deriving expectations from the unmodified native CFG."""
 code=Code(original.app);native=_native_contract(original,facts,code)
 site=native['cleanup'];end=site+14;a=native['flags'];entry=build['entries']['hook_scheduler_atomic']
 fixed=Code(patched.app);appendix=fixed.body(entry);rows=[]
 def check(name,fn):
  try:details=fn()
  except Exception as exc:raise AssertionError('scheduler_atomic-'+name+': '+str(exc)) from exc
  rows.append(dict(name='scheduler_atomic-'+name,passed=True,**(details or {})))
 def board(image=patched,value=4,mask=0):
  m=InterruptMachine(image,facts);m.defaults(1)
  m.put(native['startup'],(601).to_bytes(2,'little'));m.put(a,bytes([value]))
  m.put(native['wake_status'],b'\x20');m.put(native['wake_counter'],(200).to_bytes(2,'little'))
  m.uc.reg_write(UC_ARM_REG_R5,a);m.uc.reg_write(UC_ARM_REG_R6,8)
  m.uc.reg_write(UC_ARM_REG_PRIMASK,mask)
  return m
 def guarded():
  contract=build.get('scheduler_atomic',{})
  assert contract.get('enabled') is True,'missing enabled contract'
  assert (contract.get('site'),contract.get('branch_site'),contract.get('continuation'),contract.get('flags'))==(site,site+4,end,a),'native contract mismatch'
  assert patched.app[site:site+4]==encode_bl(site,entry),'guarded BL veneer'
  assert fixed.ins[site+4].op=='b' and fixed.ins[site+4].target==end,'continuation bypass branch'
  assert patched.app[site+6:site+14]==original.app[site+6:site+14],'native skip/store bytes changed'
  assert site in {i.at for i in code.body(facts['functions']['main'])},'cleanup outside main CFG'
  for mask in (0,1):
   m=board(mask=mask,value=0xa5);sp=m.uc.reg_read(UC_ARM_REG_SP)
   m.uc.reg_write(UC_ARM_REG_R0,0x12345678);m.uc.reg_write(UC_ARM_REG_R1,0x87654321)
   m.execute(site+6,end)
   assert m.num(a)==0xa5 and entry not in m.executed,'native skip path entered cleanup'
   assert m.uc.reg_read(UC_ARM_REG_R0)==0x12345678 and m.uc.reg_read(UC_ARM_REG_R1)==0x87654321,'native skip path changed registers'
   assert m.uc.reg_read(UC_ARM_REG_SP)==sp and m.uc.reg_read(UC_ARM_REG_PRIMASK)==mask,'native skip path changed stack/mask'
  return dict(guarded_original_bytes=6,unchanged_skip_bytes=2)
 check('guarded-veneer-and-native-skip',guarded)
 def semantics():
  # Reuse one machine: the cleanup is leaf code, every tested input is reset.
  m=board();regs=(UC_ARM_REG_R2,UC_ARM_REG_R3,*CALLEE,UC_ARM_REG_R12)
  sentinels=[0x12340000+j for j in range(len(regs))]
  for value in range(256):
   for mask in (0,1):
    for cv in range(4):
     for r,v in zip(regs,sentinels):m.uc.reg_write(r,v)
     m.uc.reg_write(UC_ARM_REG_R5,a);m.uc.reg_write(UC_ARM_REG_R6,8)
     expected=list(sentinels);expected[regs.index(UC_ARM_REG_R5)]=a;expected[regs.index(UC_ARM_REG_R6)]=8
     m.uc.reg_write(UC_ARM_REG_PRIMASK,mask);m.uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(cv<<28))
     sp=m.uc.reg_read(UC_ARM_REG_SP);canary=bytes(range(16));m.put(sp-24,canary);m.put(a,bytes([value]))
     m.execute(site,end)
     assert m.num(a)==(value|8)&0xfb,'all-byte flag semantics'
     assert m.uc.reg_read(UC_ARM_REG_R0)==(value|8)&0xfb and m.uc.reg_read(UC_ARM_REG_R1)==0xfb,'cleanup R0/R1 results'
     assert [m.uc.reg_read(r) for r in regs]==expected,'cleanup preserved-register ABI'
     assert m.uc.reg_read(UC_ARM_REG_SP)==sp and m.read(sp-24,16)==canary,'cleanup stack/canary ABI'
     assert m.uc.reg_read(UC_ARM_REG_PRIMASK)==mask,'exact incoming PRIMASK restoration'
     assert m.uc.reg_read(UC_ARM_REG_XPSR)&0xf0000000==cv<<28,'cleanup APSR NZCV effects'
  return dict(flag_inputs=256,incoming_masks=[0,1],incoming_CV=4,cases=2048)
 check('all-byte-semantics-and-ABI',semantics)
 boundaries=[site,*[i.at for i in appendix],site+4,end]
 def wake_boundaries():
  observations=[]
  for mask in (0,1):
   for boundary in boundaries:
    m=board(mask=mask)
    if boundary==end:
     m.execute(site,end);m.pend(1)
     if not mask:m.idle()
    else:
     m.at(boundary,lambda b:b.pend(1));m.execute(site,end)
    assert m.uc.reg_read(UC_ARM_REG_PRIMASK)==mask,'exact mask after boundary request'
    if mask:
     assert not m.irq_log and 1 in m.pending,'masked request delivered/lost before restore'
     assert m.num(a)==8,'masked cleanup changed semantics'
     m.uc.reg_write(UC_ARM_REG_PRIMASK,0);m.idle()
    assert native['wake'] in m.executed,'native wake did not execute'
    assert m.num(a)==10,'native wake enable bit lost by cleanup'
    assert not m.num(native['wake_status'])&32 and not m.pending,'native wake request not completed'
    observations.append(dict(mask=mask,boundary=boundary,flags=m.num(a)))
  return dict(boundaries=boundaries,cases=len(observations),observations=observations,
   synthetic_call_state=True,full_system_reachability_proven=False,physical_occurrence_proven=False)
 check('native-wake-every-boundary-and-exact-mask',wake_boundaries)
 def bounded():
  m=board();seen=[];previous=m.callback
  def observe(b,pc):
   if pc==site or pc==site+4 or pc in {i.at for i in appendix}:seen.append((pc,b.uc.reg_read(UC_ARM_REG_PRIMASK)))
   return bool(previous and previous(b,pc))
  m.callback=observe;m.execute(site,end)
  masked=[pc for pc,mask in seen if mask]
  assert len(appendix)==10 and len(seen)==12,'bounded appendix instruction count'
  assert len(masked)==6,'bounded six-instruction masked interval'
  assert [fixed.ins[pc].op for pc in masked]==['ldrb','orrs','movs','ands','strb','msr'],'masked interval extends outside fresh RMW/restore'
  assert not any(i.op=='bl' for i in appendix),'masked cleanup calls unrelated work'
  return dict(appendix_instructions=10,veneer_instructions=2,masked_instructions=6,
   instruction_count_only=True,cycle_bound_claimed=False)
 check('bounded-masked-interval',bounded)
 def slow():
  # Native 200th measurement tick coalesces a bit already pending before cleanup.
  m=board(value=6);m.put(native['wake_status'],b'\0');m.put(native['slow_counter'],(199).to_bytes(2,'little'))
  seen=[];m.at(native['slow_store'],lambda b:seen.append(b.num(a)))
  m.at(site,lambda b:b.pend(1));m.execute(site,end)
  assert seen==[6] and m.num(a)==10,'already-set slow tick must coalesce'
  assert native['measurement'] in m.executed and m.num(native['slow_counter'],2)==0,'native slow producer absent'
  # A genuinely new 200th tick deferred across the store remains pending afterwards.
  store=next(i.at for i in appendix if i.op=='strb')
  m=board(value=6);m.put(native['wake_status'],b'\0');m.put(native['slow_counter'],(199).to_bytes(2,'little'))
  seen=[];m.at(native['slow_store'],lambda b:seen.append(b.num(a)))
  m.at(store,lambda b:b.pend(1));m.execute(site,end)
  assert seen==[10] and m.num(a)==14,'new post-cleanup slow tick was cleared'
  assert m.num(native['slow_counter'],2)==0 and not m.pending,'new native slow tick not completed'
  return dict(coalesced_flags=10,new_pending_flags=14)
 check('slow-coalescing-and-new-pending',slow)
 def oem():
  m=board(original);m.at(site+2,lambda b:b.pend(1));m.execute(site,end)
  assert native['wake'] in m.executed and not m.num(native['wake_status'])&32,'OEM native wake did not execute'
  assert m.num(a)==8,'OEM lost-update counterexample changed'
  control=board(original);control.execute(site,end);control.pend(1);control.idle()
  assert control.num(a)==10,'OEM post-cleanup wake control failed'
  return dict(kind='characterization',observed_oem_lost_update=True,synthetic_call_state=True,
   full_system_reachability_proven=False,physical_occurrence_proven=False)
 check('OEM-lost-update-control',oem)
 assert {r['name'] for r in rows}==set(REQUIRED),'incomplete scheduler atomic suite'
 return rows
