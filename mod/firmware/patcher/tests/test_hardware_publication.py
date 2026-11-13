"""Publication refuses any omitted hardware/timing/concurrency native group."""
from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS
from seplos.cli import SCHEMA,run_worker


def report_fixture(version):
 from seplos.marker_uart0_tests import REQUIRED as MARKER
 from seplos.storage_diagnostics_tests import REQUIRED as LIGHT
 from seplos.service_tests import REQUIRED as SERVICE
 from seplos.configurable_hardstop_tests import REQUIRED as HARDSTOP
 from seplos.permissions_tests import REQUIRED as POSITIVE
 from seplos.remote_diagnostics_tests import REQUIRED as REMOTE
 from seplos.hardware_tests import REQUIRED as HARDWARE
 from seplos.uart_timing_tests import REQUIRED as TIMING
 from seplos.interrupt_tests import REQUIRED as INTERRUPTS,FULL_REQUIRED
 from seplos.cutoff_tests import FAST_REQUIRED
 light=version.startswith('1.5.');atomic=version in ('1.5.5','1.6.5')
 hooks={**{f'hook_{i}':i*4 for i in range(4)},'marker':16}
 facts=dict(hooks={k:v for k,v in hooks.items() if k!='marker'},marker_uart0=dict(hooks=dict(marker=16)))
 if not light:
  hooks={f'hook_{i}':i*4 for i in range(20)};hooks['hook_configurable_hard_stop']=80
  facts['configurable_hardstop']=dict(site=80)
 if atomic:
  hooks['hook_scheduler_atomic']=84;facts['scheduler_atomic']=dict(hooks={'hook_scheduler_atomic':84})
 built=dict(patch_version=version,info_format=5,info_bytes=21,remote_capabilities=15,
  remote_diagnostics=True,uart0_marker=True,image_flags=58 if light else 254,
  positive_flags=True,extended_diagnostics=True,ram_bytes=0 if light else 4,hooks=hooks)
 if light:built.update(storage_diagnostics=True,checkpoint_before_reset=False)
 else:built.update(service=True,cutoff=True,checkpoint_before_reset=True,configurable_hard_stop=True,hard_stop_default=False)
 groups=[('hardware',HARDWARE),('UART timing',TIMING),
         ('interrupt',INTERRUPTS+(() if light else FULL_REQUIRED))]
 if not light:groups.append(('fast current',FAST_REQUIRED))
 if atomic:
  from seplos.scheduler_atomic_tests import REQUIRED as ATOMIC
  groups.append(('scheduler atomic',ATOMIC))
  built['scheduler_atomic']=dict(enabled=True)
 names=(*MARKER,*(LIGHT if light else (*SERVICE,*HARDSTOP,*POSITIVE)),*REMOTE,
        *(n for _,group in groups for n in group),*[f'cutoff-{i}' for i in range(30)],
        *[f'other-{i}' for i in range(60)])
 source=ORIGINALS/'CAN1101[V16.06.13_PN01_250607].ehex'
 report=dict(schema=SCHEMA,mode='patch',ext_version=version,positive_flags=True,
  status='passed',stage='complete',input_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
  suite='ext'+version.replace('.','')+'-real-thumb-v1',suite_complete=True,
  facts=facts,build=built,tests=[dict(name=n,passed=True) for n in names])
 return source,report,groups


class HardwarePublication(unittest.TestCase):
 def test_each_missing_group_is_refused_for_each_profile(self):
  for version in ('1.5.4','1.6.4','1.5.5','1.6.5'):
   source,base,groups=report_fixture(version)
   for label,group in groups:
    for missing in group:
     with self.subTest(profile=version,group=label,missing=missing),tempfile.TemporaryDirectory() as tmp:
      report=copy.deepcopy(base);report['tests']=[r for r in report['tests'] if r['name']!=missing]
      worker=Path(tmp)/'worker.py'
      worker.write_text('from pathlib import Path\nimport json,sys\nr='+repr(report)+'\nPath(sys.argv[sys.argv.index("--out")+1],"report.json").write_text(json.dumps(r))\n')
      result,artifacts=run_worker(source,'patch',worker=worker,ext_version=version)
      self.assertEqual(artifacts,{})
      self.assertIn('mandatory '+label+' suite incomplete',result['error'])


if __name__=='__main__':unittest.main()
