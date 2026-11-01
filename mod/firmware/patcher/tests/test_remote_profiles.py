"""New profiles require explicit immutable remote-read capabilities."""
from pathlib import Path
import copy,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from seplos.profiles import SUPPORTED_VERSIONS,require_profile
from seplos.cli import run_worker,SCHEMA
from corpus import ORIGINALS
import hashlib

class RemoteProfiles(unittest.TestCase):
 def test_only_154_and_164_are_current(self):
  self.assertEqual(SUPPORTED_VERSIONS,('1.5.4','1.6.4'))
 def test_previous_outputs_are_rejected_before_build(self):
  for version in ('1.5.3','1.6.3'):
   with self.subTest(version=version),self.assertRaises(ValueError):require_profile(version)
 def test_parent_requires_mnt05_and_remote_capability_contract(self):
  self.assertIn('1.5.4',SUPPORTED_VERSIONS,'new profile is not supported yet')
  from seplos.marker_uart0_tests import REQUIRED as MARKER
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  base=dict(schema=SCHEMA,mode='patch',maint_version='1.5.4',positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint154-real-thumb-v1',suite_complete=True,
   tests=[dict(name=x,passed=True) for x in [*MARKER,*[f'other-{i}' for i in range(80)]]],
   build=dict(patch_version='1.5.4',info_format=5,info_bytes=21,uart0_marker=True,image_flags=58,remote_capabilities=15,remote_diagnostics=True))
  for field,value in [('info_format',4),('info_bytes',19),('remote_capabilities',7)]:
   report=copy.deepcopy(base);report['build'][field]=value
   with tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py'
    worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
    result,artifacts=run_worker(source,'patch',worker=worker,maint_version='1.5.4')
    self.assertEqual(artifacts,{})
    self.assertIn('remote info contract missing',result['error'])

 def test_parent_refuses_each_missing_feature_group_for_both_profiles(self):
  from seplos.remote_diagnostics_tests import REQUIRED as REMOTE
  from seplos.marker_uart0_tests import REQUIRED as MARKER
  from seplos.storage_diagnostics_tests import REQUIRED as LIGHT
  from seplos.service_tests import REQUIRED as SERVICE
  from seplos.configurable_hardstop_tests import REQUIRED as HARDSTOP
  from seplos.permissions_tests import REQUIRED as POSITIVE
  source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
  for version in SUPPORTED_VERSIONS:
   light=version=='1.5.4'
   hooks={**{f'hook_{i}':i*4 for i in range(4)},'marker':16}
   facts=dict(hooks={k:v for k,v in hooks.items() if k!='marker'},marker_uart0=dict(hooks=dict(marker=16)))
   if not light:
    hooks={f'hook_{i}':i*4 for i in range(20)};hooks['hook_configurable_hard_stop']=80
    facts['configurable_hardstop']=dict(site=80)
   names=(*MARKER,*(LIGHT if light else (*SERVICE,*HARDSTOP,*POSITIVE)),*REMOTE)
   built=dict(patch_version=version,info_format=5,info_bytes=21,remote_capabilities=15,remote_diagnostics=True,uart0_marker=True,image_flags=58 if light else 254,positive_flags=True,extended_diagnostics=True,ram_bytes=0 if light else 4,hooks=hooks)
   if light:built.update(storage_diagnostics=True,checkpoint_before_reset=False)
   else:built.update(service=True,checkpoint_before_reset=True,configurable_hard_stop=True,hard_stop_default=False)
   base=dict(schema=SCHEMA,mode='patch',maint_version=version,positive_flags=True,status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite='maint'+version.replace('.','')+'-real-thumb-v1',suite_complete=True,facts=facts,build=built)
   rows=[dict(name=n,passed=True) for n in (*names,*[f'cutoff-{i}' for i in range(30)],*[f'other-{i}' for i in range(60)])]
   for missing in REMOTE:
    with self.subTest(profile=version,missing=missing),tempfile.TemporaryDirectory() as tmp:
     report=copy.deepcopy(base);report['tests']=[r for r in rows if r['name']!=missing]
     worker=Path(tmp)/'worker.py'
     worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
     result,artifacts=run_worker(source,'patch',worker=worker,maint_version=version)
     self.assertEqual(artifacts,{})
     self.assertIn('mandatory remote diagnostics suite incomplete',result['error'])

if __name__=='__main__':unittest.main()
