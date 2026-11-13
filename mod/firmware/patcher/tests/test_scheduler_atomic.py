"""Native scheduler cleanup regressions and guarded discovery."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build
from seplos.interrupt_tests import InterruptMachine,_native_contract
from seplos.thumb import Code
from unicorn.arm_const import UC_ARM_REG_R5,UC_ARM_REG_R6

class SchedulerAtomic(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  cls.facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  cls.image,cls.report=build(cls.original,cls.facts,13,ext_version='1.5.5')
 def test_native_wake_survives_cleanup(self):
  n=_native_contract(self.original,self.facts,Code(self.original.app))
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  m.put(n['startup'],(601).to_bytes(2,'little'));m.put(n['flags'],b'\4')
  m.put(n['wake_status'],b'\x20');m.put(n['wake_counter'],(200).to_bytes(2,'little'))
  m.uc.reg_write(UC_ARM_REG_R5,n['flags']);m.uc.reg_write(UC_ARM_REG_R6,8)
  m.at(self.report['entries']['hook_scheduler_atomic']+10,lambda b:b.pend(1));m.execute(n['cleanup'],n['cleanup']+14)
  self.assertEqual(m.num(n['flags']),10,'native wake enable bit lost by cleanup')
 def test_mandatory_both_profiles(self):
  from seplos.scheduler_atomic_tests import validate_scheduler_atomic,REQUIRED
  for version in ('1.5.5','1.6.5'):
   with self.subTest(version=version):
    facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
    image,report=build(self.original,facts,13,ext_version=version)
    rows=validate_scheduler_atomic(self.original,image,facts,report)
    self.assertEqual({r['name'] for r in rows},set(REQUIRED))
    self.assertTrue(all(r['passed'] for r in rows))
 def test_discovery_rejects_unbound_inputs_and_unsafe_incoming(self):
  from seplos.scheduler_atomic import discover_scheduler_atomic
  d=discover_scheduler_atomic(self.original,copy.deepcopy(self.facts));code=Code(self.original.app)
  cases=[]
  r6=next(i for i in code.body(self.facts['functions']['main']) if i.op=='movs' and i.args=='r6, #0x8')
  cases.append((r6.at,bytes.fromhex('1026'),'R5/R6 cleanup inputs'))
  setup=next(i.at for i in code.body(self.facts['functions']['main']) if i.op=='adds' and i.args=='r4, r5, #0x1')
  for raw in ('8543','20bc','20c8','01cd'):
   cases.append((setup,bytes.fromhex(raw),'R5/R6 cleanup inputs'))
  incoming=next(i for i in code.body(self.facts['functions']['main']) if i.target==d['site'])
  for target,message in ((d['site']+2,'overwritten cleanup'),(d['site']+8,'bypasses atomic cleanup')):
   # Preserve the original conditional opcode; change only its local displacement.
   opcode=int.from_bytes(incoming.raw,'little')&0xff00
   raw=(opcode|(((target-incoming.at-4)//2)&255)).to_bytes(2,'little')
   cases.append((incoming.at,raw,message))
  for at,raw,message in cases:
   with self.subTest(at=at,message=message):
    app=bytearray(self.original.app);app[at:at+len(raw)]=raw;image=self.original.with_app(app)
    facts=copy.deepcopy(self.facts);facts['original_app_sha256']=image.sha
    with self.assertRaisesRegex(ValueError,message):discover_scheduler_atomic(image,facts)
 def test_meaningful_runtime_mutations_fail_corresponding_assertions(self):
  from seplos.scheduler_atomic_tests import validate_scheduler_atomic
  entry=self.report['entries']['hook_scheduler_atomic'];code=Code(self.image.app);body=code.body(entry)
  cases=[]
  cpsid=next(i for i in body if i.op=='cpsid')
  # Removing exclusion restores the actual stale native wake overwrite.
  cases.append((cpsid.at,b'\x00\xbf','native-wake-every-boundary-and-exact-mask: native wake enable bit lost'))
  msr=next(i for i in body if i.op=='msr')
  cases.append((msr.at,b'\x00\xbf'*2,'all-byte-semantics-and-ABI: exact incoming PRIMASK'))
  # CPSIE restores zero rather than the caller mask, breaking mask=1.
  cases.append((msr.at,bytes.fromhex('62b600bf'),'all-byte-semantics-and-ABI: exact incoming PRIMASK'))
  site=self.facts['scheduler_atomic']['site']
  cases.append((site+4,self.original.app[site+4:site+6],'guarded-veneer-and-native-skip: continuation bypass'))
  cases.append((site+6,bytes.fromhex('00bf'),'guarded-veneer-and-native-skip: native skip/store'))
  # Move the fresh read above CPSID: masking a stale value is still unsafe.
  load=next(i for i in body if i.op=='ldrb')
  app=bytearray(self.image.app);app[cpsid.at:cpsid.at+2]=load.raw;app[load.at:load.at+2]=cpsid.raw
  with self.assertRaisesRegex(AssertionError,'native-wake-every-boundary-and-exact-mask: native wake enable bit lost'):
   validate_scheduler_atomic(self.original,self.image.with_app(app),self.facts,self.report)
  for at,raw,message in cases:
   with self.subTest(at=at,message=message):
    app=bytearray(self.image.app);app[at:at+len(raw)]=raw
    with self.assertRaisesRegex(AssertionError,message):validate_scheduler_atomic(self.original,self.image.with_app(app),self.facts,self.report)
if __name__=='__main__':unittest.main()
