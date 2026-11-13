"""Native IRQ replay and scheduler contracts; no physical timing claim."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build
from seplos.interrupt_tests import InterruptMachine,validate_interrupts,REQUIRED,FULL_REQUIRED
from unicorn.arm_const import UC_ARM_REG_PRIMASK,UC_ARM_REG_R4

class Interrupts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  cls.facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  cls.image,cls.report=build(cls.original,cls.facts,13,ext_version='1.5.4')
 def test_mandatory_both_profiles(self):
  self.assertIsNotNone(validate_interrupts,'native interrupt validator is required')
  for profile in ('1.5.4','1.6.4'):
   with self.subTest(profile=profile):
    facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
    image,report=build(self.original,facts,13,ext_version=profile)
    rows=validate_interrupts(self.original,image,facts,report)
    self.assertEqual({r['name'] for r in rows},set(REQUIRED+(FULL_REQUIRED if profile.startswith('1.6') else ())))
    self.assertTrue(all(r['passed'] for r in rows))
    characterization=next(r for r in rows if r['name'].endswith('A8-native-wake-lost-update-and-coalescing-controls'))
    self.assertEqual(characterization['kind'],'characterization')
    self.assertTrue(characterization['observed_oem_lost_update'])
    self.assertFalse(characterization['full_system_reachability_proven'])
    self.assertFalse(characterization['physical_occurrence_proven'])
 def test_masked_pending_and_priority(self):
  self.assertIsNotNone(InterruptMachine,'opt-in IRQ scheduler is required')
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  m.uc.reg_write(UC_ARM_REG_PRIMASK,1)
  for irq in (3,2,1,0):m.pend(irq)
  m.idle();self.assertEqual(m.irq_log,[])
  m.uc.reg_write(UC_ARM_REG_PRIMASK,0);m.idle()
  self.assertEqual([x[1] for x in m.irq_log if x[0]=='enter'],[0,1,2,3])
 def test_callee_register_mutation_is_not_hidden(self):
  self.assertIsNotNone(InterruptMachine,'opt-in IRQ scheduler is required')
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  # Synthetic malformed handler: movs r4,#1; bx lr.
  m.put(0x3e000,bytes.fromhex('01247047'));m.handlers[0]=0x3e000
  m.uc.reg_write(UC_ARM_REG_R4,0x12345678);m.pend(0)
  with self.assertRaisesRegex(AssertionError,'IRQ callee-saved register clobber'):
   m.idle()
 def test_hardware_stacked_registers_restore_without_full_context(self):
  self.assertIsNotNone(InterruptMachine,'opt-in IRQ scheduler is required')
  from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  # AAPCS permits R0/R1 changes in an IRQ; the exception frame owns them.
  m.put(0x3e000,bytes.fromhex('012002217047'));m.handlers[0]=0x3e000
  m.uc.reg_write(UC_ARM_REG_R0,0x12345678);m.uc.reg_write(UC_ARM_REG_R1,0x87654321)
  sp=m.uc.reg_read(UC_ARM_REG_SP);m.pend(0);m.idle()
  self.assertEqual(m.uc.reg_read(UC_ARM_REG_R0),0x12345678)
  self.assertEqual(m.uc.reg_read(UC_ARM_REG_R1),0x87654321)
  self.assertEqual(m.uc.reg_read(UC_ARM_REG_SP),sp)
 def test_exception_frame_corruption_is_detected(self):
  self.assertIsNotNone(InterruptMachine,'opt-in IRQ scheduler is required')
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  # movs r0,#1; str r0,[sp]; bx lr corrupts stacked R0.
  m.put(0x3e000,bytes.fromhex('012000907047'));m.handlers[0]=0x3e000;m.pend(0)
  with self.assertRaisesRegex(AssertionError,'IRQ hardware exception frame clobber'):m.idle()
 def test_nested_stack_canary_corruption_is_detected(self):
  m=InterruptMachine(self.image,self.facts);m.defaults(1)
  # Write at SP-768, the explicitly bounded test envelope guard.
  m.put(0x3e000,bytes.fromhex('6846ff38ff38ff38033801607047'));m.handlers[0]=0x3e000;m.pend(0)
  with self.assertRaisesRegex(AssertionError,'IRQ nested stack canary clobber'):m.idle()
 def test_uart0_handler_mutation_hits_received_frame_assertion(self):
  from seplos.thumb import Code
  app=bytearray(self.image.app);irq=int.from_bytes(app[0x4c:0x50],'little')&~1;code=Code(self.image.app)
  rx=[i.target for i in code.body(irq) if i.op=='bl'][-1]
  state=next(i.at+i.size for i in code.body(rx) if i.op=='movs' and i.args=='r0, #0x4')
  self.assertEqual((code.ins[state].op,code.ins[state].args),('strb','r0, [r4]'))
  app[state:state+2]=bytes.fromhex('00bf')
  with self.assertRaisesRegex(AssertionError,'interrupt-diagnostics-history-native-coexistence: UART0 native RX did not complete frame'):
   validate_interrupts(self.original,self.image.with_app(app),self.facts,self.report)
 def test_priority_mutation_hits_native_priority_assertion(self):
  self.assertIsNotNone(validate_interrupts,'native interrupt validator is required')
  from seplos.hardware_tests import discover_hardware
  from seplos.thumb import Code
  hw=discover_hardware(self.original,self.facts);code=Code(self.original.app)
  priority=[i for i in code.body(hw['irq_init'][2]) if i.op=='movs' and i.args=='r2, #0x1'][-1]
  app=bytearray(self.image.app);app[priority.at:priority.at+2]=bytes.fromhex('0022')
  with self.assertRaisesRegex(AssertionError,'interrupt-native-priorities-and-vectors: native NVIC priority'):
   validate_interrupts(self.original,self.image.with_app(app),self.facts,self.report)
 def test_progress_tail_mutation_hits_contract(self):
  self.assertIsNotNone(validate_interrupts,'native interrupt validator is required')
  from seplos.thumb import Code
  code=Code(self.image.app);handler=int.from_bytes(self.image.app[0x44:0x48],'little')&~1
  tail=[i for i in code.body(handler) if i.op=='strb'][-1]
  app=bytearray(self.image.app);app[tail.at:tail.at+2]=bytes.fromhex('00bf')
  with self.assertRaisesRegex(AssertionError,'interrupt-native-progress-mask'):
   validate_interrupts(self.original,self.image.with_app(app),self.facts,self.report)

if __name__=='__main__':unittest.main()
