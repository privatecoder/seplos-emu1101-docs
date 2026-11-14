"""Real UART0 frame regression, including the unmodified native parser/decoder."""
from pathlib import Path
import copy,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS,fixture
from seplos.image import Image
from seplos.build import build
from seplos.interrupt_tests import InterruptMachine
from seplos.machine import ascii_frame

class Polling(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=Image.read(ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex')
  cls.facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  cls.image,cls.report=build(cls.original,cls.facts,13,ext_version='1.5.6')
 def test_valid_native_frame_completes_before_deadline(self):
  m=InterruptMachine(self.image,self.facts);m.defaults(0)
  m.put(0x20000026,b'\x0b');m.run(0x13f6)
  # Drain the actual native UART0 TX interrupt until receiver turnaround.
  while m.num(0x50010004,4)&0x40:m.pend(3);m.idle()
  packet=ascii_frame(1,0x5a,bytes(range(32)))
  self.assertEqual(len(packet),82)
  m.uart0_receive(packet);m.idle()
  self.assertEqual(m.num(0x20000108),4,'native RX silence did not complete frame')
  self.assertEqual(m.read(0x20000304,82),packet)
  # OEM calls remain real; the future main-loop veneer is exercised by its site.
  from seplos.thumb import Code
  code=Code(self.original.app)
  main={i.at for i in code.body(self.facts['functions']['main'])}
  site=next(a for a in code.callers(0x14ae) if a in main)
  m.execute(site,site+4)
  self.assertFalse(m.num(0x20000000)&1,'valid complete response still waits for tick30')
  self.assertEqual(m.num(0x20000518,4)&2,2,'native online update missing')
  self.assertIn(0xeec,m.executed);self.assertIn(0x1384,m.executed)
 def test_mandatory_both_profiles(self):
  from seplos.polling_tests import validate_polling,REQUIRED
  for version in ('1.5.6','1.6.6'):
   with self.subTest(version=version):
    facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
    image,report=build(self.original,facts,13,ext_version=version)
    rows=validate_polling(self.original,image,facts,report)
    self.assertEqual({r['name'] for r in rows},set(REQUIRED))
 def test_discovery_rejects_changed_native_deadline_or_input(self):
  from seplos.polling import discover_polling
  d=discover_polling(self.original,copy.deepcopy(self.facts))
  from seplos.thumb import Code
  code=Code(self.original.app)
  limit=next(i for i in code.body(d['timer']) if i.op=='cmp' and i.args=='r0, #0x1e')
  app=bytearray(self.original.app);app[limit.at:limit.at+2]=bytes.fromhex('1d28')
  changed=self.original.with_app(app)
  with self.assertRaisesRegex(ValueError,'digest mismatch'):discover_polling(changed,copy.deepcopy(self.facts))
  facts=copy.deepcopy(self.facts);facts['original_app_sha256']=changed.sha
  with self.assertRaisesRegex(ValueError,'contract|role'):discover_polling(changed,facts)
 def test_broadcast_evaluation_preserves_native_RX_state(self):
  from seplos.polling_tests import PollMachine
  from seplos.polling import discover_polling
  d=discover_polling(self.original,copy.deepcopy(self.facts))
  for flag in (0x10,0x20):
   observed=[]
   for image in (self.original,self.image):
    m=PollMachine(image,self.facts);m.defaults(0);m.put(d['flags'],bytes([flag]));m.put(d['maximum'],b'\x0b')
    m.execute(d['start_site'],d['start_site']+4);m.turnaround()
    m.receive(ascii_frame(1,0x5a,bytes(32)))
    m.execute(d['evaluate_site'],d['evaluate_site']+4)
    observed.append((m.num(d['state']),m.num(d['rx_count'],2),m.num(d['flags'])))
   self.assertEqual(observed[0],observed[1],'broadcast native state changed before expiry')
 def test_parent_requires_rediscovered_polling_contract(self):
  from test_hardware_publication import report_fixture
  from seplos.cli import run_worker
  import tempfile
  source,base,_=report_fixture('1.5.6')
  base['facts']=copy.deepcopy(self.facts);base['build']=copy.deepcopy(self.report)
  for field,value in (('enabled',False),('counter',0x20000502),('native_contracts',{})):
   report=copy.deepcopy(base);report['build']['polling'][field]=value
   with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py'
    worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,ext_version='1.5.6')
    self.assertEqual(artifacts,{})
    self.assertIn('UART0 polling source contract missing',result['error'])
 def test_parent_requires_published_polling_veneers(self):
  from test_hardware_publication import report_fixture
  from seplos.cli import run_worker
  import tempfile,hashlib
  source,base,_=report_fixture('1.5.6')
  base['facts']=copy.deepcopy(self.facts);base['build']=copy.deepcopy(self.report)
  app=bytearray(self.image.app);site=self.report['polling']['start_site'];app[site:site+4]=b'\x00\xbf'*2
  changed=self.image.with_app(app);raw=changed.render().encode('ascii')
  base['build']['app_sha256']=changed.sha;base['output_file_sha256']=hashlib.sha256(raw).hexdigest()
  with tempfile.TemporaryDirectory() as tmp:
   worker=Path(tmp)/'worker.py'
   worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(base)+'\no=Path(sys.argv[sys.argv.index("--out")+1])\n(o/"report.json").write_text(json.dumps(r))\n(o/"firmware.ehex").write_bytes('+repr(raw)+')\n')
   result,artifacts=run_worker(source,'patch',worker=worker,ext_version='1.5.6')
   self.assertEqual(artifacts,{})
   self.assertIn('UART0 polling veneer mismatch',result['error'])
 def test_parent_binds_actual_poll_payload_and_independent_targets(self):
  from test_hardware_publication import report_fixture
  from seplos.cli import run_worker
  from seplos.thumb import encode_bl
  import tempfile,hashlib
  source,base,_=report_fixture('1.5.6')
  base['facts']=copy.deepcopy(self.facts);base['build']=copy.deepcopy(self.report)
  for kind in ('redirect-native','replace-wrapper'):
   report=copy.deepcopy(base);app=bytearray(self.image.app)
   if kind=='redirect-native':
    for name,role in (('hook_poll_start','start'),('hook_poll_evaluate','evaluate')):
     site=report['build']['polling']['hooks'][name];entry=report['build']['polling'][role]
     app[site:site+4]=encode_bl(site,entry);report['build']['entries'][name]=entry
   else:
    entry=report['build']['entries']['hook_poll_evaluate'];app[entry:entry+2]=bytes.fromhex('7047')
   changed=self.image.with_app(app);raw=changed.render().encode('ascii')
   report['build']['app_sha256']=changed.sha;report['output_file_sha256']=hashlib.sha256(raw).hexdigest()
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py'
    worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\no=Path(sys.argv[sys.argv.index("--out")+1])\n(o/"report.json").write_text(json.dumps(r))\n(o/"firmware.ehex").write_bytes('+repr(raw)+')\n(o/"payload.resolved.s").write_text("forged")\n(o/"payload.dis").write_text("forged")\n')
    result,artifacts=run_worker(source,'patch',worker=worker,ext_version='1.5.6')
    self.assertFalse(bool(artifacts),'worker-controlled entries/bytes bypassed parent gate')
    self.assertIn('independent UART0 polling',result['error'])
if __name__=='__main__':unittest.main()
