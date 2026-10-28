"""Configurable hard-stop defaults, live selection and publication guards."""
from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame,frame
from seplos.selftest import ascii_payload

class ConfigurableHardStop(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  base=fixture('oem-16.06.13-facts')['facts'];cls.profiles={}
  for default in (False,True):
   facts=copy.deepcopy(base)
   image,report=build(cls.original,facts,13,hard_stop=default,maint_version='1.6.3')
   cls.profiles[default]=(image,facts,report)
 def board(self,default=False,mode=0xc0,adr=1):
  im,facts,_=self.profiles[default];m=Machine(im,facts);m.defaults(adr)
  m.put(m.r['group0'],bytes([(m.num(m.r['group0'])&0x3f)|mode]))
  m.put(facts['power_rtc']['system_status'],b'\0');m.put(0x20000030,bytes(8))
  m.put(facts['hard_stop']['event6'],b'\2');m.put(0x200000c4,b'\0')
  return m
 def charge(self,m):
  m.run(m.facts['hard_stop']['function'])
  return bool(m.num(m.facts['hard_stop']['forbidden_flags'])&64)
 def test_version_and_dynamic_default_flags(self):
  for default in (False,True):
   m=self.board(default);rtn,data=ascii_payload(m.transact(ascii_frame(1,0x64,b'\3'),True),1)
   self.assertEqual((rtn,data[:4],data[7:10],data[-1]),(0,b'MNT\4',b'\1\6\3',0xfe|int(default)))
 def test_explicit_on_and_off_override_both_defaults(self):
  for default in (False,True):
   for mode,expected in ((0,False),(0x40,True),(0x80,default),(0xc0,default)):
    with self.subTest(default=default,mode=mode):
     m=self.board(default,mode);self.assertEqual(self.charge(m),expected)
     self.assertEqual(bool(m.num(0x50002000,4)&(1<<12)),not expected)
 def test_existing_FF_stays_soft_in_normal_build(self):
  m=self.board();self.assertEqual(m.num(m.r['group0']),255)
  self.assertFalse(self.charge(m))
 def test_live_selection_needs_no_reset(self):
  m=self.board()
  for mode,expected in ((0x40,True),(0,False),(0x40,True),(0xc0,False)):
   m.put(m.r['group0'],bytes([(m.num(m.r['group0'])&0x3f)|mode]))
   self.assertEqual(self.charge(m),expected)
 def test_recovery_priority_and_OVP_unchanged(self):
  m=self.board(mode=0x40);m.put(m.r['learned']-14+8,(-1100).to_bytes(2,'little',signed=True));m.put(0x200000c4,b'\11')
  self.assertFalse(self.charge(m));self.assertEqual(m.num(0x200000c4),10)
  m.put(m.r['learned']-14+8,bytes(2));self.assertTrue(self.charge(m))
  m.put(m.r['learned']-14+8,(-1100).to_bytes(2,'little',signed=True));m.put(0x200000c4,b'\11');m.put(0x20000031,b'\x22')
  self.assertTrue(self.charge(m));self.assertEqual(m.num(0x20000031)&0x22,0)
 def test_one_new_hook_no_new_persistent_RAM(self):
  _,facts,report=self.profiles[False]
  self.assertEqual(len(report['hooks']),21);self.assertEqual(report['ram_bytes'],4)
  self.assertIn('hook_configurable_hard_stop',report['hooks'])
 def test_C_parameter_roundtrip_preserves_other_bits(self):
  m=self.board();lower=m.num(m.r['group0'])&0x3f
  for mode in (0x40,0,0xc0):
   payload=bytearray(m.payload());payload[150]=lower|mode
   self.assertEqual(m.transact(frame(1,0xa1,payload),True),frame(1,0xa1))
   self.assertEqual(m.num(m.r['group0']),lower|mode)
   m.run(m.f['loader']);self.assertEqual(m.num(m.r['group0']),lower|mode)
   self.assertEqual(self.charge(m),mode==0x40)
 def test_recovery_counter_discovery_tracks_supported_OEMs(self):
  from seplos.configurable_hardstop import discover_configurable
  for row in fixture('supported-recovery-oems')['inputs']:
   facts=copy.deepcopy(row['facts'])
   roles=discover_configurable(Image.read(historical_input(row['input'])),facts)
   self.assertEqual(roles['recovery_counter'],row['expected_recovery_counter'],row['input'])
 def test_CLI_analyze_and_patch163(self):
  from seplos.cli import run_worker
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  for mode,default in (('analyze',False),('patch',False),('patch',True)):
   report,artifacts=run_worker(source,mode,13,maint_version='1.6.3',hard_stop='enable' if default else 'preserve')
   self.assertEqual(report['status'],'compatible' if mode=='analyze' else 'passed',report.get('error'))
   self.assertIn('configurable_hardstop',report['facts'])
   if mode=='patch':
    from seplos.configurable_hardstop_tests import REQUIRED
    self.assertTrue(set(REQUIRED)<={t['name'] for t in report['tests']})
    self.assertEqual(report['build']['image_flags'],254|int(default));self.assertIn('firmware.ehex',artifacts)
 def test_publisher_rejects_missing_capability_default_hook_or_suite(self):
  from seplos.cli import run_worker,SCHEMA
  from seplos.marker_uart0_tests import REQUIRED as M
  from seplos.service_tests import REQUIRED as S
  from seplos.permissions_tests import REQUIRED as P
  from seplos.configurable_hardstop_tests import REQUIRED as H
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  _,facts,built=self.profiles[False];built={k:v for k,v in built.items() if k not in ('resolved_assembly','disassembly')}
  base=dict(schema=SCHEMA,mode='patch',maint_version='1.6.3',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint163-real-thumb-v1',suite_complete=True,facts=facts,build=built,
   tests=[dict(name=n,passed=True) for n in [*M,*S,*P,*H,*[f'cutoff-{i}' for i in range(40)]]])
  for kind,error in (('capability','configurable_hardstop capability/default contract missing'),('default','configurable_hardstop capability/default contract missing'),('hook','configurable_hardstop hook/RAM contract missing'),('test','mandatory configurable_hardstop suite incomplete'),('polarity','build polarity differs'),('worker-polarity','worker polarity differs')):
   report=copy.deepcopy(base)
   if kind=='capability':report['build']['image_flags']&=~128
   elif kind=='default':report['build']['hard_stop_default']=True
   elif kind=='hook':report['build']['hooks'].pop('hook_configurable_hard_stop')
   elif kind=='polarity':report['build']['positive_flags']=False
   elif kind=='worker-polarity':report['positive_flags']=False
   else:report['tests']=[t for t in report['tests'] if t['name']!=H[0]]
   with tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py';worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,maint_version='1.6.3')
    self.assertEqual(artifacts,{});self.assertIn(error,result['error'])

if __name__=='__main__':unittest.main()
