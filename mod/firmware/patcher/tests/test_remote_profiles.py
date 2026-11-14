"""New profiles require explicit immutable remote-read capabilities."""
from pathlib import Path
import copy,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from seplos.profiles import SUPPORTED_VERSIONS,require_profile
from seplos.cli import run_worker,SCHEMA
from corpus import ORIGINALS
import hashlib

class RemoteProfiles(unittest.TestCase):
 def test_current_and_reference_profiles_are_explicit(self):
  self.assertEqual(SUPPORTED_VERSIONS,('1.5.4','1.6.4','1.5.5','1.6.5','1.6.6','1.5.6','1.6.7'))
 def test_previous_outputs_are_rejected_before_build(self):
  for version in ('1.5.3','1.6.3'):
   with self.subTest(version=version),self.assertRaises(ValueError):require_profile(version)
 def test_parent_requires_ext05_and_remote_capability_contract(self):
  self.assertIn('1.5.4',SUPPORTED_VERSIONS,'new profile is not supported yet')
  from seplos.marker_uart0_tests import REQUIRED as MARKER
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  base=dict(schema=SCHEMA,mode='patch',ext_version='1.5.4',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='ext154-real-thumb-v1',suite_complete=True,
   tests=[dict(name=x,passed=True) for x in [*MARKER,*[f'other-{i}' for i in range(80)]]],
   build=dict(patch_version='1.5.4',info_format=5,info_bytes=21,uart0_marker=True,image_flags=58,remote_capabilities=15,remote_diagnostics=True))
  for field,value in [('info_format',4),('info_bytes',19),('remote_capabilities',7)]:
   report=copy.deepcopy(base);report['build'][field]=value
   with tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py'
    worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,ext_version='1.5.4')
    self.assertEqual(artifacts,{})
    self.assertIn('remote info contract missing',result['error'])

 def test_parent_refuses_each_missing_feature_group_for_both_profiles(self):
  from seplos.remote_diagnostics_tests import REQUIRED as REMOTE
  from test_hardware_publication import report_fixture
  for version in SUPPORTED_VERSIONS:
   source,base,_=report_fixture(version)
   for missing in REMOTE:
    with self.subTest(profile=version,missing=missing),tempfile.TemporaryDirectory() as tmp:
     report=copy.deepcopy(base);report['tests']=[r for r in report['tests'] if r['name']!=missing]
     worker=Path(tmp)/'worker.py'
     worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
     result,artifacts=run_worker(source,'patch',worker=worker,ext_version=version)
     self.assertEqual(artifacts,{})
     self.assertIn('mandatory remote diagnostics suite incomplete',result['error'])

if __name__=='__main__':unittest.main()
