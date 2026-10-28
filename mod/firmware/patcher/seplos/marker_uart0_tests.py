"""Mandatory revision-one R64 proof through real OEM parser AND encoder.

Only the physical UART0 sender boundary is intercepted; dispatcher returns
normally so register/stack checks cover the whole original call frame.
"""
from .machine import Machine,ascii_frame
from .selftest import ascii_payload
from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP

REQUIRED=tuple('uart0-marker-'+name for name in (
 'layout-version-and-unique-hook','info-addressed-R-C-identical',
 'status-known-unknown-no-permissions','clear-addressed-idempotent',
 'unexplained-never-erased','readback-failure-not-success','foreign-and-FF-silent',
 'malformed-token-and-start-not-added','nonhex-before-OEM-normalization',
 'malformed-checksum-version-cid-length','C-and-display-canaries',
 'original-R-42-44-47-51','callee-registers-stack-and-parser-chain',
 'twelve-packs-one-target-clears'))


def uart0_exchange(m,packet):
 d=m.facts['marker_uart0'];m.put(d['uart0_rx'],packet)
 m.put(d['uart0_rx_length'],len(packet).to_bytes(2,'little'));m.put(d['uart0_state'],b'\4')
 previous=m.callback;m.marker_trace=[]
 def peripheral(board,pc):
  if pc==d['uart0_parser']:m.marker_trace.append('OEM-parser')
  if pc==m.facts.get('cutoff',{}).get('entries',{}).get('hook_cut_uart0_parser'):m.marker_trace.append('cutoff-parser')
  if pc==d['uart0_sender']:
   board.ret();return True
  return bool(previous and previous(board,pc))
 m.callback=peripheral
 try:m.run(d['uart0_dispatch'])
 finally:m.callback=previous
 if not m.num(d['uart0_state']):return b''
 return m.read(d['uart0_state']+1,m.num(d['uart0_tx_length'],2))


def validate_uart0_marker(original,patched,facts,report):
 d=facts['marker_uart0'];r=facts['ram'];rows=[]
 def check(name,fn):
  try:fn()
  except Exception as exc:raise AssertionError('uart0-marker-'+name+': '+str(exc)) from exc
  rows.append(dict(name='uart0-marker-'+name,passed=True))
 def equal(a,b):assert a==b,(a,b)
 def board(address=0,stock=False):
  m=Machine(original if stock else patched,facts);m.defaults(address);return m
 def query(m,info=b'\2',target=None):
  address=m.num(r['address']);raw=uart0_exchange(m,ascii_frame(address if target is None else target,0x64,info))
  return ascii_payload(raw,address) if raw else None
 expected=b'MNT\4'+bytes(facts['oracle']['base_version'])+bytes([report['base_revision'],*map(int,report['patch_version'].split('.'))])+bytes.fromhex(report['build_id'])+bytes([report['image_flags']])
 def layout():
  equal((report['info_format'],report['info_bytes'],len(expected)),(4,19,19))
  assert report['uart0_marker'] and report['image_flags']&16
  equal(len(report['hooks']),len(set(report['hooks'].values())))
  assert 'hook_uart0_marker_parser' in report['hooks'] and 'hook_cut_uart0_parser' not in report['hooks']
 check('layout-version-and-unique-hook',layout)
 def infos():
  for adr in range(22):
   m=board(adr);m.put(r['group0'],b'\0')
   for marker in (0xffffffff,0,0x12345678):
    m.put(0x23000,marker.to_bytes(4,'little'));raw=uart0_exchange(m,ascii_frame(adr,0x64,b'\3'))
    equal(ascii_payload(raw,adr),(0,expected));equal(raw[9:13],b'8026');equal(len(raw),56)
    equal(ascii_payload(m.transact(ascii_frame(adr,0x64,b'\3'),True),adr),(0,expected))
   equal(m.flash_ops,[]);equal(m.saves,[])
 check('info-addressed-R-C-identical',infos)
 def status():
  for adr in range(22):
   m=board(adr);m.put(r['group0'],b'\0');m.put(r['slaves'],b'\7')
   for marker in (0xffffffff,0,0x12345678):
    raw=marker.to_bytes(4,'little');m.put(0x23000,raw);equal(query(m),(0,raw+b'\7'))
   equal(m.flash_ops,[])
 check('status-known-unknown-no-permissions',status)
 def clears():
  for adr in range(22):
   m=board(adr);m.put(r['group0'],b'\0');m.put(0x23000,bytes(4));before=m.payload()
   for _ in range(2):equal(query(m,b'\0\xc3\x5a'),(0,b'\xff'*4+bytes([m.num(r['slaves'])])))
   equal(m.flash_ops,[('erase',0x23000)]);equal(m.payload(),before);equal(m.saves,[])
 check('clear-addressed-idempotent',clears)
 def unknown():
  for marker in (1,0xfffffffe,0x12345678):
   m=board(11);raw=marker.to_bytes(4,'little');m.put(0x23000,raw)
   equal(query(m,b'\0\xc3\x5a'),(5,b''));equal(m.read(0x23000,4),raw);equal(m.flash_ops,[])
 check('unexplained-never-erased',unknown)
 def failures():
  for adr in (0,1,11,21):
   m=board(adr);m.put(0x23000,bytes(4));m.iap_fail=True
   equal(query(m,b'\0\xc3\x5a'),(5,b''));equal(m.read(0x23000,4),bytes(4))
 check('readback-failure-not-success',failures)
 def foreign():
  for adr in (0,1,11,21):
   for target in (0,1,11,21,22,255):
    if adr==target:continue
    m=board(adr);m.put(0x23000,bytes(4))
    for data in (b'\2',b'\3',b'\0\xc3\x5a'):
     equal(uart0_exchange(m,ascii_frame(target,0x64,data)),b'')
    equal(m.flash_ops,[]);equal(m.read(0x23000,4),bytes(4))
 check('foreign-and-FF-silent',foreign)
 def tokens():
  for payload in (b'\5' if report.get('extended_diagnostics') else b'\4',b'\1\xc3\x5a',b'\0\xc3\0',b'\0\0\x5a'):
   m=board();m.put(0x23000,bytes(4));equal(query(m,payload),(5,b''));equal(m.flash_ops,[])
 check('malformed-token-and-start-not-added',tokens)
 def nonhex():
  good=ascii_frame(0,0x64,b'\0\xc3\x5a')
  for offset in range(1,len(good)-1):
   if offset in (7,8):continue # Unknown command follows the original path.
   m=board();m.put(0x23000,bytes(4));raw=bytearray(good);raw[offset]=ord('G')
   if offset<len(raw)-5:raw[-5:-1]=f'{(-sum(raw[1:-5]))&65535:04X}'.encode()
   out=uart0_exchange(m,raw);assert not out or ascii_payload(out)[0]!=0
   equal(m.flash_ops,[]);equal(m.read(0x23000,4),bytes(4))
 check('nonhex-before-OEM-normalization',nonhex)
 def malformed():
  good=ascii_frame(0,0x64,b'\0\xc3\x5a');bad=[good[:-5]+b'0000\r',good[:-1]+b'X',ascii_frame(0,0x64,b''),ascii_frame(0,0x64,b'\2\0')]
  for offset,value in ((1,b'21'),(5,b'47'),(9,b'0006')):
   raw=bytearray(good);raw[offset:offset+len(value)]=value;raw[-5:-1]=f'{(-sum(raw[1:-5]))&65535:04X}'.encode();bad.append(bytes(raw))
  for raw in bad:
   m=board();m.put(0x23000,bytes(4));out=uart0_exchange(m,raw)
   assert not out or ascii_payload(out)[0]!=0
   equal(m.flash_ops,[]);equal(m.read(0x23000,4),bytes(4))
 check('malformed-checksum-version-cid-length',malformed)
 def canaries():
  m=board(11);regions=[(r['rx']-1,0x250),(r['lcd_meta']-0xc0,0x1ba)]
  for a,n in regions:m.put(a,bytes((i*17+3)&255 for i in range(n)))
  before=[m.read(a,n) for a,n in regions];query(m,b'\3');query(m);m.put(0x23000,bytes(4));query(m,b'\0\xc3\x5a')
  equal([m.read(a,n) for a,n in regions],before)
 check('C-and-display-canaries',canaries)
 def original_commands():
  for adr in (0,1,11):
   for cmd in (0x42,0x44,0x47,0x51):
    before=board(adr,True);m=board(adr);packet=ascii_frame(adr,cmd,bytes([adr]) if cmd in (0x42,0x44) else b'')
    equal(uart0_exchange(m,packet),uart0_exchange(before,packet))
 check('original-R-42-44-47-51',original_commands)
 def abi():
  m=board(11);regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
  values=[0x12345000+i for i in range(8)]
  for reg,value in zip(regs,values):m.uc.reg_write(reg,value)
  sp=m.uc.reg_read(UC_ARM_REG_SP);equal(query(m,b'\3'),(0,expected))
  equal([m.uc.reg_read(reg) for reg in regs],values);equal(m.uc.reg_read(UC_ARM_REG_SP),sp)
  equal(m.marker_trace.count('OEM-parser'),1)
  equal(m.marker_trace.count('cutoff-parser'),int(report.get('cutoff',False)))
 check('callee-registers-stack-and-parser-chain',abi)
 def shared_bus():
  machines=[board(i) for i in range(12)]
  for m in machines:m.put(0x23000,bytes(4))
  replies=[uart0_exchange(m,ascii_frame(7,0x64,b'\0\xc3\x5a')) for m in machines]
  equal([i for i,x in enumerate(replies) if x],[7])
  equal([m.read(0x23000,4) for m in machines],[b'\xff'*4 if i==7 else bytes(4) for i in range(12)])
 check('twelve-packs-one-target-clears',shared_bus)
 equal(set(REQUIRED),{x['name'] for x in rows})
 return rows
