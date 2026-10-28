"""Current profile CLI publication, no-overwrite and bounded-worker failures."""
from pathlib import Path
import sys,unittest,tempfile,subprocess,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from corpus import ORIGINALS
OEM=next(ORIGINALS.glob('*16.06.13*ehex'))

class CLI(unittest.TestCase):
 def run_cli(self,*args):
  return subprocess.run([sys.executable,'-I','-B',str(ROOT/'seplos_patch.py'),*map(str,args)],cwd='/private/tmp',capture_output=True,text=True,timeout=180)
 def test_both_current_profiles_analyze_and_publish_without_polarity_flag(self):
  with tempfile.TemporaryDirectory() as tmp:
   for version,flags,minimum in (('1.5.3',58,194),('1.6.3',254,273)):
    for mode in ('analyze','patch'):
     dest=Path(tmp)/(version+'-'+mode)
     result=self.run_cli(mode,OEM,'--maint-version',version,'--base-revision','13','--out',dest)
     self.assertEqual(result.returncode,0,result.stdout+result.stderr)
     report=json.loads((dest/'report.json').read_text())
     self.assertIs(report['positive_flags'],True)
     self.assertEqual(report['maint_version'],version)
     if mode=='patch':
      self.assertEqual(report['build']['image_flags'],flags)
      self.assertEqual(report['build']['patch_version'],version)
      self.assertGreaterEqual(len(report['tests']),minimum)
      self.assertTrue((dest/'firmware.ehex').is_file())
     else:self.assertFalse((dest/'firmware.ehex').exists())
 def test_full_profile_refuses_unsupported_gate_ABI(self):
  with tempfile.TemporaryDirectory() as tmp:
   old=next(ORIGINALS.glob('*16.06.03*ehex'));dest=Path(tmp)/'refused'
   result=self.run_cli('analyze',old,'--maint-version','1.6.3','--out',dest)
   self.assertEqual(result.returncode,1,result.stdout+result.stderr)
   report=json.loads((dest/'report.json').read_text())
   self.assertIn('unsupported MAINT1.6 gate ABI',report['error'])
   self.assertFalse((dest/'firmware.ehex').exists())
 def test_patch_refuses_overwrite_and_double_patch(self):
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'result'
   result=self.run_cli('patch',OEM,'--maint-version','1.5.3','--out',dest)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertTrue((dest/'firmware.ehex').is_file())
   self.assertEqual(self.run_cli('patch',OEM,'--maint-version','1.5.3','--out',dest).returncode,2)
   other=Path(tmp)/'double'
   result=self.run_cli('patch',dest/'firmware.ehex','--maint-version','1.5.3','--out',other)
   self.assertNotEqual(result.returncode,0)
   self.assertFalse((other/'firmware.ehex').exists())
 def test_bad_container_publishes_report_only(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'bad.ehex';source.write_text(':00\n');out=Path(tmp)/'report'
   result=self.run_cli('patch',source,'--maint-version','1.5.3','--out',out)
   self.assertNotEqual(result.returncode,0)
   self.assertTrue((out/'report.json').is_file())
   self.assertFalse((out/'firmware.ehex').exists())
 def test_crashed_timed_out_and_incomplete_workers_publish_nothing(self):
  from seplos.cli import run_worker
  for code in ('import os;os.abort()','import time;time.sleep(10)','pass'):
   with tempfile.TemporaryDirectory() as tmp:
    worker=Path(tmp)/'worker.py';worker.write_text(code)
    report,artifacts=run_worker(OEM,'patch',timeout=1,worker=worker,maint_version='1.5.3')
    self.assertEqual(report['status'],'worker_failed');self.assertEqual(artifacts,{})

if __name__=='__main__':unittest.main()
