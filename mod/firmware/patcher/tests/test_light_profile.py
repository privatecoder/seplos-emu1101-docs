"""Lightweight profile permissions, diagnostics and bounded publication."""
from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS, LEGACY, legacy_files, historical_input, fixture
from seplos.image import Image
from seplos.build import build
from seplos.machine import Machine,ascii_frame
from seplos.selftest import ascii_payload
from seplos.marker_uart0_tests import uart0_exchange
from unicorn.arm_const import UC_ARM_REG_PC

class LightProfile(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  cls.original=Image.read(cls.source)
  cls.facts=copy.deepcopy(fixture('oem-16.06.13-facts')['facts'])
  cls.image,cls.report=build(cls.original,cls.facts,13,maint_version='1.5.3')
 def board(self,adr=1,bit3=True,bit4=False):
  m=Machine(self.image,self.facts);m.defaults(adr)
  m.put(m.r['group0'],bytes([(m.num(m.r['group0'])&~24)|(8 if bit3 else 0)|(16 if bit4 else 0)]))
  m.saves.clear();m.nv_ops.clear();m.flash_ops.clear();m.executed.clear();return m
 def query(self,m,cmd,data=b'',port='C'):
  adr=m.num(m.r['address']);packet=ascii_frame(adr,cmd,data)
  raw=uart0_exchange(m,packet) if port=='R' else m.transact(packet,True)
  return ascii_payload(raw,adr) if raw else None
 def test_info153_positive_without_cutoff(self):
  for port in ('R','C'):
   for adr in (0,1,21):
    rtn,data=self.query(self.board(adr),0x64,b'\3',port)
    self.assertEqual((rtn,data[:4],data[7:10],data[-1]),(0,b'MNT\4',b'\1\5\3',0x3a))
 def test_C_power_RTC_permission_both_values_and_roles(self):
  for adr in (0,1,11,21):
   for allowed in (False,True):
    for cmd,data in ((0x45,b'\0\4\x10'),(0x45,b'\0\4\x1f'),(0x4e,bytes.fromhex('07EA0A18010203'))):
     m=self.board(adr,allowed);self.assertEqual(self.query(m,cmd,data),(0 if allowed else 5,b''))
     self.assertEqual(m.saves,[]);self.assertEqual(m.nv_ops,[])
 def test_R_power_independent_of_C_permission(self):
  for allowed in (False,True):
   m=self.board(bit3=allowed);self.assertEqual(self.query(m,0x45,b'\0\4\x1f','R'),(0,b''))
 def test_bit4_reserved_and_no_power_persistence(self):
  for port in ('R','C'):
   for bit4 in (False,True):
    m=self.board(bit4=bit4);before=m.read(0x25000,0x8000);group=m.num(m.r['group0'])
    self.assertEqual(self.query(m,0x45,b'\0\4\x1f',port),(0,b''))
    self.assertEqual(m.num(m.r['group0']),group);self.assertEqual(m.read(0x25000,0x8000),before)
    self.assertEqual(m.saves,[]);self.assertEqual(m.nv_ops,[])
 def test_reset_remains_without_SOC_checkpoint(self):
  for port in ('R','C'):
   m=self.board();m.pause=m.facts['power_rtc']['reset'];before=m.read(0x25000,0x8000)
   packet=ascii_frame(1,0x45,b'\0\6\0')
   if port=='R':uart0_exchange(m,packet)
   else:
    m.feed(packet);site=m.facts['hooks']['hook_dispatch'];m.execute(site,site+4)
   self.assertEqual(m.uc.reg_read(UC_ARM_REG_PC),m.pause)
   self.assertEqual(m.read(0x25000,0x8000),before);self.assertEqual(m.saves,[])
 def test_diagnostics_stay_free_R_C(self):
  for port in ('R','C'):
   m=self.board(bit3=False);rtn,data=self.query(m,0x64,b'\4',port)
   self.assertEqual((rtn,len(data),data[0],data[7:]),(0,10,1,b'\xff\xff\0'))
   self.assertEqual(m.saves,[]);self.assertEqual(m.nv_ops,[])
 def test_five_OEM_sites_zero_RAM(self):
  expected={**self.facts['hooks'],**self.facts['marker_uart0']['hooks']}
  self.assertEqual(self.report['hooks'],expected);self.assertEqual(len(expected),5)
  self.assertEqual(self.report['ram_bytes'],0);self.assertTrue(self.report['positive_flags'])
  self.assertFalse(self.report.get('cutoff'));self.assertFalse(self.report.get('checkpoint_before_reset'))
  allowed={a for site in expected.values() for a in range(site,site+4)}
  self.assertTrue(all(a in allowed or x==y for a,(x,y) in enumerate(zip(self.original.app,self.image.app))))
 @classmethod
 def CLI(cls,hard='preserve'):
  from seplos.cli import run_worker
  return run_worker(cls.source,'patch',13,maint_version='1.5.3',hard_stop=hard)
 def test_CLI_analyze_patch_and_static_hard_stop(self):
  from seplos.cli import run_worker
  analyzed,_=run_worker(self.source,'analyze',13,maint_version='1.5.3')
  self.assertEqual(analyzed['status'],'compatible',analyzed.get('error'))
  for hard,flag in [('preserve',0x3a),('enable',0x3b)]:
   report,artifacts=self.CLI(hard);self.assertEqual(report['status'],'passed',report.get('error'))
   self.assertIn('firmware.ehex',artifacts);self.assertEqual(report['build']['image_flags'],flag)
   self.assertTrue(any(t['name']=='storage_diagnostics-positive-power-permission' for t in report['tests']))
   self.assertFalse(any(t['name'].startswith('positive-bit4-') for t in report['tests']))
 def test_publication_rejects_wrong_capabilities_hooks_or_old_suite(self):
  from seplos.cli import run_worker,SCHEMA
  from seplos.marker_uart0_tests import REQUIRED as M
  from seplos.storage_diagnostics_tests import REQUIRED as D
  base=dict(schema=SCHEMA,mode='patch',maint_version='1.5.3',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),suite='maint153-real-thumb-v1',suite_complete=True,facts=self.facts,
   tests=[dict(name=n,passed=True) for n in [*M,*D,*[f'other-{i}' for i in range(60)]]],
   build=dict(patch_version='1.5.3',info_format=4,info_bytes=19,uart0_marker=True,image_flags=58,positive_flags=True,storage_diagnostics=True,extended_diagnostics=True,checkpoint_before_reset=False,ram_bytes=0,hooks=self.report['hooks']))
  for kind,error in [('capability','capability contract'),('hooks','five-hook contract'),('old-suite','suite incomplete'),('RAM','capability contract')]:
   report=copy.deepcopy(base)
   if kind=='capability':report['build']['image_flags']|=4
   elif kind=='hooks':report['build']['hooks']['new_hook']=0xa00
   elif kind=='RAM':report['build']['ram_bytes']=4
   else:report['tests']=[t for t in report['tests'] if t['name']!=D[0]]
   with tempfile.TemporaryDirectory() as temp:
    worker=Path(temp)/'worker.py';worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(self.source,'patch',worker=worker,maint_version='1.5.3')
    self.assertEqual(artifacts,{});self.assertIn(error,result['error'])

if __name__=='__main__':unittest.main()
