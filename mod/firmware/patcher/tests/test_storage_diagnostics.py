"""Read-only storage diagnostics and unchanged parameter semantics."""
from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame
from seplos.selftest import ascii_payload
from seplos.marker_uart0_tests import uart0_exchange
from seplos.service_tests import crc,soc_record
from unicorn.arm_const import UC_ARM_REG_PC

class StorageDiagnostics(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  cls.facts=fixture('oem-16.06.13-facts')['facts']
  cls.facts=copy.deepcopy(cls.facts)
  cls.image,cls.report=build(cls.original,cls.facts,13,maint_version='1.5.3')
 def board(self,adr=1):
  m=Machine(self.image,self.facts);m.defaults(adr);m.run(m.f['serializer'])
  record=m.read(m.r['iap_buffer'],171)
  for a in (0x25000,0x26000):m.put(a,record+crc(record)+b'\xff'*83)
  for a in (0x2b000,0x2c000):m.put(a,soc_record()+b'\xff'*232)
  m.saves.clear();m.nv_ops.clear();m.executed.clear();return m
 def query(self,m,info=b'\4',port='C',target=None):
  adr=m.num(m.r['address']);packet=ascii_frame(adr if target is None else target,0x64,info)
  raw=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
  return ascii_payload(raw,adr) if raw else None
 def test_version_and_diagnostic_only_capability(self):
  m=self.board();rtn,data=self.query(m,b'\3')
  self.assertEqual((rtn,data[:4],data[7:10],data[-1]),(0,b'MNT\4',b'\1\5\3',0x3a))
  self.assertFalse(self.report.get('cutoff',False));self.assertFalse(self.report.get('checkpoint_before_reset',False))
 def test_same_five_OEM_sites_only(self):
  expected={**self.facts['hooks'],**self.facts['marker_uart0']['hooks']}
  self.assertEqual(self.report['hooks'],expected);self.assertEqual(len(expected),5)
  changed={a for a,(x,y) in enumerate(zip(self.original.app,self.image.app)) if x!=y}
  self.assertTrue(changed<={a for site in expected.values() for a in range(site,site+4)})
 def test_read_only_R_C_and_slaves(self):
  for adr in (0,1,11,21):
   for port in ('R','C'):
    with self.subTest(adr=adr,port=port):
     m=self.board(adr);m.put(m.r['group0'],b'\0');before=m.read(0x23000,0xa000);params=m.payload()
     self.assertEqual(self.query(m,port=port),(0,bytes([1,1,1,1,1,1,1,255,255,0])))
     self.assertEqual(m.read(0x23000,0xa000),before);self.assertEqual(m.payload(),params)
     self.assertEqual(m.saves,[]);self.assertEqual(m.nv_ops,[])
     self.assertNotIn(m.f['iap_read'],m.executed)
 def test_corrupt_diagnosis_does_not_repair(self):
  for port in ('R','C'):
   m=self.board();m.put(0x25000+171,b'\0\0');m.put(0x2b000,b'\xff'*256)
   before=m.read(0x25000,0x8000)
   self.assertEqual(self.query(m,port=port),(0,bytes([1,2,1,0,0,1,0,255,255,0])))
   self.assertEqual(m.read(0x25000,0x8000),before);self.assertEqual(m.nv_ops,[])
 def test_reserved_bit5_never_reported_as_lock(self):
  for value in (0,32,255):
   m=self.board();m.put(m.r['group0'],bytes([value]))
   for a in (0x25000,0x26000):
    record=bytearray(m.read(a,171));record[163]=value;m.put(a,record+crc(record))
   answer=self.query(m);self.assertIsNotNone(answer)
   self.assertEqual(answer[1][7:],b'\xff\xff\0')
 def test_foreign_and_FF_silent(self):
  for port in ('R','C'):
   for target in (0,2,255):
    m=self.board();self.assertIsNone(self.query(m,port=port,target=target))
    self.assertEqual(m.nv_ops,[])
 def test_R_C_reset_remains_without_checkpoint(self):
  for port in ('R','C'):
   m=self.board();m.put(m.r['group0'],bytes([m.num(m.r['group0'])|8]))
   m.pause=m.facts['power_rtc']['reset'];before=m.read(0x25000,0x8000)
   packet=ascii_frame(1,0x45,b'\0\6\0')
   if port=='R':uart0_exchange(m,packet)
   else:
    m.feed(packet);site=m.facts['hooks']['hook_dispatch'];m.execute(site,site+4)
   self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),m.pause)
   self.assertNotIn(m.f['capacity_save'],m.executed)
   self.assertEqual(m.read(0x25000,0x8000),before);self.assertEqual(m.nv_ops,[])
 def test_CLI_analyze_and_patch152(self):
  from seplos.cli import run_worker
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  for mode in ('analyze','patch'):
   report,artifacts=run_worker(source,mode,13,maint_version='1.5.3')
   self.assertEqual(report['status'],'compatible' if mode=='analyze' else 'passed',report.get('error'))
   self.assertIn('storage_diagnostics',report['facts']);self.assertNotIn('cutoff',report['facts'])
   if mode=='patch':
    from seplos.storage_diagnostics_tests import REQUIRED
    self.assertTrue(set(REQUIRED)<={t['name'] for t in report['tests']})
    self.assertEqual(report['build']['image_flags'],58);self.assertIn('firmware.ehex',artifacts)
 def test_CLI_optional_hard_stop(self):
  from seplos.cli import run_worker
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  report,artifacts=run_worker(source,'patch',13,maint_version='1.5.3',hard_stop='enable')
  self.assertEqual(report['status'],'passed',report.get('error'))
  self.assertEqual(report['build']['image_flags'],59);self.assertEqual(len(report['build']['hooks']),5)
  self.assertTrue(report['build']['hard_stop']['enabled']);self.assertIn('firmware.ehex',artifacts)
 def test_publication_rejects_wrong_capabilities_hooks_or_suite(self):
  from seplos.cli import run_worker,SCHEMA
  from seplos.marker_uart0_tests import REQUIRED as M
  from seplos.storage_diagnostics_tests import REQUIRED as D
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  base=dict(schema=SCHEMA,mode='patch',maint_version='1.5.3',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint153-real-thumb-v1',suite_complete=True,facts=self.facts,
   tests=[dict(name=n,passed=True) for n in [*M,*D,*[f'other-{i}' for i in range(60)]]],
   build=dict(patch_version='1.5.3',info_format=4,info_bytes=19,uart0_marker=True,image_flags=58,positive_flags=True,storage_diagnostics=True,extended_diagnostics=True,checkpoint_before_reset=False,ram_bytes=0,hooks=self.report['hooks']))
  for kind,error in (('capabilities','storage_diagnostics capability contract missing'),('hooks','storage_diagnostics five-hook contract missing'),('test','mandatory storage_diagnostics suite incomplete')):
   report=copy.deepcopy(base)
   if kind=='capabilities':report['build']['image_flags']|=64
   elif kind=='hooks':report['build']['hooks']['new_hook']=0xa00
   else:report['tests']=[t for t in report['tests'] if t['name']!=D[0]]
   with tempfile.TemporaryDirectory() as temp:
    worker=Path(temp)/'worker.py';worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,maint_version='1.5.3')
    self.assertEqual(artifacts,{});self.assertIn(error,result['error'])

if __name__=='__main__':unittest.main()
