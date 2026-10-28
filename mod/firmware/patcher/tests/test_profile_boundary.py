"""Current-only production boundaries, before any image execution/publication."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from seplos.build import build
from seplos.cli import run_worker, worker_job
RETIRED=('1.5','1.6','1.5.1','1.5.2','1.6.1','1.6.2')

class Profiles(unittest.TestCase):
 def cli(self,*args):
  return subprocess.run([sys.executable,'-I','-B',str(ROOT/'seplos_patch.py'),*map(str,args)],cwd='/private/tmp',capture_output=True,text=True)
 def test_help_has_only_current_profiles_and_no_polarity_option(self):
  result=self.cli('patch','--help')
  self.assertEqual(result.returncode,0)
  self.assertIn('{1.5.3,1.6.3}',result.stdout)
  self.assertNotIn('--positive-flags',result.stdout)
 def test_cli_refuses_retired_profiles_before_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   for version in RETIRED:
    out=Path(tmp)/version
    result=self.cli('patch','missing.ehex','--maint-version',version,'--out',out)
    self.assertEqual(result.returncode,2,result.stdout+result.stderr)
    self.assertFalse(out.exists())
 def test_profile_is_required_and_removed_mode_and_flag_are_errors(self):
  with tempfile.TemporaryDirectory() as tmp:
   for extra in ([],['--maint-version','1.5.3','--positive-flags']):
    out=Path(tmp)/'missing-profile'
    result=self.cli('patch','missing.ehex',*extra,'--out',out)
    self.assertEqual(result.returncode,2,result.stdout+result.stderr)
    self.assertFalse(out.exists())
   result=self.cli('hard-stop','missing.ehex','--out',Path(tmp)/'standalone')
   self.assertEqual(result.returncode,2)
 def test_python_builder_refuses_retired_versions_before_reading_input(self):
  for version in RETIRED:
   with self.subTest(version=version),self.assertRaisesRegex(ValueError,'unsupported MAINT version'):
    build(None,None,maint_version=version)
 def test_polarity_is_not_an_api_option(self):
  with self.assertRaises(TypeError):build(None,None,maint_version='1.5.3',positive_flags=False)
 def test_parent_refuses_old_profile_or_mode_before_starting_worker(self):
  with patch('seplos.cli.subprocess.Popen',side_effect=AssertionError('worker must not start')):
   for version in RETIRED:
    with self.assertRaisesRegex(ValueError,'unsupported MAINT version'):
     run_worker('missing.ehex','patch',maint_version=version)
   with self.assertRaisesRegex(ValueError,'unsupported mode'):
    run_worker('missing.ehex','hard-stop',maint_version='1.5.3')
 def test_private_worker_cannot_build_retired_profiles(self):
  with tempfile.TemporaryDirectory() as tmp:
   for version in RETIRED:
    with self.assertRaisesRegex(ValueError,'unsupported MAINT version'):
     worker_job(Path('missing.ehex'),Path(tmp),'patch',13,'preserve',version)
   self.assertEqual(list(Path(tmp).iterdir()),[])

 def test_python_apis_have_no_implicit_profile(self):
  with self.assertRaises(TypeError):build(None,None)
  with self.assertRaises(TypeError):run_worker('missing.ehex','patch')
  with self.assertRaises(TypeError):worker_job(Path('missing.ehex'),Path('/private/tmp'),'patch',13,'preserve')
 def test_private_cli_requires_a_current_profile_without_old_flag(self):
  with tempfile.TemporaryDirectory() as tmp:
   for extra in ([],['--maint-version','1.5.2'],['--maint-version','1.5.3','--positive-flags']):
    out=Path(tmp)/'private'
    result=self.cli('_worker','missing.ehex','--mode','patch',*extra,'--out',out)
    self.assertEqual(result.returncode,2,result.stdout+result.stderr)
    self.assertFalse(out.exists())
 def test_corpus_cli_has_the_same_profile_boundary(self):
  with tempfile.TemporaryDirectory() as tmp:
   for extra in ([],['--maint-version','1.6.2'],['--maint-version','1.6.3','--positive-flags']):
    out=Path(tmp)/'corpus'
    result=subprocess.run([sys.executable,'-I','-B',str(ROOT/'verify_corpus.py'),*extra,'--out',str(out)],cwd='/private/tmp',capture_output=True,text=True)
    self.assertEqual(result.returncode,2,result.stdout+result.stderr)
    self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
